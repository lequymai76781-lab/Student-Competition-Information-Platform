"""Learning data is derived from committed human audit, never client claims."""
import hashlib
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.api.deps import get_current_admin
from app.main import app
from app.models import AdminAuditLog, Competition, User
from app.services.competition_field_ingestion_service import CompetitionFieldIngestionService
from app.services.field_review_service import FieldReviewService


@pytest.fixture
def learning(client, db_session, monkeypatch, tmp_path):
    from app.services.review_learning_service import candidate_features, canonical_hash
    actor = User(username='learning-reviewer', email='lr@example.test', hashed_password='unused', is_admin=True, is_active=True)
    db_session.add(actor)
    db_session.commit()
    comp = db_session.scalar(select(Competition))
    row = CompetitionFieldIngestionService().stage(db_session, entity_type='competition', competition_id=comp.id,
        title='关于组织竞赛报名的通知', fields={'frequency': '每年一次'},
        source={'source_type': 'university_notice', 'source_title': '关于组织竞赛报名的通知',
                'source_url': 'https://source.example.edu.cn/notice', 'publisher': '教务处'},
        raw={'title': '关于组织竞赛报名的通知', 'content_preview': '请报名并提交材料。'})
    db_session.commit()
    manifest = tmp_path/'manifest.json'
    manifest.write_text(json.dumps({'dataset_id': 'isolated-unit-fixture', 'origin': 'real_candidate',
        'candidates': {str(row.id): {'candidate_sha256': canonical_hash(candidate_features(db_session, row.id))}}}), encoding='utf8')
    monkeypatch.setenv('REVIEW_LEARNING_DB', str(tmp_path/'learning.sqlite'))
    monkeypatch.setenv('REVIEW_LEARNING_MANIFEST', str(manifest))
    monkeypatch.setenv('REVIEW_LEARNING_ACTOR_MODE', 'human')
    app.dependency_overrides[get_current_admin] = lambda: actor
    try:
        yield client, db_session, actor, row, comp, manifest
    finally:
        app.dependency_overrides.pop(get_current_admin, None)


def open_session(ctx):
    client, _, _, row, _, _ = ctx
    response = client.post('/api/admin/review-learning/sessions', json={'candidate_id': row.id})
    assert response.status_code == 200, response.text
    return response.json()['data']['session_id']


def submit_event(ctx, sid, primary='participation'):
    response = ctx[0].post(f'/api/admin/review-learning/sessions/{sid}/events', json={
        'event': 'submit', 'details': {'human_primary_type': primary}})
    assert response.status_code == 200, response.text


def reject(ctx, sid=None):
    client, db, actor, row, _, _ = ctx
    detail = FieldReviewService.detail(db, row.id)
    return client.post(f'/api/admin/field-reviews/{row.id}/review', headers={'X-Review-Learning-Session':sid} if sid else {}, json={
        'preview_token': detail['preview_token'], 'note': '已核对原始资料，不采用该字段候选。',
        'decisions': [{'field_name': 'frequency', 'action': 'reject'}]})


def test_open_blind_session_cannot_change_candidate_or_official(learning):
    client, db, _, row, comp, _ = learning
    before = row.raw_value, row.status, comp.frequency
    sid = open_session(learning)
    response = client.post('/api/admin/review-learning/sessions', json={'candidate_id': row.id})
    assert response.json()['data']['session_id'] == sid
    assert not any('shadow' in key or 'prediction' in key for key in response.json()['data'])
    db.refresh(row); db.refresh(comp)
    assert before == (row.raw_value, row.status, comp.frequency)


def test_finish_requires_committed_audit_and_not_client_assertion(learning):
    sid = open_session(learning)
    response = learning[0].post(f'/api/admin/review-learning/sessions/{sid}/complete', json={'human_primary_type': 'participation'})
    assert response.status_code == 409
    forged = learning[0].post(f'/api/admin/review-learning/sessions/{sid}/complete', json={'human_primary_type': 'participation', 'human_action': 'approve'})
    assert forged.status_code == 422
    assert learning[0].get('/api/admin/review-learning/examples').json()['data']['total'] == 0


