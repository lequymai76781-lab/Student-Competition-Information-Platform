"""Field review's public service contract, using only the isolated test DB."""
from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event, select

from app.models import (
    AdminAuditLog, Competition, CompetitionEdition, CompetitionFactRevision,
    CompetitionFactSource, ReviewQueue, User, UserCorrectionSubmission,
)


@pytest.fixture
def svc():
    from app.services.field_review_service import FieldReviewService
    return FieldReviewService


@pytest.fixture
def admin(db_session):
    user = User(email="field-admin@example.test", username="field-admin", hashed_password="unused", is_admin=True)
    db_session.add(user)
    db_session.commit()
    return user


def candidate(db, svc, fields=None, **kwargs):
    payload = dict(entity_type="competition", competition_id=1, title="待核验资料", fields=fields or [])
    payload.update(kwargs)
    row = svc.create_candidate(db, payload)
    db.commit()
    return row


def proposal(field="organizer", value="新的主办方", source=True):
    return dict(field_name=field, candidate_value=value, source={
        "source_type": "official_website", "source_title": "官方章程",
        "source_url": "https://example.test/rules", "publisher": "竞赛组委会",
    } if source else None)


def verify_all(db, svc, row, admin):
    detail = svc.detail(db, row.id)
    for field in detail["fields"]:
        for item in field["proposals"]:
            detail = svc.verify_source(db, row.id, item["id"], {"preview_token": detail["preview_token"], "note": "核对原文"}, admin=admin)
    db.commit()
    return detail


def approve(db, svc, row, admin, field="organizer", **extra):
    detail = svc.detail(db, row.id)
    item = next(item for item in detail["fields"] if item["field_name"] == field)
    decision = {"field_name": field, "action": "approve", "proposal_id": item["proposals"][0]["id"], **extra}
    return svc.review(db, row.id, {"preview_token": detail["preview_token"], "note": "已核对", "decisions": [decision]}, admin=admin)


def test_candidate_is_staged_and_official_source_is_unverified(db_session, svc):
    row = candidate(db_session, svc, [proposal()])
    result = svc.detail(db_session, row.id)
    assert db_session.get(Competition, 1).organizer == "测试主办方"
    assert result["fields"][0]["change_type"] == "modify"
    assert "UNVERIFIED" in result["flags"]
    assert result["fields"][0]["source"]["verified_by"] is None


def test_no_source_and_unverified_cannot_approve(db_session, svc, admin):
    for has_source in (False, True):
        row = candidate(db_session, svc, [proposal(source=has_source)])
        with pytest.raises(HTTPException) as exc:
            approve(db_session, svc, row, admin)
        assert exc.value.status_code == 422
        assert db_session.get(Competition, 1).organizer == "测试主办方"


def test_source_flags_cannot_be_forged(db_session, svc):
    item = proposal()
    item["source"].update(verified_by=99, verified_at="2026-09-27T00:00:00Z", verification_state="VERIFIED")
    with pytest.raises((ValidationError, HTTPException)):
        candidate(db_session, svc, [item])


@pytest.mark.parametrize("field", ["year", "competition_id", "is_official_verified", "verification_status", "updated_at"])
def test_identity_and_internal_columns_are_not_review_fields(db_session, svc, field):
    with pytest.raises((ValidationError, HTTPException)):
        candidate(db_session, svc, [proposal(field, 2026)])


def test_verify_requires_persisted_active_admin(db_session, svc, admin):
    row = candidate(db_session, svc, [proposal()])
    data = svc.detail(db_session, row.id)
    fake = SimpleNamespace(id=98765, is_admin=True, is_active=True)
    with pytest.raises(HTTPException) as exc:
        svc.verify_source(db_session, row.id, data["fields"][0]["proposals"][0]["id"], {"preview_token": data["preview_token"], "note": "伪造"}, admin=fake)
    assert exc.value.status_code == 403


def test_partial_accept_reject_defer_preserves_unaccepted_values(db_session, svc, admin):
    row = candidate(db_session, svc, [proposal(), proposal("description", "未采纳简介"), proposal("short_name", "稍后处理")])
    before = db_session.get(Competition, 1).description
    data = verify_all(db_session, svc, row, admin)
    result = svc.review(db_session, row.id, {"preview_token": data["preview_token"], "note": "逐项处理", "decisions": [
        {"field_name": "organizer", "action": "approve", "proposal_id": data["fields"][0]["proposals"][0]["id"]},
        {"field_name": "description", "action": "reject"}, {"field_name": "short_name", "action": "defer"},
    ]}, admin=admin)
    db_session.commit()
    assert result["status"] == "partially_approved"
    assert db_session.get(Competition, 1).organizer == "新的主办方"
    assert db_session.get(Competition, 1).description == before
    assert db_session.get(Competition, 1).short_name == "测试大赛"
    assert {r.field_name for r in db_session.scalars(select(CompetitionFactRevision))} == {"organizer"}
    source = db_session.scalar(select(CompetitionFactSource))
    assert source.verification_status == "verified_manual"
    assert source.last_verified_at is not None
    audit = db_session.scalars(select(AdminAuditLog).where(AdminAuditLog.action == "field_review")).one()
    assert audit.admin_id == admin.id
    assert audit.before["values"]["organizer"] == "测试主办方"
    assert audit.after["values"]["organizer"] == "新的主办方"


