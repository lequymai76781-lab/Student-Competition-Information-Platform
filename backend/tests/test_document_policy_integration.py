"""Policy automation contract: real guarded sessions, isolated fixtures only."""
import importlib
import json
from datetime import datetime, timezone
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.database.base import Base
from app.database.session import SessionLocal
from app.models import User, University, Competition, PolicyDocument, CompetitionPolicyRecognition, AdminAuditLog, ReviewQueue
from app.services.competition_field_ingestion_service import CompetitionFieldIngestionService

NOW=datetime(2026,10,1,tzinfo=timezone.utc)
@pytest.fixture(autouse=True)
def hypothetically_authorized_policy_mechanics(monkeypatch):
 # These synthetic integration fixtures exercise the existing evidence gates
 # after hypothetical validation. Actual default-off safety has separate tests.
 from app.services import document_calibration_policy as calibration
 from app.services.source_document_classifier import DOCUMENT_TYPES
 monkeypatch.setattr(calibration,'AUTO_THRESHOLDS',{kind:.90 for kind in DOCUMENT_TYPES})
 monkeypatch.setattr(calibration,'INFORMATIONAL_AUTO_ENABLED',True)
 monkeypatch.setattr(calibration,'POLICY_AUTO_ENABLED',True)
 # Exercise hypothetical validated information routing; production remains held.
 monkeypatch.setattr(calibration,'HIERARCHICAL_AUTO_THRESHOLDS',{'participation':.90,'result':.90,'information':.90,'repost':.90,'policy':None,'update':None,'other':None})
 monkeypatch.setattr(calibration,'HIERARCHICAL_INFORMATIONAL_ENABLED',True)

@pytest.fixture
def svc():
 try:return importlib.import_module('app.services.document_policy_service')
 except ModuleNotFoundError:pytest.fail('Document policy integration not implemented')

@pytest.fixture
def db():
 engine=create_engine('sqlite:///:memory:',connect_args={'check_same_thread':False},poolclass=StaticPool)
 Base.metadata.create_all(engine)
 with Session(engine) as s:
  s.add_all([University(id=1,name='示例大学',official_domain='example.edu.cn'),Competition(id=1,name='全国大学生数学建模竞赛',short_name='数学建模竞赛',is_official_verified=True,verification_status='verified_official'),Competition(id=2,name='全国大学生电子设计竞赛',is_official_verified=True,verification_status='verified_official'),User(id=1,username='admin',email='admin@local.test',hashed_password='fixture',is_admin=True,is_active=True),User(id=2,username='normal',email='normal@local.test',hashed_password='fixture',is_admin=False,is_active=True)])
  s.commit()
 with SessionLocal(bind=engine) as s:yield s
 engine.dispose()

def policy(db,**kw):
 values=dict(university_id=1,title='示例大学2026年推免竞赛目录',publisher='示例大学教务处',source_url='https://jwc.example.edu.cn/policy/2026.html',content_text='本办法适用于全校本科学生。本竞赛目录自2026年1月1日起施行，列入以下竞赛的获奖学生可以获得推荐免试加分。\n1. 全国大学生数学建模竞赛\n2. 全国大学生电子设计竞赛',effective_from=datetime(2026,1,1,tzinfo=timezone.utc),effective_until=datetime(2026,12,31,23,59,59,tzinfo=timezone.utc),published_at=datetime(2026,1,1,tzinfo=timezone.utc),is_verified=True,is_current=True,verification_status='official_domain_verified',parser_type='html',year=2026,scope_type='university',metadata_json={})
 values.update(kw)
 with Session(db.get_bind()) as s:
  row=PolicyDocument(**values);s.add(row);s.commit();identity=row.id
 return identity

def analyze(svc,db,identity):return svc.PolicyAutomationService.analyze(db,identity,admin=db.get(User,1),now=NOW)

def source_candidate(db,title,fields=None):
 row=CompetitionFieldIngestionService().stage(db,entity_type='competition',title=title,competition_id=1,fields=fields or {},source={'source_type':'university_notice','source_title':title,'source_url':'https://jwc.example.edu.cn/news'},raw={'title':title,'content_preview':'学校举办的竞赛活动已经结束。','content_text':'学校举办的竞赛活动已经结束。学生完成作品展示，本页回顾赛事活动过程。','content_is_complete':True})
 db.commit();return row