def test_business_commit_automatically_records_immutable_example(learning):
    client, db, _, row, comp, _ = learning
    old = comp.frequency
    sid = open_session(learning)
    client.post(f'/api/admin/review-learning/sessions/{sid}/events', json={'event': 'source_open'})
    client.post(f'/api/admin/review-learning/sessions/{sid}/events', json={'event': 'decision'})
    submit_event(learning, sid)
    response = reject(learning,sid)
    assert response.status_code == 200, response.text
    examples = client.get('/api/admin/review-learning/examples').json()['data']['items']
    assert len(examples) == 1
    example = examples[0]
    assert example['human_ground_truth']['human_action'] == 'reject'
    assert example['human_ground_truth']['human_field_decisions'] == {'frequency': 'reject'}
    assert example['human_ground_truth']['human_risk_level'] is None
    assert example['review_context']['source_open_count'] == 1
    assert example['review_context']['review_duration'] >= 0
    assert example['review_context']['audit_id'] > 0
    assert example['shadow_prediction']['shadow_model_version']
    replay = client.post(f'/api/admin/review-learning/sessions/{sid}/complete', json={'human_primary_type': 'participation'})
    assert replay.status_code == 200
    assert client.get('/api/admin/review-learning/examples').json()['data']['total'] == 1
    db.refresh(comp)
    assert comp.frequency == old


def test_failed_business_submit_never_creates_sample(learning):
    sid = open_session(learning); submit_event(learning, sid)
    client, _, _, row, _, _ = learning
    result = client.post(f'/api/admin/field-reviews/{row.id}/review', json={'preview_token': 'stale', 'note': 'invalid',
        'decisions': [{'field_name': 'frequency', 'action': 'reject'}]})
    assert result.status_code == 409
    assert client.get('/api/admin/review-learning/examples').json()['data']['total'] == 0


def test_automation_on_genuine_candidate_cannot_enter_real_learning(learning, monkeypatch):
    monkeypatch.setenv('REVIEW_LEARNING_ACTOR_MODE', 'automation')
    sid = open_session(learning); submit_event(learning, sid)
    assert reject(learning,sid).status_code == 200
    result = learning[0].post(f'/api/admin/review-learning/sessions/{sid}/complete', json={'human_primary_type': 'participation'})
    assert result.status_code in {403, 409}
    assert learning[0].get('/api/admin/review-learning/examples').json()['data']['total'] == 0


def test_old_audit_cannot_be_claimed_as_new_review(learning):
    client, db, actor, row, _, _ = learning
    db.add(AdminAuditLog(admin_id=actor.id, object_type='field_candidate', object_id=row.id,
        action='field_review', after={'review': {'decisions': [{'field_name':'frequency','action':'reject'}]}},
        created_at=datetime.now(timezone.utc)))
    db.commit()
    sid = open_session(learning); submit_event(learning, sid)
    assert client.post(f'/api/admin/review-learning/sessions/{sid}/complete', json={'human_primary_type':'participation'}).status_code == 409


def test_session_and_examples_require_admin(client):
    for method, path, data in [('GET','/performance',None),('GET','/examples',None),('GET','/config',None),
            ('GET','/batches',None),('POST','/sessions',{'candidate_id':1}),('POST','/replay',{}),
            ('POST','/batches',{'min_samples':100})]:
        response = client.request(method, '/api/admin/review-learning'+path, json=data)
        assert response.status_code == 403


def test_current_human_label_not_leaked_to_predictor_features(learning):
    from app.services.review_learning_service import candidate_features
    _, db, _, row, _, _ = learning
    doc=json.loads(row.raw_value)
    doc['document_classification']={'human_primary_type':'policy','shadow_reason':'SECRET'}
    doc['decisions']={'frequency':{'action':'approved','note':'SECRET'}}
    doc['history']=[{'note':'SECRET'}]
    row.raw_value=json.dumps(doc)
    db.commit()
    assert 'SECRET' not in json.dumps(candidate_features(db,row.id))


def test_unknown_candidate_rejected_without_manifest_entry(learning):
    learning[5].write_text(json.dumps({'dataset_id':'empty','origin':'real_candidate','candidates':{}}))
    assert learning[0].post('/api/admin/review-learning/sessions',json={'candidate_id':learning[3].id}).status_code == 409


def test_changed_input_rejected_after_open(learning):
    sid=open_session(learning)
    _,db,_,row,_,_=learning
    doc=json.loads(row.raw_value);doc['proposals'][0]['candidate_value']='每月一次'
    row.raw_value=json.dumps(doc);db.commit()
    response=learning[0].post(f'/api/admin/review-learning/sessions/{sid}/complete',json={'human_primary_type':'participation'})
    assert response.status_code == 409


def test_other_admin_cannot_use_session(learning):
    sid=open_session(learning)
    client,db,_,_,_,_=learning
    actor=User(username='second',email='second@example.test',hashed_password='unused',is_admin=True,is_active=True)
    db.add(actor);db.commit();app.dependency_overrides[get_current_admin]=lambda:actor
    assert client.post(f'/api/admin/review-learning/sessions/{sid}/events',json={'event':'source_open'}).status_code == 403