def test_conflicts_include_local_and_other_pending_candidates(db_session, svc, admin):
    row = candidate(db_session, svc, [proposal(), proposal(value="另一官方说法")])
    other = candidate(db_session, svc, [proposal(value="第三种说法")])
    data = svc.detail(db_session, row.id)
    assert "CONFLICT" in data["flags"]
    assert len(data["fields"][0]["proposals"]) == 2
    assert data["fields"][0]["conflicts"][0]["candidate_id"] == other.id
    assert not data["bulk_eligible_fields"]


def test_explicit_conflict_selection_preserves_other_evidence(db_session, svc, admin):
    row = candidate(db_session, svc, [proposal(), proposal(value="另一官方说法")])
    data = verify_all(db_session, svc, row, admin)
    result = svc.review(db_session, row.id, {"preview_token": data["preview_token"], "note": "选择第二来源", "decisions": [{"field_name": "organizer", "action": "approve", "proposal_id": data["fields"][0]["proposals"][1]["id"]}]}, admin=admin)
    db_session.commit()
    assert db_session.get(Competition, 1).organizer == "另一官方说法"
    assert len(result["fields"][0]["proposals"]) == 2


def test_edition_identity_mismatch_is_rejected(db_session, svc):
    with pytest.raises(HTTPException) as exc:
        candidate(db_session, svc, [proposal("registration_deadline", "2027-05-20T00:00:00+08:00")], entity_type="edition", edition_id=1, year=2027)
    assert exc.value.status_code == 422


def test_edition_review_changes_only_selected_year(db_session, svc, admin):
    db_session.add(CompetitionEdition(competition_id=1, year=2027, edition_name="2027届"))
    db_session.commit()
    row = candidate(db_session, svc, [proposal("official_registration_deadline", "2027-05-20T00:00:00+08:00")], entity_type="edition", edition_id=2, year=2027)
    before = db_session.get(CompetitionEdition, 1).official_registration_deadline
    verify_all(db_session, svc, row, admin)
    approve(db_session, svc, row, admin, "official_registration_deadline")
    db_session.commit()
    assert db_session.get(CompetitionEdition, 1).official_registration_deadline == before
    assert db_session.get(CompetitionEdition, 2).official_registration_deadline == datetime(2027, 5, 19, 16, tzinfo=timezone.utc)


def test_stale_preview_rejects_new_queue_and_fact_values(db_session, svc, admin):
    row = candidate(db_session, svc, [proposal()])
    old = svc.detail(db_session, row.id)
    fresh = verify_all(db_session, svc, row, admin)
    decision = {"field_name": "organizer", "action": "approve", "proposal_id": fresh["fields"][0]["proposals"][0]["id"]}
    with pytest.raises(HTTPException) as exc:
        svc.review(db_session, row.id, {"preview_token": old["preview_token"], "note": "旧页面", "decisions": [decision]}, admin=admin)
    assert exc.value.status_code == 409
    db_session.get(Competition, 1).organizer = "其他管理员已更新"
    db_session.commit()
    with pytest.raises(HTTPException) as exc:
        svc.review(db_session, row.id, {"preview_token": fresh["preview_token"], "note": "旧页面", "decisions": [decision]}, admin=admin)
    assert exc.value.status_code == 409


def test_repeat_review_and_delete_without_confirmation_are_rejected(db_session, svc, admin):
    row = candidate(db_session, svc, [proposal("description", None)])
    verify_all(db_session, svc, row, admin)
    with pytest.raises(HTTPException) as exc:
        approve(db_session, svc, row, admin, "description")
    assert exc.value.status_code == 422
    approve(db_session, svc, row, admin, "description", confirm_delete=True)
    db_session.commit()
    assert db_session.get(Competition, 1).description is None
    with pytest.raises(HTTPException) as exc:
        approve(db_session, svc, row, admin, "description", confirm_delete=True)
    assert exc.value.status_code == 409


def test_free_text_prepare_stages_and_retains_submitter(db_session, svc, admin):
    row = candidate(db_session, svc, description="来源提到新的主办方")
    data = svc.detail(db_session, row.id)
    result = svc.prepare(db_session, row.id, {"preview_token": data["preview_token"], "entity_type": "competition", "competition_id": 1, "title": "结构化", "fields": [proposal()]}, admin=admin)
    db_session.commit()
    assert result["fields"][0]["candidate_value"] == "新的主办方"
    assert db_session.get(Competition, 1).organizer == "测试主办方"


def test_new_competition_requires_approved_name_and_preserves_other_fields(db_session, svc, admin):
    row = candidate(db_session, svc, [proposal("name", "新赛事"), proposal()], competition_id=None)
    verify_all(db_session, svc, row, admin)
    with pytest.raises(HTTPException) as exc:
        approve(db_session, svc, row, admin, "organizer")
    assert exc.value.status_code == 422
    result = approve(db_session, svc, row, admin, "name")
    db_session.commit()
    created = db_session.get(Competition, result["competition_id"])
    assert created.name == "新赛事"
    assert created.organizer is None
    assert created.is_official_verified is False