def test_information_archived_but_source_kept(svc,db):
 row=source_candidate(db,'数学建模竞赛圆满结束')
 result=svc.DocumentPolicyService.classify_candidate(db,row.id,admin=db.get(User,1))
 assert result['classification']['informational_only'] is True
 assert db.get(ReviewQueue,row.id).status=='informational'
 assert db.get(ReviewQueue,row.id).source_url=='https://jwc.example.edu.cn/news'
 from app.services.field_review_service import FieldReviewService
 assert FieldReviewService.list_candidates(db,status='pending')['total']==0

def test_information_title_never_hides_fact_proposal(svc,db):
 row=source_candidate(db,'数学建模竞赛圆满结束',{'frequency':'每年举办'})
 result=svc.DocumentPolicyService.classify_candidate(db,row.id,admin=db.get(User,1))
 assert result['classification']['informational_only'] is False
 assert row.status=='pending'
 assert db.get(Competition,1).frequency is None

def test_correction_is_audited_and_survives_replay(svc,db):
 row=source_candidate(db,'数学建模竞赛圆满结束')
 svc.DocumentPolicyService.classify_candidate(db,row.id,admin=db.get(User,1))
 result=svc.DocumentPolicyService.correct_classification(db,row.id,'registration_notice','标题有歧义，已看正文',admin=db.get(User,1))
 assert result['classification']['document_type']=='registration_notice'
 assert row.status=='pending'
 log=db.scalar(select(AdminAuditLog).where(AdminAuditLog.action=='document_classification_corrected'))
 assert log.after['predicted_type']=='completion_news' and log.after['final_type']=='registration_notice'
 assert log.admin_id==1 and log.after['matched_rules'] and log.after['corrected_at']
 assert svc.DocumentPolicyService.classify_candidate(db,row.id,admin=db.get(User,1))['classification']['document_type']=='registration_notice'

def test_nonadmin_cannot_correct(svc,db):
 row=source_candidate(db,'普通通知')
 with pytest.raises(HTTPException) as exc:svc.DocumentPolicyService.correct_classification(db,row.id,'policy_recognition_document','冒充政策',admin=db.get(User,2))
 assert exc.value.status_code==403

def test_high_confidence_policy_relations_with_audit_and_no_fact_write(svc,db):
 identity=policy(db)
 result=analyze(svc,db,identity)
 assert result['automatic_relations']==2, result
 rows=list(db.scalars(select(CompetitionPolicyRecognition)))
 assert len(rows)==2 and {x.usage_type for x in rows}=={'postgraduate_recommendation_recognition'}
 for row in rows:
  evidence=json.loads(row.evidence_text)
  assert evidence['verification_method']=='AUTO_POLICY_MATCH'
  assert evidence['source_url'].startswith('https://jwc.example.edu.cn/')
  assert evidence['matched_raw_name'] and evidence['match_reason'] and evidence['effective_from']
 assert db.get(Competition,1).name=='全国大学生数学建模竞赛'
 assert db.scalar(select(func.count()).select_from(AdminAuditLog).where(AdminAuditLog.action=='auto_policy_match'))==2
 again=analyze(svc,db,identity)
 assert again['automatic_relations']==2
 assert db.scalar(select(func.count()).select_from(CompetitionPolicyRecognition))==2
 assert db.scalar(select(func.count()).select_from(AdminAuditLog).where(AdminAuditLog.action=='auto_policy_match'))==2

