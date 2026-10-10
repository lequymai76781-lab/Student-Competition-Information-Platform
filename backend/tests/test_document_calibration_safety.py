import json
import pytest
from sqlalchemy import select, func

from app.services.source_document_classifier import classify_document
from app.services.document_policy_service import classification_for, _source_fingerprint


@pytest.mark.parametrize("source,expected", [
    ({"title": "关于组织2030年全国大学生电子设计竞赛的通知"}, "organization_notice"),
    ({"title": "关于举办大学生创业竞赛校内初赛的通知"}, "selection_notice"),
    ({"title": "科技竞赛暨校内赛启动报名通知"}, "selection_notice"),
    ({"title": "教育部关于举办创新大赛的通知", "publisher": "某大学（转载教育部）"}, "repost"),
    ({"title": "某竞赛报名通知", "publisher": "某学院（转载竞赛组委会）"}, "repost"),
    ({"title": "学科竞赛", "source_url": "https://school.test/contest/list.htm", "content_preview": "首页 当前位置 学科竞赛 获奖名单 下一页 每页 总共"}, "other"),
    ({"title": "数学建模暑期集训圆满落幕"}, "other"),
    ({"title": "关于数学建模竞赛实验班报名选拔的通知"}, "other"),
    ({"title": "关于开展劳动周活动的通知"}, "other"),
    ({"title": "2030 WORLD PROGRAMMING CONTEST — FACT SHEET"}, "competition_intro"),
    ({"title": "World Competition — About the competition"}, "competition_intro"),
])
def test_generalized_repairs_without_id_specific_rules(source, expected):
    assert classify_document(source)["primary_type"] == expected


@pytest.mark.parametrize("title", ["蓝桥杯报名通知", "蓝桥杯获奖名单公示", "本科生推免竞赛目录", "大学生竞赛简介", "科技竞赛圆满结束"])
def test_unvalidated_rule_scores_do_not_authorize_automatic_processing(title):
    result = classify_document({"title": title})
    assert result["classification_status"] == "NEEDS_QUICK_CONFIRM"
    assert result["requires_human_confirmation"]
    assert not result["informational_only"]
    assert result["auto_threshold"] is None


def test_ambiguous_and_high_risk_require_manual_work():
    for title in ["竞赛报名延期通知", "竞赛成绩更正通知", "校赛报名及获奖结果通知", "校园信息"]:
        assert classify_document({"title": title})["classification_status"] == "NEEDS_MANUAL_CLASSIFICATION"
    value = classify_document({"title": "赛事介绍", "content_preview": "更正如下：报名截止日期调整。"})
    assert value["risk_level"] == "HIGH_RISK"
    assert "correction_notice" in value["secondary_types"]
    assert not value["informational_only"]


def test_metadata_and_navigation_heuristics_do_not_hide_valid_article():
    assert classify_document({"title": "某竞赛获奖名单公示", "source_url": "https://example.test/list.htm", "content_preview": "首页 下一页"})["primary_type"] == "publicity_notice"
    assert classify_document({"title": "培训班学员参加竞赛获奖结果"})["primary_type"] == "result_notice"
    assert classify_document({"title": "科研竞赛报名通知", "publisher": "某校教务处"})["primary_type"] == "registration_notice"


def test_old_cached_auto_classification_cannot_bypass_calibration_hold():
    doc = {"schema_version":1,"title":"科技竞赛圆满结束","proposals":[],"collection_context":{}}
    old={"document_type":"completion_news","classification_status":"AUTO_CLASSIFIED","informational_only":True,"rule_version":"document-rules-1.0","source_fingerprint":_source_fingerprint(doc)}
    doc["document_classification"]=old
    result=classification_for(doc)
    assert result["classification_status"]=="NEEDS_QUICK_CONFIRM"
    assert not result["informational_only"]
    old.update(classification_status="HUMAN_CONFIRMED",corrected_at="2026-10-01T00:00:00Z",informational_only=False)
    assert classification_for(doc)["classification_status"]=="HUMAN_CONFIRMED"