def test_bulk_disallows_overwrite_and_is_atomic(db_session, svc, admin):
    safe = candidate(db_session, svc, [proposal("frequency", "New English Name")])
    unsafe = candidate(db_session, svc, [proposal()])
    first = verify_all(db_session, svc, safe, admin)
    second = verify_all(db_session, svc, unsafe, admin)
    with pytest.raises(HTTPException) as exc:
        svc.bulk_review(db_session, {"items": [{"id": safe.id, "preview_token": first["preview_token"], "field_names": ["frequency"]}, {"id": unsafe.id, "preview_token": second["preview_token"], "field_names": ["organizer"]}], "note": "批量"}, admin=admin)
    assert exc.value.status_code == 422
    assert db_session.get(Competition, 1).frequency is None
    assert not list(db_session.scalars(select(CompetitionFactRevision)))


def test_low_risk_bulk_succeeds(db_session, svc, admin):
    row = candidate(db_session, svc, [proposal("frequency", "Test Contest"), proposal("official_account", "test-account")])
    data = verify_all(db_session, svc, row, admin)
    assert set(data["bulk_eligible_fields"]) == {"frequency", "official_account"}
    result = svc.bulk_review(db_session, {"items": [{"id": row.id, "preview_token": data["preview_token"], "field_names": data["bulk_eligible_fields"]}], "note": "同来源补全"}, admin=admin)
    db_session.commit()
    assert result["items"][0]["status"] == "approved"
    assert db_session.get(Competition, 1).frequency == "Test Contest"


def test_audit_failure_rolls_back_facts_sources_and_queue(db_session, svc, admin):
    row = candidate(db_session, svc, [proposal()])
    data = verify_all(db_session, svc, row, admin)
    def fail_audit(mapper, connection, target):
        if target.action == "field_review":
            raise RuntimeError("simulated audit disk failure")
    event.listen(AdminAuditLog, "before_insert", fail_audit)
    try:
        with pytest.raises(RuntimeError):
            approve(db_session, svc, row, admin)
    finally:
        event.remove(AdminAuditLog, "before_insert", fail_audit)
    assert db_session.scalar(select(Competition.organizer).where(Competition.id == 1)) == "测试主办方"
    assert db_session.get(Competition, 1).organizer == "测试主办方"
    assert not list(db_session.scalars(select(CompetitionFactRevision)))
    assert not list(db_session.scalars(select(CompetitionFactSource)))
    assert svc.detail(db_session, row.id)["preview_token"] == data["preview_token"]


def test_review_syncs_correction_and_linked_legacy_queue(db_session, svc, admin):
    correction = UserCorrectionSubmission(user_id=admin.id, competition_id=1, correction_type="other", description="修正主办方")
    db_session.add(correction)
    db_session.flush()
    legacy = ReviewQueue(item_type="user_correction", item_id=correction.id, competition_id=1, reason="修正")
    db_session.add(legacy)
    db_session.commit()
    row = candidate(db_session, svc, [proposal()], origin="user_submission", origin_id=correction.id, origin_kind="user_correction")
    verify_all(db_session, svc, row, admin)
    approve(db_session, svc, row, admin)
    db_session.commit()
    assert correction.status == legacy.status == "approved"
    assert correction.reviewed_by == admin.id


def test_new_edition_uses_explicit_year_and_only_approved_fields(db_session, svc, admin):
    row = candidate(db_session, svc, [proposal("registration_fee", 25), proposal("fee_notes", "暂未确认")], entity_type="edition", year=2028)
    verify_all(db_session, svc, row, admin)
    result = approve(db_session, svc, row, admin, "registration_fee")
    db_session.commit()
    edition = db_session.get(CompetitionEdition, result["edition_id"])
    assert edition.year == 2028
    assert edition.registration_fee == 25
    assert edition.fee_notes is None
    assert edition.verification_status == "verified_manual"


def test_naive_dates_and_wrong_entity_fields_are_rejected(db_session, svc):
    with pytest.raises(HTTPException):
        candidate(db_session, svc, [proposal("registration_deadline", "2026-11-05T12:00:00")], entity_type="edition", edition_id=1)
    with pytest.raises(HTTPException):
        candidate(db_session, svc, [proposal("registration_deadline", "2026-11-05T12:00:00+08:00")])


def test_reject_requires_no_source_and_completes_without_fact_changes(db_session, svc, admin):
    row = candidate(db_session, svc, [proposal(source=False)])
    data = svc.detail(db_session, row.id)
    result = svc.review(db_session, row.id, {"preview_token": data["preview_token"], "note": "未提供证据", "decisions": [{"field_name": "organizer", "action": "reject"}]}, admin=admin)
    db_session.commit()
    assert result["status"] == "rejected"
    assert db_session.get(Competition, 1).organizer == "测试主办方"
    assert not list(db_session.scalars(select(CompetitionFactSource)))


