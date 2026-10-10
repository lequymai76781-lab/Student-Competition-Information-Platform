"""Relation workflow uses real guarded sessions and isolated in-memory data."""
import importlib
import json
from datetime import datetime
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, func, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.database.base import Base
from app.database.session import SessionLocal
from app.models import (Competition, CompetitionEdition, University, User, ReviewQueue, AdminAuditLog,
    UniversityCompetitionEditionRelation as Relation, PolicyDocument, CompetitionPolicyRecognition as Recognition)
from app.services.mid_scale_ingestion_service import MidScaleIngestionService

@pytest.fixture
def service():
    try:
        return importlib.import_module("app.services.school_relation_review_service").SchoolRelationReviewService
    except ModuleNotFoundError:
        class MissingService:
            def __getattr__(self, name):
                pytest.fail("School relation review service is not implemented")
        return MissingService()

@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as seed:
        seed.add_all([University(id=1,name="测试大学"),University(id=2,name="另一大学"),
            Competition(id=1,name="测试竞赛"),Competition(id=2,name="另一竞赛"),
            CompetitionEdition(id=1,competition_id=1,year=2024),CompetitionEdition(id=2,competition_id=1,year=2025),
            CompetitionEdition(id=3,competition_id=2,year=2025),
            User(id=1,username="admin",email="admin@example.test",hashed_password="fixture",is_admin=True),
            User(id=2,username="user",email="user@example.test",hashed_password="fixture",is_admin=False)])
        seed.commit()
    with SessionLocal(bind=engine) as session:
        yield session
    engine.dispose()

def candidate(db,key="a",*,year=2025,policy=False,deadline=None):
    source=dict(key=key,url=f"https://school.example.test/{key}",title="测试大学竞赛材料",publisher="测试大学教务处",
        source_type="university_policy" if policy else "university_notice",published_at="2025-01-01",
        accessed_at="2026-09-28T00:00:00+08:00",access_status="readable",year=year,
        competition_fields={},edition_fields={},evidence_notes="已读取正文",
        university_notice=dict(notice_type="policy_recognition" if policy else "registration_notice",
            is_formal_recognition=policy,recognition_evidence="目录第1项明确列出测试竞赛" if policy else None,
            school_deadline=deadline))
    row=MidScaleIngestionService.stage_item(db,dict(kind="school_mapping",competition_id=1,competition_name="测试竞赛",
        university_name="测试大学",school_source_name="测试大学教务处",source=source))[0]
    db.commit()
    return row.id

def payload(s,db,id,**kw):
    return dict(preview_token=s.detail(db,id)["preview_token"],note="已逐项核对原文",**kw)
def verify(s,db,id):
    return s.verify_source(db,id,payload(s,db,id),admin=db.get(User,1))
def approve(s,db,id):
    return s.review(db,id,payload(s,db,id,action="approve"),admin=db.get(User,1))
def policy(s,db,id,**kw):
    data=dict(scope_type="university",student_scope="undergraduate",applicability_text="本科学生参加测试竞赛",
        validity_note="仅确认2025历史政策，未核实当前有效",current_validity_confirmed=False,
        effective_from="2025-01-01T00:00:00+08:00",effective_until="2025-12-31T23:59:59+08:00",
        recognition_evidence="目录第1项明确列出测试竞赛")
    data.update(kw)
    return s.prepare(db,id,payload(s,db,id,**data),admin=db.get(User,1))
def count(db,model):
    return db.scalar(select(func.count()).select_from(model))

@pytest.fixture
def relation_http_client(db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.deps import get_db
    from app.api.routes.field_reviews import router
    from app.core.config import get_settings
    from app.core.exceptions import register_exception_handlers
    from app.core.security import create_token
    app = FastAPI()
    app.include_router(router, prefix="/api")
    register_exception_handlers(app)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, headers={"Authorization": "Bearer " + create_token(1, get_settings().app_secret)}) as client:
        yield client