@pytest.mark.parametrize('changes,reason',[
 ({'source_url':'https://example.edu.cn.evil.test/policy'},'official_source'),
 ({'source_url':'https://example.edu.cn@evil.test/policy'},'official_source'),
 ({'source_url':'https://thirdparty.test/policy','official_domain':'thirdparty.test'},'official_source'),
 ({'is_verified':False},'source_unverified'),
 ({'title':'关于组织参加数学建模竞赛报名通知'},'not_formal_policy'),
 ({'content_text':''},'missing_content'),
 ({'effective_from':None},'validity_unclear'),
 ({'effective_until':datetime(2025,12,31,tzinfo=timezone.utc)},'expired'),
 ({'metadata_json':{'needs_ocr':True}},'ocr'),
 ({'attachment_url':'https://jwc.example.edu.cn/missing.pdf','metadata_json':{'attachment_missing':True}},'attachment_missing'),
 ({'scope_type':'college','college_id':None},'scope_unclear'),
])
def test_policy_gate_fails_closed(svc,db,changes,reason):
 result=analyze(svc,db,policy(db,**changes))
 assert result['automatic_relations']==0, result
 assert any(reason in s for s in result['blocking_reasons']),result
 assert db.scalar(select(func.count()).select_from(CompetitionPolicyRecognition))==0

@pytest.mark.parametrize('title,dimension',[
 ('示例大学竞赛奖励办法','award_recognition'),('示例大学综合测评竞赛加分目录','comprehensive_evaluation_recognition'),('示例大学创新学分竞赛认定目录','innovation_credit_recognition'),('示例大学学科竞赛认定目录','policy_recognition')])
def test_each_recognition_dimension(svc,db,title,dimension):
 result=analyze(svc,db,policy(db,title=title))
 assert result['automatic_relations']==2,result
 assert dimension in {x.usage_type for x in db.scalars(select(CompetitionPolicyRecognition))}

def test_unknown_name_needs_human_and_has_full_candidate_schema(svc,db):
 result=analyze(svc,db,policy(db,content_text='本办法自2026年1月1日起施行，适用于本科学生的竞赛认定。\n1. 神秘未知大学生竞赛'))
 assert result['automatic_relations']==0
 assert result['requires_human_confirmation']
 e=result['entries'][0]
 assert all(k in e for k in ['school_id','policy_document_id','raw_competition_name','normalized_name','recognition_type','effective_from','effective_to','source_title','source_url','publisher','published_at','match_status','match_confidence','matched_competition_id','match_reason'])

def test_new_policy_conflict_disables_stale_auto_relation(svc,db):
 old=policy(db)
 assert analyze(svc,db,old)['automatic_relations']==2
 db.commit()
 new=policy(db,title='示例大学2026年修订推免竞赛目录',source_url='https://jwc.example.edu.cn/policy/revision.html',published_at=datetime(2026,9,1,tzinfo=timezone.utc),content_text='本竞赛目录适用于全校本科学生推免加分，自2026年9月1日起实施。\n1. 全国大学生电子设计竞赛')
 result=analyze(svc,db,new)
 assert result['automatic_relations']==0 and result['conflicts']
 assert not db.get(PolicyDocument,old).is_current
 from app.services.user_facing_data_policy import UserFacingDataPolicy
 assert all(not UserFacingDataPolicy.recognition_allowed(x) for x in db.scalars(select(CompetitionPolicyRecognition)))

def test_no_unreviewed_competition_mutation_laundered(svc,db):
 identity=policy(db);db.get(Competition,1).frequency='未经审核的修改'
 from app.database.review_guard import UnreviewedFactWrite
 with pytest.raises(UnreviewedFactWrite):analyze(svc,db,identity)


def test_high_risk_classification_reaches_field_risk(svc,db):
 row=source_candidate(db,'竞赛报名延期通知',{'frequency':'每年举办'})
 svc.DocumentPolicyService.classify_candidate(db,row.id,admin=db.get(User,1))
 from app.services.field_review_service import FieldReviewService
 result=FieldReviewService.detail(db,row.id)
 assert result['document_classification']['document_type']=='deadline_extension'
 assert result['risk_level']=='HIGH_RISK'

def test_manual_match_confirmation_retains_document_safety_gates(svc,db):
 identity=policy(db,content_text='本办法适用于全校本科学生，自2026年1月1日起施行，以下竞赛列入推免加分目录。\n1. 全国大学生数学建模竞赛校级赛道')
 first=analyze(svc,db,identity);assert first['automatic_relations']==0
 raw=first['entries'][0]['raw_competition_name']
 second=svc.PolicyAutomationService.confirm_match(db,identity,raw,1,'已确认该文件所列范围确实对应本项赛事',admin=db.get(User,1),now=NOW)
 assert second['automatic_relations']==0 and second['human_confirmed_relations']==1
 assert second['entries'][0]['match_reason']=='human_confirmed'
 assert db.scalar(select(AdminAuditLog).where(AdminAuditLog.action=='policy_match_confirmed')) is not None