def test_notification_failure_rolls_back_deadline_event_revision_and_decision(db_session, svc, admin, monkeypatch):
    from app.models import CompetitionUpdateEvent, Notification
    from app.services.notification_service import NotificationService
    row = candidate(db_session, svc, [proposal("official_registration_deadline", "2026-11-01T12:00:00+08:00")], entity_type="edition", edition_id=1)
    before = db_session.get(CompetitionEdition, 1).official_registration_deadline
    data = verify_all(db_session, svc, row, admin)
    def fail_notifications(self, db, update_event):
        db.add(Notification(user_id=admin.id, type="competition_update", title="should roll back", dedup_key="field-rollback"))
        db.flush()
        raise RuntimeError("notification storage failure")
    monkeypatch.setattr(NotificationService, "_notify_event", fail_notifications)
    with pytest.raises(RuntimeError):
        approve(db_session, svc, row, admin, "official_registration_deadline")
    assert db_session.get(CompetitionEdition, 1).official_registration_deadline == before
    assert not list(db_session.scalars(select(CompetitionUpdateEvent)))
    assert not list(db_session.scalars(select(CompetitionFactRevision)))
    assert not list(db_session.scalars(select(Notification)))
    assert svc.detail(db_session, row.id)["preview_token"] == data["preview_token"]


@pytest.mark.parametrize("table", ["review_queue", "competitions"])
def test_compare_and_swap_rejects_change_after_preview_validation(db_session, svc, admin, table):
    row = candidate(db_session, svc, [proposal()])
    verify_all(db_session, svc, row, admin)
    injected = []
    def mutate_before_cas(connection, cursor, statement, parameters, context, executemany):
        if not injected and statement.startswith(f"UPDATE {table} "):
            injected.append(True)
            if table == "review_queue":
                connection.exec_driver_sql("UPDATE review_queue SET raw_value = raw_value || ' ' WHERE id = ?", (row.id,))
            else:
                connection.exec_driver_sql("UPDATE competitions SET organizer = 'Concurrent official change' WHERE id = 1")
    event.listen(db_session.get_bind(), "before_cursor_execute", mutate_before_cas)
    try:
        with pytest.raises(HTTPException) as exc:
            approve(db_session, svc, row, admin)
        assert exc.value.status_code == 409
    finally:
        event.remove(db_session.get_bind(), "before_cursor_execute", mutate_before_cas)
    assert injected
    assert not list(db_session.scalars(select(CompetitionFactRevision)))


def test_bulk_second_failure_rolls_back_first_candidate(db_session, svc, admin):
    first = candidate(db_session, svc, [proposal("frequency", "English Name")])
    second = candidate(db_session, svc, [proposal("official_account", "account")])
    one = verify_all(db_session, svc, first, admin)
    two = verify_all(db_session, svc, second, admin)
    def fail_second_audit(mapper, connection, target):
        if target.action == "field_review" and target.object_id == second.id:
            raise RuntimeError("second audit failure")
    event.listen(AdminAuditLog, "before_insert", fail_second_audit)
    try:
        with pytest.raises(HTTPException):
            svc.bulk_review(db_session, {"items": [{"id": first.id, "preview_token": one["preview_token"], "field_names": ["frequency"]}, {"id": second.id, "preview_token": two["preview_token"], "field_names": ["official_account"]}], "note": "批量失败"}, admin=admin)
    finally:
        event.remove(AdminAuditLog, "before_insert", fail_second_audit)
    assert db_session.get(Competition, 1).frequency is None
    assert db_session.get(Competition, 1).official_account is None
    assert not list(db_session.scalars(select(CompetitionFactRevision)))
    assert svc.detail(db_session, first.id)["status"] == "pending"


@pytest.fixture
def field_app(db_session):
    from app.api.deps import get_db
    from app.api.routes.field_reviews import router
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    return app


def test_every_field_review_route_requires_admin(field_app):
    with TestClient(field_app) as client:
        for method, url in [("get", ""), ("get", "/config"), ("get", "/1"), ("post", ""), ("put", "/1/prepare"), ("post", "/1/review"), ("post", "/1/reject-unstructured"), ("post", "/1/sources/p/verify"), ("post", "/bulk-review")]:
            response = client.request(method, "/api/admin/field-reviews" + url, json={} if method != "get" else None)
            assert response.status_code == 403, (method, url, response.text)


def test_api_create_filter_verify_review_and_forgery_rejection(field_app, db_session, admin):
    from app.api.deps import get_current_admin
    field_app.dependency_overrides[get_current_admin] = lambda: admin
    with TestClient(field_app) as client:
        prefix = "/api/admin/field-reviews"
        created = client.post(prefix, json={"entity_type": "competition", "competition_id": 1, "title": "API 候选", "fields": [proposal()]})
        assert created.status_code == 200
        data = created.json()["data"]
        filtered = client.get(prefix, params={"flag": "UNVERIFIED", "submitter_id": admin.id, "competition_id": 1, "limit": 1}).json()["data"]
        assert filtered["total"] == 1
        assert filtered["items"][0]["id"] == data["id"]
        assert client.get(prefix, params={"flag": "NO_SOURCE"}).json()["data"]["total"] == 0
        verified = client.post(f"{prefix}/{data['id']}/sources/{data['fields'][0]['proposals'][0]['id']}/verify", json={"preview_token": data["preview_token"], "note": "对照通知"})
        assert verified.status_code == 200
        fresh = verified.json()["data"]
        approved = client.post(f"{prefix}/{data['id']}/review", json={"preview_token": fresh["preview_token"], "note": "采纳", "decisions": [{"field_name": "organizer", "action": "approve", "proposal_id": fresh["fields"][0]["proposals"][0]["id"]}]})
        assert approved.status_code == 200
        assert approved.json()["data"]["status"] == "approved"
        assert db_session.get(Competition, 1).organizer == "新的主办方"
        forged = proposal()
        forged["source"]["verified_by"] = admin.id
        assert client.post(prefix, json={"entity_type": "competition", "competition_id": 1, "title": "伪造", "fields": [forged]}).status_code == 422