@pytest.mark.parametrize("kind", ["known_notice", "unknown_year_notice", "policy"])
def test_http_prepare_preserves_omitted_identity_fields(service, db, relation_http_client, kind):
    identity = candidate(db, policy=kind == "policy", year=None if kind == "unknown_year_notice" else 2025)
    before = service.detail(db, identity)
    body = dict(preview_token=before["preview_token"], note="HTTP准备只提交需要补充的字段")
    if kind == "unknown_year_notice":
        body.update(year=2025, edition_id=2)
    elif kind == "policy":
        body.update(scope_type="university", student_scope="undergraduate", applicability_text="本科学生参加测试竞赛",
            validity_note="仅确认2025历史政策，未核实当前有效", current_validity_confirmed=False,
            effective_from="2025-01-01T00:00:00+08:00", effective_until="2025-12-31T23:59:59+08:00",
            recognition_evidence="目录第1项明确列出测试竞赛")
    response = relation_http_client.put(f"/api/admin/field-reviews/{identity}/relation/prepare", json=body)
    assert response.status_code == 200, response.text
    result = response.json()["data"]
    assert (result["university_id"], result["competition_id"], result["year"]) == (1, 1, 2025)
    assert "university_id" not in result["prepared"] and "competition_id" not in result["prepared"]
    assert result["prepared"]["revoked"] == before["prepared"]["revoked"]
    if kind != "policy":
        assert result["edition_id"] == 2
        assert "scope_type" not in result["prepared"]
    else:
        assert result["prepared"]["student_scope"] == "undergraduate"
    db.expire_all()
    persisted = service.detail(db, identity)
    assert (persisted["university_id"], persisted["competition_id"]) == (1, 1)
    assert persisted["prepared"] == result["prepared"]
    assert count(db, Relation) == 0 and count(db, PolicyDocument) == 0 and count(db, Recognition) == 0

@pytest.mark.parametrize("field", ["university_id", "competition_id"])
def test_http_prepare_still_rejects_explicit_null_known_identity(service, db, relation_http_client, field):
    identity = candidate(db)
    response = relation_http_client.put(f"/api/admin/field-reviews/{identity}/relation/prepare",
        json=payload(service, db, identity, **{field: None}))
    assert response.status_code == 409, response.text
    assert service.detail(db, identity)[field] == 1

def test_notice_needs_verification_then_writes_only_relation(service,db):
    id=candidate(db)
    with pytest.raises(HTTPException) as exc:
        approve(service,db,id)
    assert exc.value.status_code==409 and count(db,Relation)==0
    assert verify(service,db,id)["source"]["verification_state"]=="VERIFIED"
    assert approve(service,db,id)["status"]=="approved"
    relation=db.scalar(select(Relation))
    assert relation.competition_edition_id==2 and relation.notice_type=="registration_notice" and relation.is_verified
    assert len(relation.metadata_json["review_sources"])==1 and count(db,Recognition)==0
    assert db.get(Competition,1).description is None
    audit=db.scalar(select(AdminAuditLog).where(AdminAuditLog.action=="school_relation_review"))
    assert audit.after["review"]["action"]=="approve"

@pytest.mark.parametrize("action,status",[("reject","rejected"),("defer","deferred")])
def test_reject_or_defer_never_creates_formal_data(service,db,action,status):
    id=candidate(db)
    result=service.review(db,id,payload(service,db,id,action=action),admin=db.get(User,1))
    assert result["status"]==status and count(db,Relation)==0
    if action=="defer":
        verify(service,db,id)
        assert approve(service,db,id)["status"]=="approved"

def test_unknown_year_must_be_prepared_without_switching_competition(service,db):
    id=candidate(db,year=None);verify(service,db,id)
    with pytest.raises(HTTPException): approve(service,db,id)
    with pytest.raises(HTTPException):
        service.prepare(db,id,payload(service,db,id,edition_id=3,year=2025),admin=db.get(User,1))
    result=service.prepare(db,id,payload(service,db,id,edition_id=2,year=2025),admin=db.get(User,1))
    assert result["edition_id"]==2 and result["source"]["verification_state"]=="UNVERIFIED"
    verify(service,db,id);approve(service,db,id)
    assert db.scalar(select(Relation)).competition_edition_id==2

def test_known_identity_and_registration_type_cannot_be_replaced(service,db):
    id=candidate(db)
    for change in [dict(year=2024,edition_id=1),dict(competition_id=2),dict(university_id=2),
                   dict(notice_type="policy_recognition"),dict(scope_type="university",student_scope="all")]:
        with pytest.raises(HTTPException):
            service.prepare(db,id,payload(service,db,id,**change),admin=db.get(User,1))
    assert count(db,PolicyDocument)==0

def test_same_relation_merges_distinct_sources(service,db):
    a,b=candidate(db,"a"),candidate(db,"b")
    verify(service,db,a);approve(service,db,a);db.commit()
    verify(service,db,b);approve(service,db,b)
    assert count(db,Relation)==1
    assert {s["source_url"] for s in db.scalar(select(Relation)).metadata_json["review_sources"]}=={
        "https://school.example.test/a","https://school.example.test/b"}

def test_historical_notice_never_joins_latest_edition(service,db):
    for year in (2024,2025):
        id=candidate(db,str(year),year=year);verify(service,db,id);approve(service,db,id);db.commit()
    assert set(db.scalars(select(Relation.competition_edition_id)))=={1,2}