def test_match_confirmation_does_not_override_expiry(svc,db):
 identity=policy(db,content_text='本办法适用于全校本科学生，自2024年1月1日起施行，以下竞赛列入推免加分目录。\n1. 全国大学生数学建模竞赛校级赛道',effective_until=datetime(2025,1,1,tzinfo=timezone.utc))
 first=analyze(svc,db,identity);raw=first['entries'][0]['raw_competition_name']
 second=svc.PolicyAutomationService.confirm_match(db,identity,raw,1,'核对名称',admin=db.get(User,1),now=NOW)
 assert second['automatic_relations']==0
 assert any('expired' in reason for reason in second['blocking_reasons'])


def test_explicit_supersession_requires_cancellation_sentence_near_old_title(svc,db):
 old=policy(db);analyze(svc,db,old);db.commit()
 title=db.get(PolicyDocument,old).title
 new=policy(db,title='示例大学2026年推免竞赛目录',source_url='https://jwc.example.edu.cn/new-policy',published_at=datetime(2026,9,1,tzinfo=timezone.utc),content_text=f'本办法适用于本科学生，自2026年9月1日起实施。参考文件《{title}》。以下名单为现行目录。此前不相关的奖学金办法同时废止。\n1. 全国大学生电子设计竞赛')
 result=analyze(svc,db,new)
 assert result['automatic_relations']==0 and result['conflicts']

def test_competition_name_does_not_establish_student_scope(svc,db):
 identity=policy(db,content_text='本竞赛目录自2026年1月1日起施行，列入以下竞赛可获得推免加分，适用范围详见未提供的附件。\n1. 全国大学生数学建模竞赛')
 result=analyze(svc,db,identity)
 assert result['automatic_relations']==0
 assert any('student_scope_unclear' in x for x in result['blocking_reasons'])


def test_content_reanalysis_retires_removed_relations(svc,db):
 identity=policy(db);assert analyze(svc,db,identity)['automatic_relations']==2;db.commit()
 with Session(db.get_bind()) as s:
  p=s.get(PolicyDocument,identity);p.content_text='本竞赛目录自2026年1月1日起施行，适用于全校本科学生推免加分。\n1. 全国大学生电子设计竞赛';s.commit()
 db.expire_all()
 result=analyze(svc,db,identity);assert result['automatic_relations']==1
 from app.services.user_facing_data_policy import UserFacingDataPolicy
 old=list(db.scalars(select(CompetitionPolicyRecognition).where(CompetitionPolicyRecognition.competition_id==1)))
 assert old and all(not UserFacingDataPolicy.recognition_allowed(x) for x in old)


def test_superseded_legacy_policy_is_never_public():
 from types import SimpleNamespace
 from app.services.user_facing_data_policy import UserFacingDataPolicy
 p=SimpleNamespace(is_verified=True,is_current=False,is_demo=False,verification_status='verified_official',metadata_json={'superseded_by':2})
 r=SimpleNamespace(policy_document=p,is_demo=False,recognition_status='recognized',needs_manual_review=False)
 assert UserFacingDataPolicy.recognition_allowed(r) is False
@pytest.mark.parametrize('status',['pending_verification','reviewing','uncertain','insufficient_evidence','candidate','unverified'])
def test_untrusted_verification_status_cannot_auto_promote(svc,db,status):
 result=analyze(svc,db,policy(db,verification_status=status))
 assert result['automatic_relations']==0


def test_failed_attachment_cannot_hide_behind_parser_name(svc,db):
 from app.models import PolicyAttachment
 identity=policy(db,attachment_url='https://jwc.example.edu.cn/p.pdf',parser_type='pymupdf')
 with Session(db.get_bind()) as s:
  s.add(PolicyAttachment(policy_document_id=identity,source_url='https://jwc.example.edu.cn/p.pdf',parse_status='failed',error_message='cannot parse'));s.commit()
 result=analyze(svc,db,identity)
 assert result['automatic_relations']==0 and any('attachment' in r for r in result['blocking_reasons'])