def test_successful_review_still_belongs_to_callers_outer_transaction(db_session, svc, admin):
    row = candidate(db_session, svc, [proposal()])
    data = verify_all(db_session, svc, row, admin)
    identity = row.id
    approve(db_session, svc, row, admin)
    db_session.rollback()
    assert db_session.get(Competition, 1).organizer == "测试主办方"
    assert svc.detail(db_session, identity)["preview_token"] == data["preview_token"]
    assert not list(db_session.scalars(select(CompetitionFactRevision)))


def test_admin_id_alone_cannot_impersonate_persisted_admin(db_session, svc, admin):
    row = candidate(db_session, svc, [proposal()])
    data = svc.detail(db_session, row.id)
    for impostor in (SimpleNamespace(id=admin.id, is_admin=True), User(id=admin.id, is_admin=True)):
        with pytest.raises(HTTPException) as exc:
            svc.verify_source(db_session, row.id, data["fields"][0]["proposals"][0]["id"], {"preview_token": data["preview_token"], "note": "冒充身份"}, admin=impostor)
        assert exc.value.status_code == 403


def test_bulk_does_not_revalidate_unrelated_legacy_blank_fact(db_session, svc, admin):
    db_session.get(Competition, 1).frequency = ""
    db_session.commit()
    row = candidate(db_session, svc, [proposal("official_account", "Contest")])
    data = verify_all(db_session, svc, row, admin)
    svc.bulk_review(db_session, {"items": [{"id": row.id, "preview_token": data["preview_token"], "field_names": ["official_account"]}], "note": "补全"}, admin=admin)
    assert db_session.get(Competition, 1).official_account == "Contest"


def test_audit_retains_sources_for_rejected_as_well_as_approved_fields(db_session, svc, admin):
    row = candidate(db_session, svc, [proposal(), proposal("short_name", "不采纳简称")])
    data = verify_all(db_session, svc, row, admin)
    svc.review(db_session, row.id, {"preview_token": data["preview_token"], "note": "逐字段", "decisions": [{"field_name": "organizer", "action": "approve", "proposal_id": data["fields"][0]["proposals"][0]["id"]}, {"field_name": "short_name", "action": "reject"}]}, admin=admin)
    audit = db_session.scalar(select(AdminAuditLog).where(AdminAuditLog.action == "field_review"))
    assert {source["field_name"] for source in audit.after["review"]["sources"]} == {"organizer", "short_name"}


def test_bulk_still_excludes_conflict_across_sources(db_session, svc, admin):
    first = candidate(db_session, svc, [proposal("frequency", "每年一次")])
    second = candidate(db_session, svc, [proposal("official_account", "account")])
    candidate(db_session, svc, [proposal("official_account", "conflicting-account")])
    one = verify_all(db_session, svc, first, admin)
    two = verify_all(db_session, svc, second, admin)
    with pytest.raises(HTTPException) as exc:
        svc.bulk_review(db_session, {"items": [
            {"id": first.id, "preview_token": one["preview_token"], "field_names": ["frequency"]},
            {"id": second.id, "preview_token": two["preview_token"], "field_names": ["official_account"]}],
            "note": "存在冲突，不允许批量"}, admin=admin)
    assert exc.value.status_code == 422
    assert db_session.get(Competition, 1).frequency is None
    assert not list(db_session.scalars(select(CompetitionFactRevision)))


def test_bulk_rejects_external_change_between_preview_validation_and_write(db_session, svc, admin):
    row = candidate(db_session, svc, [proposal("frequency", "Contest")])
    data = verify_all(db_session, svc, row, admin)
    injected = []
    def competing_write(connection, cursor, statement, parameters, context, executemany):
        if not injected and statement.startswith("UPDATE competitions "):
            injected.append(True)
            connection.exec_driver_sql("UPDATE competitions SET frequency = 'Concurrent name' WHERE id = 1")
    event.listen(db_session.get_bind(), "before_cursor_execute", competing_write)
    try:
        with pytest.raises(HTTPException) as exc:
            svc.bulk_review(db_session, {"items": [{"id": row.id, "preview_token": data["preview_token"], "field_names": ["frequency"]}], "note": "并发修改"}, admin=admin)
        assert exc.value.status_code == 409
    finally:
        event.remove(db_session.get_bind(), "before_cursor_execute", competing_write)
    assert injected
    assert not list(db_session.scalars(select(CompetitionFactRevision)))