def test_conflicting_school_deadlines_block_approval(service,db):
    a=candidate(db,"a",deadline="2025-04-01T00:00:00+08:00")
    verify(service,db,a);approve(service,db,a);db.commit()
    b=candidate(db,"b",deadline="2025-04-02T00:00:00+08:00")
    assert "RELATION_CONFLICT" in service.detail(db,b)["flags"]
    verify(service,db,b)
    with pytest.raises(HTTPException): approve(service,db,b)
    assert count(db,Relation)==1

def test_external_relation_change_invalidates_preview(service,db):
    a,b=candidate(db,"a"),candidate(db,"b");verify(service,db,b)
    stale=payload(service,db,b,action="approve")
    verify(service,db,a);approve(service,db,a);db.commit()
    with pytest.raises(HTTPException) as exc:
        service.review(db,b,stale,admin=db.get(User,1))
    assert exc.value.status_code==409 and db.get(ReviewQueue,b).status=="pending"

def test_historical_policy_has_separate_policy_storage(service,db):
    id=candidate(db,policy=True,year=None);policy(service,db,id);verify(service,db,id);approve(service,db,id)
    doc=db.scalar(select(PolicyDocument));recognition=db.scalar(select(Recognition))
    assert count(db,Relation)==0 and count(db,Recognition)==1
    assert doc.is_verified and not doc.is_current and recognition.recognition_status=="historical_recognition"
    assert doc.metadata_json["relation_scope"]["student_scope"]=="undergraduate"
    assert doc.effective_until.year==2025 and "测试竞赛" in recognition.evidence_text

def test_graduate_policy_is_not_general_undergraduate_recognition(service,db):
    id=candidate(db,policy=True)
    policy(service,db,id,student_scope="graduate",effective_from="2020-01-01T00:00:00+08:00",effective_until=None,
        current_validity_confirmed=True,applicability_text="仅研究生",validity_note="明确持续有效")
    verify(service,db,id);approve(service,db,id)
    assert db.scalar(select(Recognition)).recognition_status=="scoped_recognition"

def test_current_policy_merges_matching_sources(service,db):
    for key in ("p1","p2"):
        id=candidate(db,key,policy=True)
        policy(service,db,id,effective_from="2020-01-01T00:00:00+08:00",effective_until=None,
            current_validity_confirmed=True,validity_note="已核实持续有效")
        verify(service,db,id);approve(service,db,id);db.commit()
    assert count(db,PolicyDocument)==1 and count(db,Recognition)==1
    assert db.scalar(select(Recognition)).recognition_status=="recognized"
    assert len(db.scalar(select(PolicyDocument)).metadata_json["review_sources"])==2

def test_policy_scope_conflict_needs_explicit_resolution(service,db):
    a=candidate(db,"a",policy=True);policy(service,db,a);verify(service,db,a);approve(service,db,a);db.commit()
    b=candidate(db,"b",policy=True);policy(service,db,b,student_scope="graduate",applicability_text="仅研究生")
    assert "RELATION_CONFLICT" in service.detail(db,b)["flags"]
    verify(service,db,b)
    with pytest.raises(HTTPException): approve(service,db,b)
    assert count(db,Recognition)==1

def test_policy_needs_explicit_competition_evidence(service,db):
    id=candidate(db,policy=True)
    row=db.get(ReviewQueue,id);doc=json.loads(row.raw_value)
    doc["collection_context"]["recognition_evidence"]=None;row.raw_value=json.dumps(doc);db.commit()
    with pytest.raises(HTTPException): policy(service,db,id,recognition_evidence="")
    verify(service,db,id)
    with pytest.raises(HTTPException): approve(service,db,id)

def test_admin_and_payload_tampering_fail(service,db):
    id=candidate(db)
    with pytest.raises(HTTPException) as exc:
        service.verify_source(db,id,payload(service,db,id),admin=db.get(User,2))
    assert exc.value.status_code==403
    with pytest.raises(HTTPException):
        service.review(db,id,payload(service,db,id,action="approve",university_id=2),admin=db.get(User,1))

def test_audit_failure_rolls_back_relation_and_candidate(service,db):
    id=candidate(db);verify(service,db,id);db.commit()
    def fail(mapper,connection,target):
        if target.action=="school_relation_review": raise RuntimeError("audit write failure")
    event.listen(AdminAuditLog,"before_insert",fail)
    try:
        with pytest.raises(RuntimeError,match="audit write failure"): approve(service,db,id)
    finally: event.remove(AdminAuditLog,"before_insert",fail)
    db.commit()
    assert count(db,Relation)==0 and db.get(ReviewQueue,id).status=="pending"

