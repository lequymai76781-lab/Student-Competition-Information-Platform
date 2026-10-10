"""Risk, queue and atomic bulk contracts on isolated fixture data."""
import json
import pytest
from fastapi import HTTPException
from sqlalchemy import event, select
from app.models import AdminAuditLog, Competition, CompetitionFactRevision, ReviewQueue, User
from app.services.field_review_service import FieldReviewService as Review

@pytest.fixture
def reviewer(db_session):
    actor=User(email='throughput@example.test',username='throughput',hashed_password='unused',is_admin=True)
    db_session.add(actor);db_session.commit()
    return actor

def item(field='frequency',value='每年一届',source_type='official_website',url='https://example.test/source'):
    return {'field_name':field,'candidate_value':value,'source':None if source_type is None else {
        'source_type':source_type,'source_url':url,'source_title':'官方资料','publisher':'组委会'}}

def stage(db,fields=None,cid=1,**kwargs):
    row=Review.create_candidate(db,{'entity_type':'competition','competition_id':cid,'title':'真实结构测试候选',
        'fields':fields if fields is not None else [item()],**kwargs})
    db.commit();return row

def verified(db,row,actor):
    detail=Review.detail(db,row.id)
    for field in detail['fields']:
        for proposal in field['proposals']:
            detail=Review.verify_source(db,row.id,proposal['id'],{'preview_token':detail['preview_token'],'note':'逐条检查原文'},admin=actor)
    db.commit();return detail

def member(d):
    return {'id':d['id'],'preview_token':d['preview_token'],'field_names':['frequency']}

def test_low_risk_is_not_permission_to_approve_unverified_source(db_session,reviewer):
    row=stage(db_session);d=Review.detail(db_session,row.id)
    assert d['risk_level']=='LOW_RISK' and d['low_risk_fields']==['frequency'] and not d['bulk_eligible_fields']
    preview=Review.bulk_preview(db_session,{'items':[member(d)],'note':'先看摘要'},admin=reviewer)
    assert preview['field_count']==1 and preview['transaction']=='atomic'
    with pytest.raises(HTTPException):
        Review.bulk_review(db_session,{'items':[member(d)],'note':'未核验不能提交'},admin=reviewer)
    assert db_session.get(Competition,1).frequency is None

@pytest.mark.parametrize('field,value,source_type,expected',[
    ('frequency','每年一届','university_policy','LOW_RISK'),
    ('frequency','每年一届','industry_organization','HIGH_RISK'),
    ('frequency','每年一届',None,'HIGH_RISK'),
    ('organizer','新主办方','official_website','HIGH_RISK'),
    ('name','新名称','official_website','HIGH_RISK'),
    ('english_name','New title','official_website','HIGH_RISK'),
    ('founded_year',2015,'official_website','HIGH_RISK'),
    ('history_timeline',[{'year':2020,'title':'历史'}],'official_website','HIGH_RISK'),
    ('description',None,'official_website','HIGH_RISK'),
])
def test_risk_rules_exclude_weak_missing_overwrite_and_important_fields(db_session,field,value,source_type,expected):
    d=Review.detail(db_session,stage(db_session,[item(field,value,source_type)]).id)
    assert d['risk_level']==expected
    if expected=='HIGH_RISK':assert not d['low_risk_fields'] and d['risk_reasons']

def test_conflict_or_identity_flag_excludes_entire_candidate(db_session,reviewer):
    d=verified(db_session,stage(db_session,[item(),item(value='每两年一届')]),reviewer)
    assert d['risk_level']=='HIGH_RISK' and 'CONFLICT' in d['risk_reasons'] and not d['bulk_eligible_fields']
    other=stage(db_session,[item('official_account','官方账号')]);doc=json.loads(other.raw_value)
    doc['collection_context']={'flags':['DUPLICATE_SUSPECTED']};other.raw_value=json.dumps(doc);db_session.commit()
    assert Review.detail(db_session,other.id)['risk_level']=='HIGH_RISK'