def test_separate_benefit_sections_not_cross_multiplied(svc,db):
 result=analyze(svc,db,policy(db,title='示例大学竞赛奖励与推免加分办法',content_text='本办法自2026年1月1日起施行，适用于全校本科学生。\n一、仅提供奖金奖励的赛事\n1. 全国大学生数学建模竞赛\n二、仅计入推免加分的赛事\n1. 全国大学生电子设计竞赛'))
 rows=list(db.scalars(select(CompetitionPolicyRecognition)))
 assert not any(r.competition_id==1 and r.usage_type=='postgraduate_recommendation_recognition' for r in rows)
 assert not any(r.competition_id==2 and r.usage_type=='award_recognition' for r in rows)


def test_college_only_body_cannot_become_university_scope(svc,db):
 result=analyze(svc,db,policy(db,content_text='本办法自2026年1月1日起施行，仅适用于新闻学院本科学生，以下竞赛属于推免加分目录。\n1. 全国大学生数学建模竞赛'))
 assert result['automatic_relations']==0
 assert any('scope_unclear' in r for r in result['blocking_reasons'])


def test_renamed_explicit_successor_disables_old(svc,db):
 old=policy(db);analyze(svc,db,old);db.commit();oldtitle=db.get(PolicyDocument,old).title
 new=policy(db,title='示例大学推荐免试竞赛加分办法',source_url='https://jwc.example.edu.cn/successor',published_at=datetime(2026,9,1,tzinfo=timezone.utc),content_text=f'本办法适用于全校本科学生，自2026年9月1日起施行。同时废止《{oldtitle}》。\n1. 全国大学生电子设计竞赛')
 result=analyze(svc,db,new)
 assert old in result['superseded_policy_ids'] or result['conflicts']
 assert not db.get(PolicyDocument,old).is_current
@pytest.mark.parametrize('path,method',[
 ('/api/admin/document-policy','get'),('/api/admin/document-policy/policies','get'),('/api/admin/document-policy/replay-classification','post'),('/api/admin/document-policy/policies/1/analyze','post'),('/api/admin/document-policy/1/classification','put')])
def test_document_policy_http_routes_require_admin(db,path,method):
 from fastapi import FastAPI
 from fastapi.testclient import TestClient
 from app.api.deps import get_db
 from app.api.routes.document_policy import router
 from app.core.config import get_settings
 from app.core.security import create_token
 # Mount prefix exactly as production.
 app=FastAPI();app.include_router(router,prefix='/api');app.dependency_overrides[get_db]=lambda:db
 with TestClient(app) as client:
  request=getattr(client,method)
  kwargs={} if method=='get' else {'json':{}}
  assert request(path,**kwargs).status_code in {401,403}
  client.headers['Authorization']='Bearer '+create_token(2,get_settings().app_secret)
  assert request(path,**kwargs).status_code==403


def test_expiry_reopens_previously_resolved_policy_match(svc,db):
 identity=policy(db,content_text='本办法适用于全校本科学生，自2026年1月1日起施行，以下竞赛列入推免加分目录。\n1. 全国大学生数学建模竞赛校级赛道')
 first=analyze(svc,db,identity);raw=first['entries'][0]['raw_competition_name']
 svc.PolicyAutomationService.confirm_match(db,identity,raw,1,'已核对名称范围',admin=db.get(User,1),now=NOW)
 row=db.scalar(select(ReviewQueue).where(ReviewQueue.item_type=='policy_match'))
 assert row.status=='resolved_automatically'
 svc.PolicyAutomationService.analyze(db,identity,admin=db.get(User,1),now=datetime(2027,1,1,tzinfo=timezone.utc))
 assert row.status=='pending'


def test_info_routing_recomputes_after_new_fact_is_added(svc,db):
 row=source_candidate(db,'数学建模竞赛圆满结束')
 assert row.status=='informational'
 doc=json.loads(row.raw_value)
 doc['proposals']=[{'id':'new','field_name':'frequency','candidate_value':'每年举办','source':{'source_title':'数学建模竞赛延期通知','source_url':'https://jwc.example.edu.cn/new'}}]
 row.raw_value=json.dumps(doc,ensure_ascii=False)
 result=svc.DocumentPolicyService.classify_candidate(db,row.id,admin=db.get(User,1))
 assert row.status=='pending' and not result['classification']['informational_only']