def test_caller_can_rollback_successful_approval(service,db):
    id=candidate(db);verify(service,db,id);db.commit();approve(service,db,id);db.rollback()
    assert count(db,Relation)==0 and db.get(ReviewQueue,id).status=="pending"

def test_repeated_defers_do_not_recursively_duplicate_review_history(service,db):
    id=candidate(db)
    for _ in range(6):
        service.review(db,id,payload(service,db,id,action="defer"),admin=db.get(User,1))
    raw=db.get(ReviewQueue,id).raw_value
    assert len(raw)<100000
    assert len(service.detail(db,id)["history"])==6

def test_same_url_with_different_relation_type_is_explicit_conflict(service,db):
    a=candidate(db,"a");verify(service,db,a);approve(service,db,a);db.commit()
    b=candidate(db,"b")
    row=db.get(ReviewQueue,b);doc=json.loads(row.raw_value)
    doc["collection_context"]["source_url"]="https://school.example.test/a"
    doc["collection_context"]["notice_type"]="organization_notice"
    row.raw_value=json.dumps(doc);row.source_url="https://school.example.test/a";db.commit()
    detail=service.detail(db,b)
    assert "RELATION_CONFLICT" in detail["flags"] and not detail["can_approve"]

@pytest.mark.parametrize("changes",[
    dict(current_validity_confirmed=True),
    dict(effective_from="2025-12-31T00:00:00+08:00",effective_until="2025-01-01T00:00:00+08:00"),
    dict(scope_type="college",college_id=None),
])
def test_invalid_current_dates_and_missing_scope_are_rejected(service,db,changes):
    id=candidate(db,policy=True)
    with pytest.raises(HTTPException): policy(service,db,id,**changes)
    assert count(db,PolicyDocument)==0

def test_revoked_policy_cannot_overwrite_recognition(service,db):
    id=candidate(db,policy=True);policy(service,db,id,revoked=True)
    assert "RELATION_CONFLICT" in service.detail(db,id)["flags"]
    verify(service,db,id)
    with pytest.raises(HTTPException): approve(service,db,id)
    assert count(db,Recognition)==0

def test_source_context_change_cannot_reuse_previous_verification(service,db):
    id=candidate(db);verify(service,db,id);db.commit()
    row=db.get(ReviewQueue,id);doc=json.loads(row.raw_value)
    doc["collection_context"]["source_url"]="https://school.example.test/replacement"
    row.raw_value=json.dumps(doc);row.source_url="https://school.example.test/replacement";db.commit()
    assert service.detail(db,id)["source"]["verification_state"]=="UNVERIFIED"
    with pytest.raises(HTTPException): approve(service,db,id)

def test_malformed_deadline_remains_reviewable_but_not_approvable(service,db):
    id=candidate(db,deadline="下周前")
    detail=service.detail(db,id)
    assert not detail["can_approve"]
    verify(service,db,id)
    with pytest.raises(HTTPException): approve(service,db,id)
    assert service.review(db,id,payload(service,db,id,action="reject"),admin=db.get(User,1))["status"]=="rejected"

def test_other_session_writes_invalidate_relation_preview(service,db):
    a,b=candidate(db,"a"),candidate(db,"b")
    verify(service,db,b);db.commit()
    stale=payload(service,db,b,action="approve")
    db.rollback()
    with SessionLocal(bind=db.bind) as other:
        verify(service,other,a);approve(service,other,a);other.commit()
    with pytest.raises(HTTPException) as exc:
        service.review(db,b,stale,admin=db.get(User,1))
    assert exc.value.status_code==409 and count(db,Relation)==1

def test_general_policy_clause_does_not_become_specific_competition_recognition(service,db):
    id=candidate(db,policy=True)
    with pytest.raises(HTTPException):
        policy(service,db,id,recognition_evidence="学校鼓励学生积极参加各类学科竞赛")
    assert count(db,Recognition)==0

