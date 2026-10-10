"""Integration safety: type decisions never approve facts or policy relations."""
import json
from datetime import datetime, timezone
import pytest
from sqlalchemy import select, func
from app.models import User, Competition, University, PolicyDocument, CompetitionPolicyRecognition, AdminAuditLog
from app.services.document_policy_service import DocumentPolicyService, classification_for, _source_fingerprint
from app.services.competition_field_ingestion_service import CompetitionFieldIngestionService


def make_candidate(db, title, fields=None, raw=None):
    comp = db.scalar(select(Competition))
    row = CompetitionFieldIngestionService().stage(
        db, entity_type="competition", title=title, competition_id=comp.id, fields=fields or {},
        source={"source_type": "university_notice", "source_title": title, "source_url": "https://example.edu.cn/article"},
        raw=raw or {"title": title})
    db.commit()
    return row, comp


def admin(db):
    value = User(username="hierarchy-admin",email="hierarchy@unit.test",hashed_password="unused",is_active=True,is_admin=True)
    db.add(value);db.commit()
    return value


def test_same_functional_types_auto_classified_without_approving_fields(test_session):
    db=test_session; actor=admin(db)
    row,comp=make_candidate(db,"关于组织大学生科技竞赛校内选拔报名的通知",{"frequency":"每年举办"})
    old=comp.frequency
    result=DocumentPolicyService.classify_candidate(db,row.id,admin=actor)
    c=result["classification"]
    assert c["primary_type"]=="participation"
    assert c["classification_status"]=="AUTO_CLASSIFIED"
    assert c["requires_human_confirmation"] is False
    assert row.status=="pending" and comp.frequency==old
    assert len(json.loads(row.raw_value)["proposals"])==1
    assert db.scalar(select(func.count()).select_from(CompetitionPolicyRecognition))==0


def test_seven_primary_correction_is_audited_and_survives_replay(test_session):
    db=test_session;actor=admin(db);row,_=make_candidate(db,"普通材料")
    result=DocumentPolicyService.correct_classification(db,row.id,"participation","人工已查看来源，属于参赛事项",admin=actor)
    assert result["classification"]["primary_type"]=="participation"
    assert result["classification"]["classification_status"]=="HUMAN_CONFIRMED"
    assert row.status=="pending"
    again=DocumentPolicyService.classify_candidate(db,row.id,admin=actor)
    assert again["classification"]["primary_type"]=="participation"
    assert db.scalar(select(AdminAuditLog).where(AdminAuditLog.action=="document_classification_corrected")).after["final_type"]=="participation"


def test_old_human_fine_label_is_preserved_and_upgraded_readonly():
    doc={"schema_version":1,"title":"赛事介绍","proposals":[],"collection_context":{}}
    saved={"document_type":"selection_notice","primary_type":"selection_notice","classification_status":"HUMAN_CONFIRMED",
           "corrected_at":"2026-10-01T00:00:00Z","classification_reason":"原人工决定","informational_only":False,
           "source_fingerprint":_source_fingerprint(doc)}
    doc["document_classification"]=saved
    original=json.dumps(doc,sort_keys=True)
    c=classification_for(doc)
    assert c["primary_type"]=="participation"
    assert c["document_type"]=="selection_notice" and c["secondary_type"]=="selection"
    assert c["classification_reason"]=="原人工决定"
    assert c["classification_status"]=="HUMAN_CONFIRMED"
    assert json.dumps(doc,sort_keys=True)==original


def test_human_information_correction_cannot_hide_update(test_session):
    db=test_session;actor=admin(db)
    row,_=make_candidate(db,"大学生竞赛介绍",raw={"title":"大学生竞赛介绍","content_text":"现更正：报名截止日期延长至下月，请以本通知为准。"})
    c=DocumentPolicyService.correct_classification(db,row.id,"information","仅确认页面为赛事介绍",admin=actor)["classification"]
    assert c["primary_type"]=="information"
    assert c["risk_level"]=="HIGH_RISK" and not c["informational_only"]
    assert row.status=="pending"


def test_old_saved_information_flag_without_body_cannot_archive():
    doc={"schema_version":1,"title":"赛事介绍","proposals":[],"collection_context":{}}
    doc["document_classification"]={"document_type":"competition_intro","primary_type":"competition_intro",
        "classification_status":"HUMAN_CONFIRMED","corrected_at":"2026-10-01T00:00:00Z",
        "informational_only":True,"source_fingerprint":_source_fingerprint(doc)}
    c=classification_for(doc)
    assert c["primary_type"]=="information" and not c["informational_only"]