def test_outer_commit_failure_at_route_rolls_back_successful_review(field_app, db_session, svc, admin, monkeypatch):
    from app.api.deps import get_current_admin
    field_app.dependency_overrides[get_current_admin] = lambda: admin
    row = candidate(db_session, svc, [proposal()])
    data = verify_all(db_session, svc, row, admin)
    def fail_commit():
        raise RuntimeError("outer transaction commit failed")
    monkeypatch.setattr(db_session, "commit", fail_commit)
    with TestClient(field_app, raise_server_exceptions=False) as client:
        response = client.post(f"/api/admin/field-reviews/{row.id}/review", json={"preview_token": data["preview_token"], "note": "批准", "decisions": [{"field_name": "organizer", "action": "approve", "proposal_id": data["fields"][0]["proposals"][0]["id"]}]})
        assert response.status_code == 500
    assert db_session.get(Competition, 1).organizer == "测试主办方"
    assert not list(db_session.scalars(select(CompetitionFactRevision)))
    assert svc.detail(db_session, row.id)["status"] == "pending"


def test_new_edition_cannot_be_created_by_approving_only_null(db_session, svc, admin):
    row = candidate(db_session, svc, [proposal("host_location", None)], entity_type="edition", year=2029)
    verify_all(db_session, svc, row, admin)
    with pytest.raises(HTTPException) as exc:
        approve(db_session, svc, row, admin, "host_location")
    assert exc.value.status_code == 422
    assert db_session.scalar(select(CompetitionEdition.id).where(CompetitionEdition.year == 2029)) is None


@pytest.mark.parametrize("key,value", [("verification_status", "verified_official"), ("verification_state", "VERIFIED"), ("verified_by", 1), ("verified_at", "2026-01-01T00:00:00Z"), ("is_verified", True)])
def test_nested_verification_metadata_is_not_accepted(db_session, svc, key, value):
    item = {"year": 2020, "title": "创办", key: value}
    with pytest.raises(HTTPException) as exc:
        candidate(db_session, svc, [proposal("history_timeline", [item])])
    assert exc.value.status_code == 422


@pytest.mark.parametrize("value", [[{"year": 2020, "title": "创办", "source_url": "javascript:alert(1)"}], [{"title": "没有年份"}], ["不是时间线条目"], [{"year": 2020, "title": "创办", "extra": {"verified_by": 1}}]])
def test_structured_fact_shape_and_links_are_validated(db_session, svc, value):
    with pytest.raises(HTTPException) as exc:
        candidate(db_session, svc, [proposal("history_timeline", value)])
    assert exc.value.status_code == 422


def test_structured_approval_adds_only_server_manual_provenance(db_session, svc, admin):
    row = candidate(db_session, svc, [proposal("history_timeline", [{"year": 2021, "title": "创办", "source_url": "https://example.test/unselected"}])])
    verify_all(db_session, svc, row, admin)
    result = approve(db_session, svc, row, admin, "history_timeline")
    value = db_session.get(Competition, 1).history_timeline[0]
    assert value["verification_status"] == "verified_manual"
    assert "verified_by" not in value
    assert value["source_url"] == "https://example.test/rules"
    assert value["verified_at"]
    assert result["fields"][0]["changed"] is False
    assert "verified_by" not in result["fields"][0]["proposals"][0]["candidate_value"][0]
    assert result["fields"][0]["source"]["verified_by"] == admin.id
    assert result["history"][-1]["sources"][0]["verified_by"] == admin.id


def test_offline_source_uses_missing_url_without_fabricating_a_public_link(db_session, svc, admin):
    item = proposal()
    item["source"]["source_url"] = None
    row = candidate(db_session, svc, [item])
    verify_all(db_session, svc, row, admin)
    approve(db_session, svc, row, admin)
    assert db_session.scalar(select(CompetitionFactSource)).source_url == ""


def test_pending_new_edition_candidate_resolves_later_created_edition_for_provenance(db_session, svc, admin):
    first = candidate(db_session, svc, [proposal("registration_fee", 25)], entity_type="edition", year=2030)
    second = candidate(db_session, svc, [proposal("host_location", "武汉")], entity_type="edition", year=2030)
    verify_all(db_session, svc, first, admin)
    verify_all(db_session, svc, second, admin)
    created = approve(db_session, svc, first, admin, "registration_fee")
    db_session.commit()
    current = svc.detail(db_session, second.id)
    assert current["edition_id"] == created["edition_id"]
    updated = approve(db_session, svc, second, admin, "host_location")
    db_session.commit()
    assert updated["edition_id"] == created["edition_id"]
    fact = db_session.scalar(select(CompetitionFactSource).where(CompetitionFactSource.field_name == "host_location"))
    assert fact.competition_edition_id == created["edition_id"]
    revision = db_session.scalar(select(CompetitionFactRevision).where(CompetitionFactRevision.field_name == "host_location"))
    assert revision.competition_edition_id == created["edition_id"]