def test_learning_path_cannot_be_formal_database(learning, monkeypatch):
    monkeypatch.setenv('REVIEW_LEARNING_DB',str(__import__('pathlib').Path(__file__).resolve().parents[2]/'data/v02.sqlite'))
    assert learning[0].get('/api/admin/review-learning/config').status_code == 409


def test_correction_preserves_audit_truth_and_supersedes(learning):
    client=learning[0];sid=open_session(learning);submit_event(learning,sid)
    assert reject(learning,sid).status_code == 200
    before=client.get('/api/admin/review-learning/examples').json()['data']['items'][0]
    response=client.post(f"/api/admin/review-learning/examples/{before['id']}/correct",json={
        'human_ground_truth':{'human_primary_type':'information'},'reason':'人工重新核对原文，纠正文档功能。'})
    assert response.status_code == 200, response.text
    after=response.json()['data']
    assert after['human_ground_truth']['human_action']=='reject'
    assert after['human_ground_truth']['human_field_decisions']=={'frequency':'reject'}
    rows=client.get('/api/admin/review-learning/examples').json()['data']['items']
    assert len(rows)==2
    assert {r['learning_status'] for r in rows}=={'superseded','corrected'}
    performance=client.get('/api/admin/review-learning/performance').json()['data']
    assert performance['sample_count']==1
    assert performance['windows']['all']['risk_denominator']==0
    assert performance['windows']['all']['risk_agreement'] is None


def test_correction_cannot_rewrite_business_action(learning):
    client=learning[0];sid=open_session(learning);submit_event(learning,sid)
    assert reject(learning,sid).status_code==200
    example=client.get('/api/admin/review-learning/examples').json()['data']['items'][0]
    result=client.post(f"/api/admin/review-learning/examples/{example['id']}/correct",json={
        'human_ground_truth':{'human_primary_type':'policy','human_action':'approve'},'reason':'forged'})
    assert result.status_code==422


def test_empty_statistics_and_underfilled_batch_are_not_success(learning):
    client=learning[0]
    stats=client.get('/api/admin/review-learning/performance').json()['data']
    assert stats['sample_count']==0
    assert stats['windows']['all']['primary_accuracy'] is None
    assert stats['windows']['all']['policy_precision'] is None
    assert client.post('/api/admin/review-learning/batches',json={'min_samples':100}).status_code==409
    replay=client.post('/api/admin/review-learning/replay').json()['data']
    assert replay['sample_count']==0 and replay['model_updated'] is False


def test_persisted_non_admin_cannot_read_learning(client,db_session):
    from app.core.config import get_settings
    from app.core.security import create_token
    person=User(username='ordinary-person',email='ordinary@example.test',hashed_password='unused',is_admin=False,is_active=True)
    db_session.add(person);db_session.commit()
    headers={'Authorization':'Bearer '+create_token(person.id,get_settings().app_secret)}
    for path in ('config','performance','examples','batches'):
        assert client.get('/api/admin/review-learning/'+path,headers=headers).status_code==403


def test_submit_label_cannot_change_after_business_commit(learning):
    client=learning[0];sid=open_session(learning);submit_event(learning,sid)
    assert reject(learning,sid).status_code==200
    changed=client.post(f'/api/admin/review-learning/sessions/{sid}/complete',json={'human_primary_type':'policy'})
    assert changed.status_code==409


def test_sidecar_failure_after_commit_keeps_review_and_allows_learning_retry(learning,monkeypatch):
    from app.services.review_learning_store import ReviewLearningStore
    sid=open_session(learning);submit_event(learning,sid)
    original=ReviewLearningStore.complete
    def unavailable(*args,**kwargs):
        raise OSError('temporary isolated sidecar failure')
    monkeypatch.setattr(ReviewLearningStore,'complete',unavailable)
    assert reject(learning,sid).status_code==200
    learning[1].refresh(learning[3])
    assert learning[3].status=='rejected'
    monkeypatch.setattr(ReviewLearningStore,'complete',original)
    response=learning[0].post(f'/api/admin/review-learning/sessions/{sid}/complete',json={'human_primary_type':'participation'})
    assert response.status_code==200,response.text
    assert learning[0].get('/api/admin/review-learning/examples').json()['data']['total']==1


def test_learning_config_exists_but_is_disabled_by_default(client, db_session, monkeypatch):
    monkeypatch.delenv('REVIEW_LEARNING_DB', raising=False)
    actor = User(username='learning-admin', email='learning@example.test', hashed_password='unused', is_admin=True, is_active=True)
    db_session.add(actor)
    db_session.commit()
    app.dependency_overrides[get_current_admin] = lambda: actor
    try:
        response = client.get('/api/admin/review-learning/config')
        assert response.status_code == 200
        assert response.json()['data']['enabled'] is False
    finally:
        app.dependency_overrides.pop(get_current_admin, None)