def test_default_policy_hold_requires_confirmation_and_preserves_document_validity(test_session):
    from app.models import University, Competition, PolicyDocument, User, CompetitionPolicyRecognition, ReviewQueue
    from app.services.policy_automation_service import PolicyAutomationService
    from datetime import datetime,timezone
    db=test_session
    school=db.scalar(select(University));school.official_domain="example.edu.cn"
    comp=db.scalar(select(Competition));comp.name="全国大学生数学建模竞赛"
    admin=User(username="calibration-admin",email="calibration@unit.test",hashed_password="unused",is_active=True,is_admin=True);db.add(admin)
    now=datetime(2026,10,1,tzinfo=timezone.utc)
    doc=PolicyDocument(university_id=school.id,title="某大学本科生竞赛认定目录",publisher="某大学教务处",source_url="https://example.edu.cn/policy",
        content_text="本办法适用于全校本科学生，自2026年1月1日起生效，下列竞赛列入本校学科竞赛认定目录。\n1. 全国大学生数学建模竞赛",effective_from=datetime(2026,1,1,tzinfo=timezone.utc),
        is_verified=True,is_current=True,verification_status="official_domain_verified",scope_type="university",parser_type="text",metadata_json={})
    db.add(doc);db.commit()
    result=PolicyAutomationService.analyze(db,doc.id,admin=admin,now=now)
    assert result["automatic_relations"]==0
    assert any("calibration" in r for r in result["blocking_reasons"])
    assert db.scalar(select(func.count()).select_from(CompetitionPolicyRecognition))==0
    assert doc.is_current and doc.verification_status=="official_domain_verified"
    queued=list(db.scalars(select(ReviewQueue).where(ReviewQueue.item_type=="policy_match")))
    assert queued and all(json.loads(r.raw_value)["relation_status"]=="NEEDS_QUICK_CONFIRM" for r in queued)


def test_authorization_hold_does_not_invalidate_historical_evidence(test_session, monkeypatch):
    from datetime import datetime,timezone
    from app.models import University, Competition, PolicyDocument, User, CompetitionPolicyRecognition
    from app.services.policy_automation_service import PolicyAutomationService, _analysis_item
    from app.services.source_document_classifier import DOCUMENT_TYPES
    from app.services import document_calibration_policy as calibration
    db=test_session
    school=db.scalar(select(University));school.official_domain="example.edu.cn"
    comp=db.scalar(select(Competition));comp.name="全国大学生数学建模竞赛"
    admin=User(username="historical-admin",email="history@unit.test",hashed_password="unused",is_active=True,is_admin=True);db.add(admin)
    now=datetime(2026,10,1,tzinfo=timezone.utc)
    doc=PolicyDocument(university_id=school.id,title="某大学本科生竞赛认定目录",publisher="某大学教务处",source_url="https://example.edu.cn/policy",
        content_text="本办法适用于全校本科学生，自2026年1月1日起生效，下列竞赛列入本校学科竞赛认定目录。\n1. 全国大学生数学建模竞赛",
        effective_from=datetime(2026,1,1,tzinfo=timezone.utc),is_verified=True,is_current=True,verification_status="official_domain_verified",scope_type="university",parser_type="text",metadata_json={})
    db.add(doc);db.commit()
    with monkeypatch.context() as historical:
        historical.setattr(calibration,"AUTO_THRESHOLDS",{kind:.90 for kind in DOCUMENT_TYPES})
        historical.setattr(calibration,"POLICY_AUTO_ENABLED",True)
        assert PolicyAutomationService.analyze(db,doc.id,admin=admin,now=now)["automatic_relations"]==1
    stored=db.scalar(select(CompetitionPolicyRecognition))
    assert not stored.needs_manual_review
    cached=_analysis_item(db,doc)["analysis"]
    assert cached["automatic_relations"]==0 and cached["historical_automatic_relations"]==1
    assert cached["entries"][0]["relation_status"]=="NEEDS_QUICK_CONFIRM"
    assert doc.metadata_json["policy_automation"]["automatic_relations"]==1
    result=PolicyAutomationService.analyze(db,doc.id,admin=admin,now=now)
    assert result["automatic_relations"]==0
    assert not stored.needs_manual_review and doc.is_current
    assert db.scalar(select(func.count()).select_from(CompetitionPolicyRecognition))==1