def test_policy_binary_gate_cannot_be_bypassed_by_fine_type_or_global_flag(test_session,monkeypatch):
    from app.services.policy_automation_service import _gate
    from app.services import document_calibration_policy as permissions
    db=test_session;school=db.scalar(select(University));school.official_domain="example.edu.cn"
    document=PolicyDocument(university_id=school.id,title="某大学竞赛认定目录",publisher="某大学教务处",
        source_url="https://example.edu.cn/policy",content_text="本办法适用于全校本科学生，自2026年1月1日起生效，以下竞赛列入认定目录。",
        effective_from=datetime(2026,1,1,tzinfo=timezone.utc),is_verified=True,is_current=True,
        verification_status="official_domain_verified",scope_type="university",parser_type="text",metadata_json={})
    db.add(document);db.flush()
    monkeypatch.setattr(permissions,"POLICY_AUTO_ENABLED",True)
    classification={"document_type":"policy_recognition_document","primary_type":"policy","risk_level":"NORMAL",
                    "requires_human_confirmation":False,"is_policy":False,"policy_confidence":0.3,
                    "policy_assessment":{"is_policy":False,"policy_confidence":0.3,"policy_status":"NEEDS_POLICY_CONFIRM"}}
    reasons=_gate(db,document,classification,datetime(2026,10,1,tzinfo=timezone.utc))
    assert any(value.startswith("policy_safety:") for value in reasons)
    classification["is_policy"]=True;classification["policy_assessment"]["is_policy"]=True
    assert any(value.startswith("policy_safety:") for value in _gate(db,document,classification,datetime(2026,10,1,tzinfo=timezone.utc)))


def test_policy_uncertainty_does_not_invalidate_historical_policy():
    from app.services.policy_automation_service import _evidence_blockers
    assert _evidence_blockers(["policy_safety: 缺少独立安全判定","policy_calibration: 尚未授权"])==[]
    assert _evidence_blockers(["expired: 政策失效"])==["expired: 政策失效"]


def test_repost_evidence_never_becomes_school_participation_authority(test_session):
    db=test_session;actor=admin(db);row,comp=make_candidate(db,"转发：全国大学生竞赛报名通知")
    school=db.scalar(select(University));row.university_id=school.id
    payload=json.loads(row.raw_value);payload["collection_context"]={**payload.get("collection_context",{}),"kind":"school_mapping"}
    row.raw_value=json.dumps(payload,ensure_ascii=False);db.commit()
    result=DocumentPolicyService.classify_candidate(db,row.id,admin=actor)
    assert result["classification"]["primary_type"]=="repost"
    assert result["relation_evidence"] is None
    assert db.scalar(select(func.count()).select_from(CompetitionPolicyRecognition))==0

@pytest.mark.parametrize("title", ["大学生竞赛获奖名单公示", "大学生竞赛简介", "转发：大学生竞赛报名通知"])
def test_unvalidated_primary_groups_remain_confirmation_only(title):
    # Real Golden Set had 2/5 result, 10/13 information, 3/4 repost automatic
    # correctness. A high rule strength must not bypass that observed failure.
    value=classification_for({"schema_version":1,"title":title,"proposals":[],"collection_context":{}})
    assert value["classification_status"]=="NEEDS_QUICK_CONFIRM"
    assert not value["informational_only"]


def test_uncertain_new_policy_cannot_supersede_or_invalidate_old_policy(test_session):
    from app.services.policy_automation_service import PolicyAutomationService
    db=test_session;actor=admin(db);school=db.scalar(select(University));school.official_domain="example.edu.cn"
    comp=db.scalar(select(Competition));comp.name="全国大学生数学建模竞赛"
    common=dict(university_id=school.id,publisher="大学教务处",source_url="https://example.edu.cn/policy",
                is_verified=True,is_current=True,verification_status="verified_official",scope_type="university",
                parser_type="text",metadata_json={"relation_scope":{"student_scope":"undergraduate"}})
    old=PolicyDocument(**common,title="2025年学科竞赛认定目录",
        effective_from=datetime(2025,1,1,tzinfo=timezone.utc),published_at=datetime(2025,1,1,tzinfo=timezone.utc),
        content_text="本办法适用于本科学生，学科竞赛认定目录如下，自2025年1月1日起施行。\\n1. 全国大学生数学建模竞赛".replace("\\n","\n"))
    new=PolicyDocument(**common,title="2026年学科竞赛认定目录",
        effective_from=datetime(2026,1,1,tzinfo=timezone.utc),published_at=datetime(2026,1,1,tzinfo=timezone.utc),
        content_text="现声明《2025年学科竞赛认定目录》废止。学生参与竞赛以当前目录认定为准，相关赛事项目按照列出的等级计入认定结果。\n1. 全国大学生数学建模竞赛")
    db.add_all([old,new]);db.commit()
    result=PolicyAutomationService.analyze(db,new.id,admin=actor,now=datetime(2026,10,1,tzinfo=timezone.utc))
    assert result["classification"]["is_policy"] is False
    assert result["automatic_relations"]==0
    assert result["superseded_policy_ids"]==[]
    assert old.is_current and old.verification_status=="verified_official"
    assert not (old.metadata_json or {}).get("superseded_by")
    assert not (old.metadata_json or {}).get("policy_version_conflict")


def test_participation_explanation_does_not_require_choosing_fine_labels():
    value=classification_for({"schema_version":1,"title":"关于组织科技竞赛校内选拔报名的通知","proposals":[],"collection_context":{}})
    assert value["primary_type"]=="participation" and value["classification_status"]=="AUTO_CLASSIFIED"
    assert "需确认主类型" not in value["classification_reason"]
