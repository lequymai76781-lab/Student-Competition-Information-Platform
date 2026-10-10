from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.api.deps import _current_user
from app.core.ratelimit import _store
from app.main import app
from app.models import (AdminAuditLog, Competition, CompetitionEdition, CompetitionFactRevision,
                        ReviewQueue, User, UserCorrectionSubmission)
from conftest import temporary_dependency_override


def _origin(client, kind, identity):
    response = client.post(f'/api/admin/field-review-origins/{kind}/{identity}')
    assert response.status_code == 200, response.text
    response = client.get(f"/api/admin/field-reviews/{response.json()['data']['field_review_id']}")
    assert response.status_code == 200, response.text
    return response.json()['data']


def _verify(client, data):
    for field in data['fields']:
        for proposal in field['proposals']:
            response = client.post(f"/api/admin/field-reviews/{data['id']}/sources/{proposal['id']}/verify",
                json={'preview_token': data['preview_token'], 'note': '核对来源原文'})
            assert response.status_code == 200, response.text
            data = response.json()['data']
    return data


def _approve(client, data, field_name, note='已核对官方来源'):
    field = next(field for field in data['fields'] if field['field_name'] == field_name)
    return client.post(f"/api/admin/field-reviews/{data['id']}/review", json={
        'preview_token': data['preview_token'], 'note': note,
        'decisions': [{'field_name': field_name, 'action': 'approve', 'proposal_id': field['proposals'][0]['id']}],
    })


@pytest.fixture()
def identity(db_session):
    _store.clear()
    user = User(email='journey@example.test', username='journey', hashed_password='unused-in-override')
    db_session.add(user)
    db_session.commit()
    with temporary_dependency_override(app, _current_user, lambda: user):
        yield user


def test_new_competition_supplement_stays_in_review_and_can_be_tracked(client, db_session, identity):
    before = db_session.scalar(select(func.count()).select_from(Competition))
    response = client.post('/api/users/me/supplements', json={
        'kind': 'competition', 'title': '未收录的测试赛事',
        'description': '请核对赛事官网与学校认定附件', 'source_url': 'https://example.edu.cn/notice',
    })
    assert response.status_code == 200
    data = response.json()['data']
    assert data['status'] == 'pending'
    queue = db_session.get(ReviewQueue, data['id'])
    assert queue.item_type == 'user_supplement'
    assert queue.source_url == 'https://example.edu.cn/notice'
    assert db_session.scalar(select(func.count()).select_from(Competition)) == before
    assert client.get('/api/users/me/supplements').json()['data'][0]['id'] == queue.id
    assert client.get('/api/admin/review/supplements').status_code == 403
    identity.is_admin = True
    db_session.commit()
    assert client.get('/api/admin/review/feedback?status=pending').json()['data'] == []
    assert client.get('/api/admin/review/summary').json()['data']['beta_feedback_pending'] == 0
    assert client.put(f'/api/admin/review/feedback/{queue.item_id}',
                      json={'status': 'approved'}).status_code == 409
    assert queue.status == 'pending'
    response = client.put(f'/api/admin/review/supplements/{queue.id}', json={
        'status': 'verified_pending_import', 'note': '来源已核验，待整理入库',
    })
    assert response.status_code == 409
    data = _verify(client, _origin(client, 'supplement', queue.id))
    assert data['status'] == 'pending'
    assert client.get('/api/users/me/supplements').json()['data'][0]['status'] == 'pending'
    assert db_session.scalar(select(func.count()).select_from(Competition)) == before
    response = _approve(client, data, 'name')
    assert response.status_code == 200, response.text
    assert client.get('/api/users/me/supplements').json()['data'][0]['status'] == 'approved'
    assert db_session.scalar(select(func.count()).select_from(Competition)) == before + 1
    assert db_session.scalar(select(func.count()).select_from(AdminAuditLog).where(AdminAuditLog.action == 'field_source_verify')) == 1
    assert db_session.scalar(select(func.count()).select_from(AdminAuditLog).where(AdminAuditLog.action == 'field_review')) == 1


@pytest.mark.parametrize('source', ['javascript:alert(1)', 'file:///tmp/test', 'invalid-url'])
def test_supplement_rejects_unsafe_source(client, identity, source):
    response = client.post('/api/users/me/supplements', json={
        'kind': 'school', 'title': '未收录学校', 'description': '学校官方通知地址', 'source_url': source,
    })
    assert response.status_code == 422


def test_supplement_requires_login(client):
    response = client.post('/api/users/me/supplements', json={
        'kind': 'school', 'title': '未收录学校', 'description': '学校信息说明',
    })
    assert response.status_code == 401