@pytest.mark.parametrize("field,original", [("co_organizers", ["原联合主办方"]), ("history_timeline", [{"year": 2020, "title": "原历史事实", "verification_status": "verified_official"}])])
def test_empty_array_requires_confirmation_to_clear_existing_values(db_session, svc, admin, field, original):
    setattr(db_session.get(Competition, 1), field, original)
    db_session.commit()
    row = candidate(db_session, svc, [proposal(field, [])])
    preview = verify_all(db_session, svc, row, admin)
    assert preview["fields"][0]["change_type"] == "delete"
    with pytest.raises(HTTPException) as exc:
        approve(db_session, svc, row, admin, field)
    assert exc.value.status_code == 422
    assert getattr(db_session.get(Competition, 1), field) == original
    result = approve(db_session, svc, row, admin, field, confirm_delete=True)
    db_session.commit()
    assert getattr(db_session.get(Competition, 1), field) == []
    assert result["history"][-1]["decisions"][0]["confirm_delete"] is True


def test_public_sources_revisions_and_updates_keep_admin_review_metadata_private(field_app, db_session, svc, admin, monkeypatch):
    from app.api.routes.competitions import router as public_router
    from app.models import CompetitionUpdateEvent
    from app.services.user_facing_data_policy import UserFacingDataPolicy
    # Exercise the real public serializers with the future manual-fact
    # allowlist locally; the existing production allowlist is not changed.
    monkeypatch.setattr(UserFacingDataPolicy, "VERIFIED_FACT_STATUSES", UserFacingDataPolicy.VERIFIED_FACT_STATUSES | {"verified_manual"})
    field_app.include_router(public_router, prefix="/api")
    private_note = "PRIVATE ADMIN REVIEW NOTE: 内部联系记录"
    db_session.get(Competition, 1).history_timeline = [{"year": 2020, "title": "旧历史事件",
        "verification_status": "verified_official", "verified_by": 123456, "review_id": 987654}]
    db_session.commit()
    rows = [
        candidate(db_session, svc, [proposal("edition_name", "公开的届次名称")], entity_type="edition", edition_id=1),
        candidate(db_session, svc, [proposal("history_timeline", [{"year": 2024, "title": "公开的历史事件"}])]),
    ]
    for row in rows:
        data = verify_all(db_session, svc, row, admin)
        result = svc.review(db_session, row.id, {"preview_token": data["preview_token"], "note": private_note, "decisions": [
            {"field_name": data["fields"][0]["field_name"], "action": "approve", "proposal_id": data["fields"][0]["proposals"][0]["id"]},
        ]}, admin=admin)
        db_session.commit()
        assert result["history"][-1]["note"] == private_note
        assert result["history"][-1]["reviewer_id"] == admin.id
        assert result["history"][-1]["sources"][0]["verified_by"] == admin.id
    with TestClient(field_app) as client:
        updates = client.get("/api/competitions/1/updates", params={"edition_id": 1})
        detail = client.get("/api/competitions/1", params={"edition_id": 1})
    assert updates.status_code == detail.status_code == 200
    assert updates.json()["data"]
    public_detail = detail.json()["data"]
    assert {source["field_name"] for source in public_detail["fact_sources"]} >= {"edition_name", "history_timeline"}
    assert public_detail["fact_revisions"]
    for public_response in (updates.text, detail.text):
        assert private_note not in public_response
        for private_key in ("review_id", "reviewer_id", "verified_by", "candidate_id"):
            assert private_key not in public_response
    for update_event in db_session.scalars(select(CompetitionUpdateEvent)):
        metadata = json.dumps(update_event.metadata_json, ensure_ascii=False)
        assert private_note not in metadata
        assert "reviewer_id" not in metadata
        assert "review_id" not in metadata
        assert "verified_by" not in metadata
    audits = list(db_session.scalars(select(AdminAuditLog).where(AdminAuditLog.action == "field_review")))
    assert len(audits) == 2
    assert all(audit.admin_id == admin.id and audit.after["review"]["note"] == private_note for audit in audits)


def unstructured_origin(db, svc, owner, kind="user_correction"):
    from app.models import BetaFeedback
    if kind == "user_correction":
        source = UserCorrectionSubmission(user_id=owner.id, competition_id=1, correction_type="其他",
            description="无法形成有效字段的原始材料", source_url="https://example.test/original-evidence")
    else:
        source = BetaFeedback(user_id=owner.id, category="数据补充", content="无法形成有效字段的原始材料")
    db.add(source)
    db.flush()
    legacy = ReviewQueue(item_type=kind, item_id=source.id, reason="原始提交", source_url="https://example.test/original-evidence")
    db.add(legacy)
    db.flush()
    row = svc.create_candidate(db, {"entity_type": "competition", "competition_id": 1, "title": "待结构化材料",
        "description": "无法形成有效字段的原始材料", "origin": "user_submission", "origin_kind": kind,
        "origin_id": source.id, "fields": []}, submitter_id=owner.id)
    row.source_url = legacy.source_url
    db.commit()
    return row, source, legacy