def test_consistent_sources_low_risk_after_every_source_verified(db_session,reviewer):
    d=verified(db_session,stage(db_session,[item(),item(url='https://example.test/second')]),reviewer)
    assert d['risk_level']=='LOW_RISK' and d['bulk_eligible_fields']==['frequency']
    result=Review.bulk_review(db_session,{'items':[member(d)],'note':'两份原文一致'},admin=reviewer);db_session.commit()
    assert result['succeeded']==1 and db_session.get(Competition,1).frequency=='每年一届'
    audit=db_session.scalars(select(AdminAuditLog).where(AdminAuditLog.action=='field_review')).one()
    assert len(audit.after['review']['sources'])==2

def test_bulk_crosses_entities_and_sources_with_per_candidate_audit(db_session,reviewer):
    db_session.add(Competition(name='第二赛事'));db_session.commit()
    ds=[verified(db_session,r,reviewer) for r in [stage(db_session),stage(db_session,[item(url='https://example.test/second')],cid=2)]]
    result=Review.bulk_review(db_session,{'items':[member(d) for d in ds],'note':'逐来源确认批量'},admin=reviewer);db_session.commit()
    assert result['total']==result['succeeded']==2 and result['failed']==0 and result['pending_ids']==[]
    assert [db_session.get(Competition,i).frequency for i in [1,2]]==['每年一届']*2
    assert len(list(db_session.scalars(select(AdminAuditLog).where(AdminAuditLog.action=='field_review'))))==2

def test_nineteenth_failure_rolls_back_batch_and_reports_identity(db_session,reviewer,monkeypatch):
    rows=[]
    for index in range(20):
        comp=Competition(name=f'批量赛事{index}');db_session.add(comp);db_session.flush();rows.append(stage(db_session,cid=comp.id))
    ds=[verified(db_session,r,reviewer) for r in rows];original=Review._record_fact
    def fail(db,doc,*args):
        if doc['competition_id']==rows[18].competition_id:raise RuntimeError('injected nineteenth failure')
        return original(db,doc,*args)
    monkeypatch.setattr(Review,'_record_fact',fail)
    with pytest.raises(HTTPException) as caught:
        Review.bulk_review(db_session,{'items':[member(d) for d in ds],'note':'整批回滚'},admin=reviewer)
    assert caught.value.detail['succeeded']==0 and caught.value.detail['failed_candidate_id']==rows[18].id
    assert len(caught.value.detail['pending_ids'])==20
    db_session.commit()
    assert all(db_session.get(ReviewQueue,r.id).status=='pending' for r in rows)
    assert all(db_session.get(Competition,r.competition_id).frequency is None for r in rows)
    assert list(db_session.scalars(select(CompetitionFactRevision)))==[]
    assert list(db_session.scalars(select(AdminAuditLog).where(AdminAuditLog.action=='field_review')))==[]

def test_timeline_orders_later_notices_and_preserves_field_scope(db_session):
    earlier=item();earlier['source']['published_at']='2026-05-01T00:00:00Z'
    later=item(value='每两年一届',url='https://example.test/change');later['source'].update(published_at='2026-05-18T00:00:00Z',source_title='更正通知')
    timeline=Review.detail(db_session,stage(db_session,[later,earlier]).id)['fields'][0]['timeline']
    assert [t['candidate_value'] for t in timeline]==['每年一届','每两年一届']
    assert timeline[1]['announcement_hint']=='更正' and all(t['scope']=='赛事本体' for t in timeline)

def test_five_hundred_search_filter_pagination_query_bound(db_session):
    for index in range(521):Review.create_candidate(db_session,{'entity_type':'competition','competition_id':1,'title':f'候选{index:03}','fields':[item()]})
    db_session.commit();queries=[]
    def count(*args):queries.append(1)
    event.listen(db_session.bind,'before_cursor_execute',count)
    try:page=Review.list_candidates(db_session,risk='LOW_RISK',search='frequency',sort='oldest',limit=20,offset=500)
    finally:event.remove(db_session.bind,'before_cursor_execute',count)
    assert page['total']==521 and len(page['items'])==20 and page['items'][0]['title']=='候选500'
    assert len(queries)<=12,len(queries)
    assert Review.list_candidates(db_session,search='官方资料',limit=20,offset=520)['total']==521
    assert Review.list_candidates(db_session,search='测试计算机设计',limit=20)['total']==521
    assert Review.list_candidates(db_session,search='does-not-exist',limit=20)['total']==0
    detail=Review.detail(db_session,page['items'][0]['id'])
    assert detail['fields'][0]['timeline_total']==521
    assert len(detail['fields'][0]['timeline'])==50