def test_formal_tabular_attachment_does_not_require_prose_keyword_in_each_row(svc,db):
 identity=policy(db,title='示例大学本科生学科竞赛认定目录',content_text='序号\t竞赛名称\t分类\n1\t全国大学生数学建模竞赛\tA类\n2\t全国大学生电子设计竞赛\tA类')
 result=analyze(svc,db,identity)
 assert result['automatic_relations']==2,result

@pytest.mark.parametrize('body',[
 '本办法自2026年1月1日起施行，适用于全校本科学生。\n一、奖金奖励赛事目录\n1. 全国大学生数学建模竞赛\n二、推免加分赛事目录\n1. 全国大学生电子设计竞赛',
 '本办法自2026年1月1日起施行，适用于全校本科学生。\n竞赛名称\t用途\n全国大学生数学建模竞赛\t奖金奖励\n全国大学生电子设计竞赛\t推免加分'])
def test_benefit_context_binds_each_entry_without_exclusive_marker(svc,db,body):
 result=analyze(svc,db,policy(db,title='示例大学竞赛奖励与推免加分办法',content_text=body))
 rows=list(db.scalars(select(CompetitionPolicyRecognition)))
 assert not any(r.competition_id==1 and r.usage_type=='postgraduate_recommendation_recognition' for r in rows)
 assert not any(r.competition_id==2 and r.usage_type=='award_recognition' for r in rows)
 assert result['automatic_relations']==2,result


def test_changed_body_cannot_reuse_automation_student_scope(svc,db):
 identity=policy(db);assert analyze(svc,db,identity)['automatic_relations']==2;db.commit()
 with Session(db.get_bind()) as s:
  p=s.get(PolicyDocument,identity);p.content_text='本办法自2026年1月1日起施行，仅适用于研究生，本科学生不适用。以下竞赛计入推免加分目录。\n1. 全国大学生数学建模竞赛';s.commit()
 db.expire_all();result=analyze(svc,db,identity)
 assert not result['automatic_relations'] or db.get(PolicyDocument,identity).metadata_json['relation_scope']['student_scope']=='postgraduate'


def test_major_only_body_cannot_become_university_scope(svc,db):
 result=analyze(svc,db,policy(db,content_text='本办法自2026年1月1日起施行，仅适用于计算机科学与技术专业本科学生，以下竞赛属于推免加分目录。\n1. 全国大学生数学建模竞赛'))
 assert result['automatic_relations']==0
 assert any('scope_unclear' in r for r in result['blocking_reasons'])


@pytest.mark.parametrize('negation',['不废止','尚未废止','暂不废止','未替代'])
def test_negated_cancellation_cannot_supersede(svc,db,negation):
 old=policy(db);analyze(svc,db,old);db.commit();oldtitle=db.get(PolicyDocument,old).title
 new=policy(db,title='示例大学2026年推免竞赛目录',source_url='https://jwc.example.edu.cn/negation',published_at=datetime(2026,9,1,tzinfo=timezone.utc),content_text=f'本办法适用于全校本科学生，自2026年9月1日起施行。{negation}《{oldtitle}》。\n1. 全国大学生电子设计竞赛')
 result=analyze(svc,db,new)
 assert result['automatic_relations']==0 and result['conflicts']
 assert not result['superseded_policy_ids']


def test_saved_complete_attachment_replaces_truncated_cache(svc,db,tmp_path,monkeypatch):
 import app.services.policy_automation_service as automation
 monkeypatch.setattr(automation,'RAW_ROOT',tmp_path,raising=False)
 source=tmp_path/'catalog.txt';source.write_text('序号\t竞赛名称\t分类\n1\t全国大学生数学建模竞赛\tA类\n2\t全国大学生电子设计竞赛\tA类',encoding='utf-8')
 identity=policy(db,title='示例大学本科生学科竞赛认定目录',content_text='序号\t竞赛名称\t分类\n1\t全国大学生数学建模竞赛\tA类',metadata_json={'local_path':str(source)})
 result=analyze(svc,db,identity)
 assert result['automatic_relations']==2,result
 assert result['attachment_replay']['file_sha256']
 assert result['attachment_replay']['entry_count']==2