@pytest.mark.parametrize("kind", ["user_correction", "user_supplement"])
def test_unstructured_rejection_syncs_origin_and_retains_evidence_without_fact_writes(db_session, svc, admin, kind):
    row, source, legacy = unstructured_origin(db_session, svc, admin, kind)
    data = svc.detail(db_session, row.id)
    assert data["origin_source_url"] == "https://example.test/original-evidence"
    result = svc.reject_unstructured(db_session, row.id, {"preview_token": data["preview_token"], "note": "材料与该赛事无关"}, admin=admin)
    db_session.commit()
    assert result["status"] == source.status == legacy.status == "rejected"
    assert result["fields"] == []
    assert result["origin_source_url"] == data["origin_source_url"]
    assert result["history"][-1]["action"] == "field_reject_unstructured"
    assert result["history"][-1]["reviewer_id"] == admin.id
    assert result["history"][-1]["note"] == "材料与该赛事无关"
    assert db_session.get(Competition, 1).organizer == "测试主办方"
    assert not list(db_session.scalars(select(CompetitionFactSource)))
    assert not list(db_session.scalars(select(CompetitionFactRevision)))
    audit = db_session.scalar(select(AdminAuditLog).where(AdminAuditLog.action == "field_reject_unstructured"))
    assert audit.admin_id == admin.id
    assert audit.before["status"] == "pending"
    assert audit.after["status"] == "rejected"
    assert audit.before["candidate"]["description"] == "无法形成有效字段的原始材料"
    assert audit.before["candidate"]["origin_source_url"] == data["origin_source_url"]
    assert result["history"][-1]["sources"][0]["verification_state"] == "UNVERIFIED"
    with pytest.raises(HTTPException) as exc:
        svc.reject_unstructured(db_session, row.id, {"preview_token": result["preview_token"], "note": "重复拒绝"}, admin=admin)
    assert exc.value.status_code == 409


@pytest.mark.parametrize("state", ["structured", "terminal", "stale", "changed_source"])
def test_unstructured_rejection_refuses_structured_terminal_and_stale_candidates(db_session, svc, admin, state):
    row = candidate(db_session, svc, [proposal()] if state == "structured" else [])
    data = svc.detail(db_session, row.id)
    if state == "terminal":
        row.status = "rejected"
        db_session.commit()
        data = svc.detail(db_session, row.id)
    elif state == "stale":
        doc = json.loads(row.raw_value)
        doc["revision"] += 1
        row.raw_value = json.dumps(doc)
        db_session.commit()
    elif state == "changed_source":
        row.source_url = "https://example.test/revised-original"
        db_session.commit()
    with pytest.raises(HTTPException) as exc:
        svc.reject_unstructured(db_session, row.id, {"preview_token": data["preview_token"], "note": "不可直接拒绝"}, admin=admin)
    assert exc.value.status_code == 409
    assert row.status == ("rejected" if state == "terminal" else "pending")


def test_unstructured_rejection_requires_persisted_admin(db_session, svc, admin):
    row = candidate(db_session, svc)
    data = svc.detail(db_session, row.id)
    with pytest.raises(HTTPException) as exc:
        svc.reject_unstructured(db_session, row.id, {"preview_token": data["preview_token"], "note": "伪造身份"},
            admin=SimpleNamespace(id=admin.id, is_admin=True))
    assert exc.value.status_code == 403


def test_unstructured_rejection_audit_failure_rolls_back_origin_and_all_queues(db_session, svc, admin):
    row, source, legacy = unstructured_origin(db_session, svc, admin)
    data = svc.detail(db_session, row.id)
    def fail_audit(mapper, connection, target):
        if target.action == "field_reject_unstructured":
            raise RuntimeError("unstructured audit failed")
    event.listen(AdminAuditLog, "before_insert", fail_audit)
    try:
        with pytest.raises(RuntimeError):
            svc.reject_unstructured(db_session, row.id, {"preview_token": data["preview_token"], "note": "拒绝无效材料"}, admin=admin)
    finally:
        event.remove(AdminAuditLog, "before_insert", fail_audit)
    assert row.status == source.status == legacy.status == "pending"
    assert source.reviewed_by is None
    assert not list(db_session.scalars(select(AdminAuditLog)))
    assert svc.detail(db_session, row.id)["preview_token"] == data["preview_token"]


def test_http_unstructured_rejection_returns_updated_detail(field_app, db_session, svc, admin):
    from app.api.deps import get_current_admin
    field_app.dependency_overrides[get_current_admin] = lambda: admin
    row, source, legacy = unstructured_origin(db_session, svc, admin)
    data = svc.detail(db_session, row.id)
    with TestClient(field_app) as client:
        response = client.post(f"/api/admin/field-reviews/{row.id}/reject-unstructured",
            json={"preview_token": data["preview_token"], "note": "无法核实且无具体字段"})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "rejected"
    assert response.json()["data"]["origin_source_url"] == "https://example.test/original-evidence"
    assert source.status == legacy.status == "rejected"


def test_preparing_unstructured_candidate_preserves_original_source_link(db_session, svc, admin):
    row, _, _ = unstructured_origin(db_session, svc, admin)
    data = svc.detail(db_session, row.id)
    result = svc.prepare(db_session, row.id, {"preview_token": data["preview_token"], "entity_type": "competition",
        "competition_id": 1, "title": "整理字段", "fields": [proposal()]}, admin=admin)
    assert result["origin_source_url"] == "https://example.test/original-evidence"
    assert result["fields"][0]["source_url"] == "https://example.test/rules"
    assert result["fields"][0]["verification_state"] == "UNVERIFIED"