def test_non_admin_cannot_bulk_preview(db_session):
    actor=User(email='ordinary@example.test',username='ordinary',hashed_password='unused',is_admin=False)
    db_session.add(actor);db_session.commit();d=Review.detail(db_session,stage(db_session).id)
    with pytest.raises(HTTPException) as caught:Review.bulk_preview(db_session,{'items':[member(d)],'note':'无权限'},admin=actor)
    assert caught.value.status_code==403


def test_queue_search_accepts_displayed_chinese_field_name(db_session):
    row=stage(db_session)
    result=Review.list_candidates(db_session,search='举办频率',limit=20,offset=0)
    assert [d['id'] for d in result['items']]==[row.id]

@pytest.mark.parametrize('model_name',['UniversityCompetitionEditionRelation','PolicyDocument','CompetitionPolicyRecognition'])
def test_runtime_cannot_bypass_relation_review(db_session,model_name):
    import app.models as models
    from sqlalchemy import delete
    from app.database.review_guard import ReviewGuardedSession,UnreviewedFactWrite
    model=getattr(models,model_name)
    with ReviewGuardedSession(bind=db_session.bind) as runtime:
        with pytest.raises(UnreviewedFactWrite):runtime.execute(delete(model).where(model.id<0))

def test_new_external_conflict_invalidates_preview_but_refreshed_manual_choice_can_proceed(db_session,reviewer):
    row=stage(db_session);old=verified(db_session,row,reviewer)
    stage(db_session,[item(value='每两年一届',url='https://example.test/later')])
    fresh=Review.detail(db_session,row.id)
    assert fresh['risk_level']=='HIGH_RISK'
    assert fresh['preview_token']!=old['preview_token']
    decision={'field_name':'frequency','action':'approve','proposal_id':old['fields'][0]['proposals'][0]['id']}
    with pytest.raises(HTTPException) as caught:
        Review.review(db_session,row.id,{'preview_token':old['preview_token'],'note':'旧预览不能提交','decisions':[decision]},admin=reviewer)
    assert caught.value.status_code==409 and db_session.get(Competition,1).frequency is None
    Review.review(db_session,row.id,{'preview_token':fresh['preview_token'],'note':'比较双方原文后明确选择年度举办','decisions':[decision]},admin=reviewer)
    assert db_session.get(Competition,1).frequency=='每年一届'

def test_first_target_lock_failure_reports_first_candidate(db_session,reviewer):
    db_session.add(Competition(name='另一个锁目标'));db_session.commit()
    rows=[stage(db_session),stage(db_session,cid=2)]
    ds=[verified(db_session,r,reviewer) for r in rows];injected=[]
    def change(connection,cursor,statement,parameters,context,executemany):
        if not injected and statement.startswith('UPDATE competitions '):
            injected.append(True)
            connection.exec_driver_sql("UPDATE competitions SET frequency='changed' WHERE id=1")
    event.listen(db_session.bind,'before_cursor_execute',change)
    try:
        with pytest.raises(HTTPException) as caught:
            Review.bulk_review(db_session,{'items':[member(d) for d in ds],'note':'第一个目标变化'},admin=reviewer)
    finally:event.remove(db_session.bind,'before_cursor_execute',change)
    assert caught.value.status_code==409 and injected
    assert caught.value.detail['failed_candidate_id']==rows[0].id
    assert caught.value.detail['succeeded']==0

def test_http_bulk_failure_exposes_safe_structured_recovery_result(db_session,reviewer):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.deps import get_current_admin,get_db
    from app.api.routes.field_reviews import router
    from app.core.exceptions import register_exception_handlers
    app=FastAPI();app.include_router(router,prefix='/api');register_exception_handlers(app)
    app.dependency_overrides[get_db]=lambda:db_session
    app.dependency_overrides[get_current_admin]=lambda:reviewer
    d=Review.detail(db_session,stage(db_session).id)
    with TestClient(app) as client:
        response=client.post('/api/admin/field-reviews/bulk-review',json={'items':[member(d)],'note':'来源尚未核验'})
    assert response.status_code==422
    result=response.json();assert result['message'].startswith('批量仅支持')
    assert result['meta']['details']['succeeded']==0
    assert result['meta']['details']['pending_ids']==[d['id']]