def test_read_preload_bounds_49_relation_details_and_preserves_preview(service,db):
    from app.services.review_queue_query import preload
    first=candidate(db,"formal-notice");verify(service,db,first);approve(service,db,first);db.commit()
    policy_id=candidate(db,"formal-policy",policy=True)
    policy(service,db,policy_id);verify(service,db,policy_id);approve(service,db,policy_id);db.commit()
    ids=[candidate(db,f"batch-{i}",policy=(i%5==0)) for i in range(47)]
    ids=[first,policy_id,*ids]
    expected={id:service.detail(db,id) for id in ids[:3]}
    rows=list(db.scalars(select(ReviewQueue).where(ReviewQueue.id.in_(ids))))
    statements=[]
    def record(connection,cursor,statement,parameters,context,executemany):
        if statement.lstrip().upper().startswith("SELECT"): statements.append(statement)
    event.listen(db.bind,"before_cursor_execute",record)
    try:
        with preload(db,rows):
            details={id:service.detail(db,id) for id in ids}
    finally:
        event.remove(db.bind,"before_cursor_execute",record)
    print(f"Relation query sample: 49 details, {len(statements)} SELECTs including parent preload")
    assert len(statements)<=18
    assert {id:details[id] for id in expected}==expected
    assert "field_review_read_context" not in db.info

def test_cached_detail_includes_deferred_peer_conflicts(service,db):
    from app.services.review_queue_query import preload
    a=candidate(db,"a",deadline="2025-04-01")
    service.review(db,a,payload(service,db,a,action="defer"),admin=db.get(User,1));db.commit()
    b=candidate(db,"b",deadline="2025-04-02")
    expected=service.detail(db,b)
    with preload(db,[db.get(ReviewQueue,b)]):
        actual=service.detail(db,b)
    assert actual==expected and "RELATION_CONFLICT" in actual["flags"]

def test_mutation_cannot_reuse_cached_official_relation_snapshot(service,db):
    from app.services.review_queue_query import preload
    a,b=candidate(db,"a"),candidate(db,"b")
    verify(service,db,b);db.commit()
    stale=payload(service,db,b,action="approve")
    rows=list(db.scalars(select(ReviewQueue)))
    with preload(db,rows):
        service.detail(db,b)
        db.rollback()
        with SessionLocal(bind=db.bind) as other:
            verify(service,other,a);approve(service,other,a);other.commit()
        with pytest.raises(HTTPException) as exc:
            service.review(db,b,stale,admin=db.get(User,1))
        assert exc.value.status_code==409
    assert count(db,Relation)==1 and db.get(ReviewQueue,b).status=="pending"

@pytest.mark.parametrize("notice_type,deadline,precision,expected_hour",[
    ("registration_notice","2025-04-01","date",None),
    ("selection_notice","2025-04-01T18:30:00+08:00","second",None),
    ("registration_notice","2025-04-01T18:30:00+08:00","second",18),
])
def test_school_deadline_semantics_and_precision_are_preserved(service,db,notice_type,deadline,precision,expected_hour):
    id=candidate(db,deadline=deadline)
    row=db.get(ReviewQueue,id);doc=json.loads(row.raw_value)
    doc["collection_context"]["notice_type"]=notice_type;row.raw_value=json.dumps(doc);db.commit()
    verify(service,db,id);approve(service,db,id)
    relation=db.scalar(select(Relation))
    if expected_hour is None:
        assert relation.internal_registration_deadline is None
    else:
        assert relation.internal_registration_deadline==datetime.fromisoformat("2025-04-01T10:30:00+00:00")
    assert relation.official_registration_deadline is None
    evidence=relation.metadata_json["school_deadlines"][0]
    assert evidence["school_deadline"]==deadline and evidence["precision"]==precision
    assert evidence["notice_type"]==notice_type
    assert evidence["source_url"]=="https://school.example.test/a"
    assert relation.metadata_json["review_sources"][0]["published_at_precision"]=="date"

@pytest.mark.parametrize("policy_kind",[False,True])
def test_formal_source_metadata_excludes_admin_identity_but_audit_retains_it(service,db,policy_kind):
    id=candidate(db,policy=policy_kind)
    if policy_kind: policy(service,db,id)
    verify(service,db,id);approve(service,db,id)
    target=db.scalar(select(PolicyDocument if policy_kind else Relation))
    source=target.metadata_json["review_sources"][0]
    assert "verified_by" not in source and "candidate_id" not in source
    assert source["source_url"]=="https://school.example.test/a"
    audit=db.scalar(select(AdminAuditLog).where(AdminAuditLog.action=="school_relation_review"))
    assert audit.object_id==id and audit.admin_id==1
    assert audit.after["review"]["sources"][0]["verified_by"]==1

def test_date_only_deadlines_still_participate_in_relation_conflicts(service,db):
    a=candidate(db,"a",deadline="2025-04-01")
    verify(service,db,a);approve(service,db,a);db.commit()
    b=candidate(db,"b",deadline="2025-04-02")
    verify(service,db,b)
    assert "RELATION_CONFLICT" in service.detail(db,b)["flags"]
    with pytest.raises(HTTPException): approve(service,db,b)