def test_old_human_news_label_survives_but_unverified_archival_is_reopened(test_session):
    from app.services.competition_field_ingestion_service import CompetitionFieldIngestionService
    from app.services.document_policy_service import DocumentPolicyService
    from app.models import Competition, User
    db=test_session; comp=db.scalar(select(Competition))
    admin=User(username="routing-admin",email="routing@unit.test",hashed_password="unused",is_active=True,is_admin=True);db.add(admin);db.commit()
    row=CompetitionFieldIngestionService().stage(db,entity_type="competition",title="竞赛介绍",competition_id=comp.id,fields={},
        source={"source_type":"university_notice","source_title":"竞赛介绍","source_url":"https://example.test/intro"},raw={"title":"竞赛介绍"})
    db.commit()
    DocumentPolicyService.correct_classification(db,row.id,"competition_intro","人工只确认主类",admin=admin)
    doc=json.loads(row.raw_value);doc["document_classification"]["informational_only"]=True
    row.raw_value=json.dumps(doc,ensure_ascii=False);row.status="informational";db.commit()
    DocumentPolicyService.classify_candidate(db,row.id,admin=admin)
    assert row.status=="pending"
    saved=json.loads(row.raw_value)["document_classification"]
    assert saved["classification_status"]=="HUMAN_CONFIRMED" and saved["document_type"]=="competition_intro"
    assert not saved["informational_only"]


def test_calibration_hold_does_not_invent_conflict_for_explicit_policy_replacement(test_session):
    from datetime import datetime,timezone
    from app.models import University,Competition,PolicyDocument,User
    from app.services.policy_automation_service import PolicyAutomationService
    db=test_session;school=db.scalar(select(University));school.official_domain="example.edu.cn"
    comp=db.scalar(select(Competition));comp.name="全国大学生数学建模竞赛"
    admin=User(username="version-admin",email="version@unit.test",hashed_password="unused",is_active=True,is_admin=True);db.add(admin)
    base=dict(university_id=school.id,publisher="某大学教务处",source_url="https://example.edu.cn/policy",is_verified=True,is_current=True,
        verification_status="official_domain_verified",scope_type="university",parser_type="text",metadata_json={})
    old=PolicyDocument(**base,title="某大学2025年本科生竞赛认定目录",effective_from=datetime(2025,1,1,tzinfo=timezone.utc),published_at=datetime(2025,1,1,tzinfo=timezone.utc),
        content_text="本办法适用于全校本科学生，自2025年1月1日起生效，下列竞赛列入本校学科竞赛认定目录。\n1. 全国大学生数学建模竞赛")
    new=PolicyDocument(**base,title="某大学2026年本科生竞赛认定目录",effective_from=datetime(2026,1,1,tzinfo=timezone.utc),published_at=datetime(2026,1,1,tzinfo=timezone.utc),
        content_text="本办法适用于全校本科学生，自2026年1月1日起生效，下列竞赛列入本校学科竞赛认定目录。\n1. 全国大学生数学建模竞赛\n《某大学2025年本科生竞赛认定目录》同时废止。")
    db.add_all([old,new]);db.commit()
    result=PolicyAutomationService.analyze(db,new.id,admin=admin,now=datetime(2026,10,1,tzinfo=timezone.utc))
    assert not result["conflicts"]
    assert not any("policy_version_conflict" in value for value in result["blocking_reasons"])
    assert result["automatic_relations"]==0 and new.is_current
    assert old.id in result["superseded_policy_ids"]