def test_attachment_path_cannot_escape_raw_directory(svc,db,tmp_path,monkeypatch):
 import app.services.policy_automation_service as automation
 monkeypatch.setattr(automation,'RAW_ROOT',tmp_path/'raw',raising=False)
 source=tmp_path/'elsewhere.txt';source.write_text('private',encoding='utf-8')
 result=analyze(svc,db,policy(db,metadata_json={'local_path':str(source)}))
 assert result['automatic_relations']==0
 assert any('attachment_unavailable' in r for r in result['blocking_reasons'])


def test_ordinary_school_notice_keeps_typed_participation_evidence_without_recognition(svc,db):
 row=source_candidate(db,'关于组织数学建模竞赛报名通知')
 doc=json.loads(row.raw_value);doc['collection_context']={'kind':'school_mapping','source_title':'关于组织数学建模竞赛报名通知','source_url':'https://jwc.example.edu.cn/news'}
 doc['university_id']=1;row.university_id=1;row.raw_value=json.dumps(doc,ensure_ascii=False)
 result=svc.DocumentPolicyService.classify_candidate(db,row.id,admin=db.get(User,1))
 # Organization + registration is now explicitly ambiguous. An actual human
 # type correction, rather than the rule score, authorizes participation proof.
 result=svc.DocumentPolicyService.correct_classification(db,row.id,'registration_notice','人工核对为报名通知',admin=db.get(User,1))
 evidence=json.loads(row.raw_value)['participation_evidence']
 assert evidence['relation_type']=='participation_evidence' and evidence['school_id']==1
 assert evidence['source_url']=='https://jwc.example.edu.cn/news'
 assert result['relation_evidence']==evidence
 assert db.scalar(select(func.count()).select_from(CompetitionPolicyRecognition))==0
 assert row.status=='pending'


def test_changed_source_invalidates_saved_classification_and_human_correction(svc,db):
 row=source_candidate(db,'数学建模竞赛圆满结束')
 svc.DocumentPolicyService.correct_classification(db,row.id,'competition_intro','已核对来源',admin=db.get(User,1))
 doc=json.loads(row.raw_value);doc['collection_context']={'source_title':'数学建模竞赛报名延期通知','source_url':'https://jwc.example.edu.cn/changed'}
 row.raw_value=json.dumps(doc,ensure_ascii=False)
 result=svc.DocumentPolicyService.classify_candidate(db,row.id,admin=db.get(User,1))
 assert result['classification']['risk_level']=='HIGH_RISK' and row.status=='pending'


def test_public_automatic_relation_requires_current_evidence_hash(svc,db):
 identity=policy(db);analyze(svc,db,identity);db.commit()
 with Session(db.get_bind()) as s:
  p=s.get(PolicyDocument,identity);p.content_text='正文已更新，原名单已经移除。';s.commit()
 db.expire_all()
 from app.services.user_facing_data_policy import UserFacingDataPolicy
 assert all(not UserFacingDataPolicy.recognition_allowed(r) for r in db.scalars(select(CompetitionPolicyRecognition)))


def test_admin_list_does_not_present_conflicting_old_relations_as_current(svc,db):
 old=policy(db);analyze(svc,db,old);db.commit()
 new=policy(db,title='示例大学2026年修订推免竞赛目录',source_url='https://jwc.example.edu.cn/revision-view',published_at=datetime(2026,9,1,tzinfo=timezone.utc),content_text='本竞赛目录适用于全校本科学生推免加分，自2026年9月1日起实施。\n1. 全国大学生电子设计竞赛')
 analyze(svc,db,new)
 item=next(p for p in svc.PolicyAutomationService.list_policies(db)['items'] if p['id']==old)
 assert item['analysis']['automatic_relations']==0
 assert item['analysis']['requires_human_confirmation'] is True
 assert all(e['blocking_reasons'] for e in item['analysis']['entries'])