def test_correction_rejects_edition_from_other_competition(client, db_session, identity):
    other = Competition(name='另一赛事', is_demo=False)
    db_session.add(other)
    db_session.flush()
    edition = CompetitionEdition(competition_id=other.id, year=2027)
    db_session.add(edition)
    db_session.commit()
    response = client.post('/api/users/me/corrections', json={
        'competition_id': 1, 'competition_edition_id': edition.id,
        'correction_type': '报名截止错误', 'description': '截止时间与通知不一致',
    })
    assert response.status_code == 422
    assert db_session.scalar(select(func.count()).select_from(UserCorrectionSubmission)) == 0


def test_deadline_review_applies_only_explicit_edition_and_retains_audit(client, db_session, identity):
    response = client.post('/api/users/me/corrections', json={
        'competition_id': 1, 'competition_edition_id': 1, 'correction_type': '报名截止错误',
        'description': '依据官方通知延期', 'source_url': 'https://example.edu.cn/updated',
    })
    correction_id = response.json()['data']['id']
    assert db_session.get(UserCorrectionSubmission, correction_id).status == 'pending'
    assert db_session.scalar(select(func.count()).select_from(ReviewQueue).where(ReviewQueue.item_type == 'user_correction')) == 1
    assert db_session.scalar(select(func.count()).select_from(ReviewQueue).where(ReviewQueue.item_type == 'field_candidate')) == 1
    newer = CompetitionEdition(competition_id=1, year=2027, official_registration_deadline=None)
    db_session.add(newer)
    identity.is_admin = True
    db_session.commit()
    deadline = datetime.now(timezone.utc) + timedelta(days=8)
    response = client.put(f'/api/admin/review/corrections/{correction_id}', json={
        'status': 'approved', 'new_deadline': deadline.isoformat(), 'note': '已核对官方延期通知',
    })
    assert response.status_code == 409
    data = _origin(client, 'correction', correction_id)
    prepared = client.put(f"/api/admin/field-reviews/{data['id']}/prepare", json={
        'preview_token': data['preview_token'], 'entity_type': 'edition', 'competition_id': 1,
        'edition_id': 1, 'year': 2026, 'title': '核对指定届次报名截止',
        'fields': [{'field_name': 'official_registration_deadline', 'candidate_value': deadline.isoformat(),
            'source': {'source_type': 'organizer_notice', 'source_url': 'https://example.edu.cn/updated'}}],
    })
    assert prepared.status_code == 200, prepared.text
    response = _approve(client, _verify(client, prepared.json()['data']), 'official_registration_deadline')
    assert response.status_code == 200, response.text
    assert db_session.get(CompetitionEdition, 1).official_registration_deadline.replace(tzinfo=timezone.utc) == deadline
    assert newer.official_registration_deadline is None
    assert db_session.scalar(select(func.count()).select_from(CompetitionFactRevision)) == 1
    assert all(queue.status == 'approved' for queue in db_session.scalars(select(ReviewQueue)))
    assert client.put(f'/api/admin/review/corrections/{correction_id}', json={'status': 'approved'}).status_code == 409


@pytest.mark.parametrize('missing', ['source', 'edition', 'deadline'])
def test_deadline_approval_requires_evidence_and_target(client, db_session, identity, missing):
    identity.is_admin = True
    row = UserCorrectionSubmission(user_id=identity.id, competition_id=1,
        competition_edition_id=None if missing == 'edition' else 1,
        correction_type='报名截止错误', description='待核验报名截止', status='pending',
        source_url=None if missing == 'source' else 'https://example.edu.cn/notice')
    db_session.add(row)
    db_session.commit()
    payload = {'status': 'approved'}
    if missing != 'deadline':
        payload['new_deadline'] = '2026-10-05T23:59:59+08:00'
    assert client.put(f'/api/admin/review/corrections/{row.id}', json=payload).status_code == 409
    data = _origin(client, 'correction', row.id)
    field = {'field_name': 'official_registration_deadline', 'candidate_value': '2026-10-05T23:59:59+08:00',
        'source': None if missing == 'source' else {'source_type': 'organizer_notice', 'source_url': row.source_url}}
    prepared = client.put(f"/api/admin/field-reviews/{data['id']}/prepare", json={
        'preview_token': data['preview_token'], 'entity_type': 'edition', 'competition_id': 1,
        'edition_id': row.competition_edition_id, 'title': '核验报名截止',
        'fields': [] if missing == 'deadline' else [field],
    })
    if missing == 'source':
        assert prepared.status_code == 200, prepared.text
        assert _approve(client, prepared.json()['data'], 'official_registration_deadline').status_code == 422
    else:
        assert prepared.status_code == 422, prepared.text
    assert row.status == 'pending'