def test_orphan_submit_cannot_capture_later_unrelated_business_audit(learning):
    sid=open_session(learning);submit_event(learning,sid)
    # A later ordinary review has no learning session header and must not inherit old labels.
    assert reject(learning).status_code==200
    assert learning[0].get('/api/admin/review-learning/examples').json()['data']['total']==0
    assert learning[0].post(f'/api/admin/review-learning/sessions/{sid}/complete',json={'human_primary_type':'participation'}).status_code==409


def test_correction_retry_is_idempotent_at_http_boundary(learning):
    client=learning[0];sid=open_session(learning);submit_event(learning,sid)
    assert reject(learning,sid).status_code==200
    original=client.get('/api/admin/review-learning/examples').json()['data']['items'][0]
    payload={'human_ground_truth':{'human_primary_type':'information'},'reason':'同一次人工纠正重试'}
    first=client.post(f"/api/admin/review-learning/examples/{original['id']}/correct",json=payload)
    second=client.post(f"/api/admin/review-learning/examples/{original['id']}/correct",json=payload)
    assert first.status_code==200
    assert second.status_code==200,second.text
    assert first.json()['data']['id']==second.json()['data']['id']


def test_primary_only_correction_preserves_explicit_secondary_and_risk(learning):
    client=learning[0];sid=open_session(learning)
    labels={'human_primary_type':'participation','human_secondary_type':'selection','human_risk_level':'HIGH_RISK'}
    assert client.post(f'/api/admin/review-learning/sessions/{sid}/events',json={'event':'submit','details':labels}).status_code==200
    assert reject(learning,sid).status_code==200
    original=client.get('/api/admin/review-learning/examples').json()['data']['items'][0]
    changed=client.post(f"/api/admin/review-learning/examples/{original['id']}/correct",json={'human_ground_truth':{'human_primary_type':'update'},'reason':'仅修改一级类型'})
    assert changed.status_code==200
    truth=changed.json()['data']['human_ground_truth']
    assert truth['human_secondary_type']=='selection'
    assert truth['human_risk_level']=='HIGH_RISK'


def test_plain_body_change_invalidates_blind_prediction_before_business_write(learning):
    from app.services.review_learning_service import candidate_features,canonical_hash
    client,db,_,row,_,manifest=learning
    doc=json.loads(row.raw_value);doc['description']='原文：请报名参加竞赛。';row.raw_value=json.dumps(doc);db.commit()
    m=json.loads(manifest.read_text(encoding='utf8'));m['candidates'][str(row.id)]['candidate_sha256']=canonical_hash(candidate_features(db,row.id));manifest.write_text(json.dumps(m),encoding='utf8')
    sid=open_session(learning);submit_event(learning,sid)
    doc['description']='新原文：报名截止日期已经更正。';row.raw_value=json.dumps(doc);db.commit()
    result=reject(learning,sid)
    assert result.status_code==409
    db.refresh(row);assert row.status=='pending'


def test_audited_preparation_preserves_original_shadow_and_records_new_review_context(learning):
    client,db,actor,row,_,_=learning
    sid=open_session(learning)
    doc=json.loads(row.raw_value);doc['year']=2025;row.raw_value=json.dumps(doc)
    db.add(AdminAuditLog(admin_id=actor.id,object_type='field_candidate',object_id=row.id,
        action='field_prepare',after={'review':{'note':'人工明确届次'}},created_at=datetime.now(timezone.utc)))
    db.commit();submit_event(learning,sid)
    result=reject(learning,sid)
    assert result.status_code==200,result.text
    example=client.get('/api/admin/review-learning/examples').json()['data']['items'][0]
    assert example['input_features']['edition'] is None
    assert example['review_context']['prepared_during_review'] is True


def test_http_performance_exposes_learning_state(learning):
    data=learning[0].get('/api/admin/review-learning/performance').json()['data']
    assert data['status']=='observing'


def test_explicit_normal_risk_uses_same_vocabulary_as_shadow(learning):
    client=learning[0];sid=open_session(learning)
    labels={'human_primary_type':'participation','human_risk_level':'NORMAL'}
    response=client.post(f'/api/admin/review-learning/sessions/{sid}/events',json={'event':'submit','details':labels})
    assert response.status_code==200,response.text
    assert reject(learning,sid).status_code==200
    result=client.post(f'/api/admin/review-learning/sessions/{sid}/complete',json=labels)
    assert result.status_code==200,result.text
    assert result.json()['data']['human_ground_truth']['human_risk_level']=='NORMAL'
