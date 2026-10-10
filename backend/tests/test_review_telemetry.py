"""Isolated telemetry tests: server times, attribution and actual review transactions."""
from datetime import datetime, timedelta, timezone
import importlib
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app.models import AdminAuditLog, User
from app.services.field_review_service import FieldReviewService as Fields

@pytest.fixture
def telemetry():
    return importlib.import_module("app.services.review_telemetry_service")

@pytest.fixture
def admin(db_session):
    user = User(email="timing@example.test", username="timing", hashed_password="unused", is_admin=True)
    db_session.add(user)
    db_session.commit()
    return user

@pytest.fixture
def clock(telemetry, monkeypatch):
    instant = [datetime(2026, 9, 28, tzinfo=timezone.utc)]
    monkeypatch.setattr(telemetry, "_now", lambda: instant[0])
    return lambda seconds: instant.__setitem__(0, datetime(2026, 9, 28, tzinfo=timezone.utc) + timedelta(seconds=seconds))

def candidate(db, fields=1):
    row = Fields.create_candidate(db, dict(entity_type="competition", competition_id=1, title="Timing fixture",
        fields=[dict(field_name=name, candidate_value="Proposed", source={"source_type": "official_website",
        "source_title": "Rules", "source_url": "https://example.test/rules"}) for name in ["description", "short_name"][:fields]]))
    db.commit()
    return row

def decide(db, row, admin, fields=None, action="reject"):
    d = Fields.detail(db, row.id)
    return Fields.review(db, row.id, dict(preview_token=d["preview_token"], note="Review evidence",
        decisions=[dict(field_name=f["field_name"], action=action) for f in d["fields"]
        if fields is None or f["field_name"] in fields]), admin=admin)

def logs(db):
    return list(db.scalars(select(AdminAuditLog).where(AdminAuditLog.object_type == "review_telemetry")))

def test_server_phases_preserve_candidate_and_preview(db_session, admin, telemetry, clock):
    row = candidate(db_session)
    before = Fields.detail(db_session, row.id)
    raw, updated = row.raw_value, row.updated_at
    svc = telemetry.ReviewTelemetryService
    session = svc.start(db_session, row.id, {"mode": "human"}, admin=admin)
    clock(4)
    svc.event(db_session, row.id, {"session_id": session["session_id"], "event": "source_open",
        "proposal_id": before["fields"][0]["proposals"][0]["id"]}, admin=admin)
    clock(9)
    svc.event(db_session, row.id, {"session_id": session["session_id"], "event": "decision",
        "field_name": "description", "decision": "reject"}, admin=admin)
    clock(12)
    result = svc.event(db_session, row.id, {"session_id": session["session_id"], "event": "submit"}, admin=admin)
    assert result["phase_seconds"] == {"source_open": 4, "decision": 9, "submit": 12}
    assert result["elapsed_seconds"] == 12 and result["reviewer_id"] == admin.id
    assert row.raw_value == raw and row.updated_at == updated
    assert Fields.detail(db_session, row.id)["preview_token"] == before["preview_token"]

def test_resume_after_source_verification_does_not_restart(db_session, admin, telemetry, clock):
    row = candidate(db_session)
    svc = telemetry.ReviewTelemetryService
    first = svc.start(db_session, row.id, {"mode": "human"}, admin=admin)
    d = Fields.detail(db_session, row.id)
    Fields.verify_source(db_session, row.id, d["fields"][0]["proposals"][0]["id"],
        {"preview_token": d["preview_token"], "note": "Read original"}, admin=admin)
    clock(20)
    second = svc.start(db_session, row.id, {"mode": "human"}, admin=admin)
    assert second["session_id"] == first["session_id"] and second["resumed"]
    assert second["elapsed_seconds"] == 20
    assert len([a for a in logs(db_session) if a.action == "review_telemetry_start"]) == 1

def test_partial_and_defer_not_completed_then_idempotent_final(db_session, admin, telemetry, clock):
    row = candidate(db_session, 2)
    svc = telemetry.ReviewTelemetryService
    session = svc.start(db_session, row.id, {"mode": "human"}, admin=admin)
    decide(db_session, row, admin, ["description"])
    assert not svc.complete(db_session, row.id, admin.id, "reject")["recorded"]
    decide(db_session, row, admin, ["short_name"], "defer")
    assert not svc.complete(db_session, row.id, admin.id, "defer")["recorded"]
    clock(15)
    decide(db_session, row, admin, ["short_name"])
    result = svc.complete(db_session, row.id, admin.id, "reject")
    assert result["session"]["status"] == "completed" and result["session"]["elapsed_seconds"] == 15
    assert not svc.complete(db_session, row.id, admin.id, "reject")["recorded"]
    assert len([a for a in logs(db_session) if a.action == "review_telemetry_complete"]) == 1
    with pytest.raises(HTTPException) as err:
        svc.event(db_session, row.id, {"session_id": session["session_id"], "event": "submit"}, admin=admin)
    assert err.value.status_code == 409

def test_human_automation_statistics_and_untimed_reviews(db_session, admin, telemetry, clock):
    svc = telemetry.ReviewTelemetryService
    tick = 0
    for mode, duration in [("human", 10), ("human", 20), ("human", 100), ("automation", 5)]:
        row = candidate(db_session)
        clock(tick)
        svc.start(db_session, row.id, {"mode": mode}, admin=admin)
        tick += duration
        clock(tick)
        decide(db_session, row, admin)
        svc.complete(db_session, row.id, admin.id, "reject")
        db_session.commit()
        tick += 1
    row = candidate(db_session)
    decide(db_session, row, admin)
    assert svc.complete(db_session, row.id, admin.id, "reject")["reason"] == "no_active_session"
    stats = svc.statistics(db_session, admin)
    human, auto = stats["groups"]["human"], stats["groups"]["automation"]
    assert human["completed_samples"] == 3 and auto["completed_samples"] == 1
    assert human["mean_seconds"] == pytest.approx(130 / 3)
    assert human["median_seconds"] == 20 and human["p90_seconds"] == 100
    assert human["theoretical_per_hour"] == pytest.approx(10800 / 130)
    assert auto["mean_seconds"] == 5
    assert stats["processed_candidates"] == 5 and stats["unknown_duration_candidates"] == 1
    assert list(svc.statistics(db_session, admin, mode="automation")["groups"]) == ["automation"]

def test_switch_interrupts_and_idle_sessions_are_not_samples(db_session, admin, telemetry, clock):
    one, two = candidate(db_session), candidate(db_session)
    svc = telemetry.ReviewTelemetryService
    old = svc.start(db_session, one.id, {"mode": "human"}, admin=admin)
    with pytest.raises(HTTPException) as err:
        svc.start(db_session, one.id, {"mode": "automation"}, admin=admin)
    assert err.value.status_code == 409
    clock(12)
    svc.start(db_session, two.id, {"mode": "human"}, admin=admin)
    with pytest.raises(HTTPException):
        svc.event(db_session, one.id, {"session_id": old["session_id"], "event": "submit"}, admin=admin)
    group = svc.statistics(db_session, admin)["groups"]["human"]
    assert group["interrupted_sessions"] == 1 and group["active_sessions"] == 1
    clock(1813)
    group = svc.statistics(db_session, admin)["groups"]["human"]
    assert group["interrupted_sessions"] == 2 and group["active_sessions"] == 0
    new = svc.start(db_session, two.id, {"mode": "human"}, admin=admin)
    assert new["session_id"] != old["session_id"]

def test_cross_account_and_cross_candidate_rejected(db_session, admin, telemetry):
    one, two = candidate(db_session), candidate(db_session)
    svc = telemetry.ReviewTelemetryService
    session = svc.start(db_session, one.id, {"mode": "human"}, admin=admin)
    other = User(email="other-timing@example.test", username="other-timing", hashed_password="unused", is_admin=True)
    db_session.add(other)
    db_session.commit()
    with pytest.raises(HTTPException) as err:
        svc.event(db_session, one.id, {"session_id": session["session_id"], "event": "submit"}, admin=other)
    assert err.value.status_code == 403
    with pytest.raises(HTTPException) as err:
        svc.event(db_session, two.id, {"session_id": session["session_id"], "event": "submit"}, admin=admin)
    assert err.value.status_code == 409
    assert svc.statistics(db_session, other)["groups"]["human"]["active_sessions"] == 0

@pytest.mark.parametrize("payload", [{}, {"mode": "robot"}, {"mode": "human", "elapsed_seconds": 1},
    {"mode": "human", "reviewer_id": 1}, {"mode": "human", "started_at": "2020-01-01"}])
def test_forged_start_measurements_rejected(db_session, admin, telemetry, payload):
    row = candidate(db_session)
    with pytest.raises(HTTPException) as err:
        telemetry.ReviewTelemetryService.start(db_session, row.id, payload, admin=admin)
    assert err.value.status_code == 422 and not logs(db_session)

@pytest.mark.parametrize("extra", [{"event": "complete"}, {"event": "submit", "mode": "human"},
    {"event": "submit", "elapsed_seconds": 1}, {"event": "source_open", "proposal_id": "missing"},
    {"event": "decision", "field_name": "organizer", "decision": "approve"}])
def test_invalid_events_rejected_without_audit(db_session, admin, telemetry, extra):
    row = candidate(db_session)
    svc = telemetry.ReviewTelemetryService
    session = svc.start(db_session, row.id, {"mode": "human"}, admin=admin)
    with pytest.raises(HTTPException) as err:
        svc.event(db_session, row.id, {"session_id": session["session_id"], **extra}, admin=admin)
    assert err.value.status_code == 422 and len(logs(db_session)) == 1

def test_persisted_admin_and_candidate_required(db_session, admin, telemetry):
    row = candidate(db_session)
    svc = telemetry.ReviewTelemetryService
    for fake in [SimpleNamespace(id=admin.id, is_admin=True), User(id=admin.id, is_admin=True)]:
        with pytest.raises(HTTPException) as err:
            svc.start(db_session, row.id, {"mode": "human"}, admin=fake)
        assert err.value.status_code == 403
    db_session.execute(User.__table__.update().where(User.id == admin.id).values(is_admin=False))
    with pytest.raises(HTTPException) as err:
        svc.statistics(db_session, admin)
    assert err.value.status_code == 403
    db_session.rollback()
    with pytest.raises(HTTPException) as err:
        svc.start(db_session, 99999, {"mode": "human"}, admin=admin)
    assert err.value.status_code == 404

def test_failure_and_outer_rollback_do_not_count_completion(db_session, admin, telemetry, clock):
    row = candidate(db_session)
    svc = telemetry.ReviewTelemetryService
    svc.start(db_session, row.id, {"mode": "human"}, admin=admin)
    db_session.commit()
    before = Fields.detail(db_session, row.id)
    assert not svc.complete(db_session, row.id, admin.id, "approve")["recorded"]
    with pytest.raises(HTTPException):
        Fields.review(db_session, row.id, {"preview_token": "stale", "note": "failed",
            "decisions": [{"field_name": "description", "action": "reject"}]}, admin=admin)
    assert svc.statistics(db_session, admin)["groups"]["human"]["completed_samples"] == 0
    clock(10)
    decide(db_session, row, admin)
    svc.complete(db_session, row.id, admin.id, "reject")
    assert svc.statistics(db_session, admin)["groups"]["human"]["completed_samples"] == 1
    db_session.rollback()
    assert Fields.detail(db_session, row.id)["preview_token"] == before["preview_token"]
    assert svc.statistics(db_session, admin)["groups"]["human"]["completed_samples"] == 0

def test_status_without_audit_cannot_fake_success(db_session, admin, telemetry):
    row = candidate(db_session)
    svc = telemetry.ReviewTelemetryService
    svc.start(db_session, row.id, {"mode": "human"}, admin=admin)
    row.status = "rejected"
    db_session.flush()
    assert not svc.complete(db_session, row.id, admin.id, "reject")["recorded"]
    assert svc.statistics(db_session, admin)["groups"]["human"]["completed_samples"] == 0

def test_empty_and_zero_duration_not_infinite_capacity(db_session, admin, telemetry, clock):
    svc = telemetry.ReviewTelemetryService
    group = svc.statistics(db_session, admin)["groups"]["human"]
    assert group["completed_samples"] == 0
    assert group["mean_seconds"] is None and group["p90_seconds"] is None and group["theoretical_per_hour"] is None
    row = candidate(db_session)
    svc.start(db_session, row.id, {"mode": "human"}, admin=admin)
    decide(db_session, row, admin)
    svc.complete(db_session, row.id, admin.id, "reject")
    assert svc.statistics(db_session, admin)["groups"]["human"]["theoretical_per_hour"] is None

def test_batch_is_one_wall_clock_sample_and_counts_members_once(db_session, admin, telemetry, clock):
    one, two = candidate(db_session), candidate(db_session)
    svc = telemetry.ReviewTelemetryService
    session = svc.start(db_session, one.id, {"mode": "human", "candidate_ids": [one.id, two.id]}, admin=admin)
    assert session["sample_type"] == "batch" and session["candidate_ids"] == [one.id, two.id]
    clock(10)
    decide(db_session, one, admin)
    assert not svc.complete(db_session, one.id, admin.id, "reject")["recorded"]
    clock(20)
    decide(db_session, two, admin)
    result = svc.complete(db_session, two.id, admin.id, "reject")
    assert result["session"]["elapsed_seconds"] == 20
    stats = svc.statistics(db_session, admin)["groups"]["human"]
    assert stats["completed_samples"] == 1 and stats["completed_candidates"] == 2
    assert stats["by_sample_type"]["batch"]["theoretical_per_hour"] == 360
    assert stats["by_sample_type"]["single"]["completed_samples"] == 0
    assert len([a for a in logs(db_session) if a.action == "review_telemetry_complete"]) == 1

@pytest.mark.parametrize("ids", [[2, 1], [1, 1], [1, 99999], list(range(1, 52))])
def test_invalid_batch_members_rejected(db_session, admin, telemetry, ids):
    row = candidate(db_session)
    with pytest.raises(HTTPException):
        telemetry.ReviewTelemetryService.start(db_session, row.id, {"mode": "human", "candidate_ids": ids}, admin=admin)
    assert not logs(db_session)


def test_relation_deferred_status_stays_reviewable_without_completion(db_session, admin, telemetry):
    row = candidate(db_session, 0)
    row.status = "deferred"
    db_session.commit()
    svc = telemetry.ReviewTelemetryService
    session = svc.start(db_session, row.id, {"mode": "human"}, admin=admin)
    result = svc.event(db_session, row.id, {"session_id": session["session_id"], "event": "decision",
        "decision": "defer"}, admin=admin)
    assert result["status"] == "active"
    assert not svc.complete(db_session, row.id, admin.id, "defer")["recorded"]


def test_other_reviewer_final_decision_does_not_complete_earlier_reviewers_clock(db_session, admin, telemetry, clock):
    row = candidate(db_session, 2)
    svc = telemetry.ReviewTelemetryService
    svc.start(db_session, row.id, {"mode": "human"}, admin=admin)
    decide(db_session, row, admin, ["description"])
    other = User(email="final-timing@example.test", username="final-timing", hashed_password="unused", is_admin=True)
    db_session.add(other)
    db_session.commit()
    clock(5)
    decide(db_session, row, other, ["short_name"])
    result = svc.complete(db_session, row.id, admin.id, "reject")
    assert not result["recorded"]
    stats = svc.statistics(db_session, admin)["groups"]["human"]
    assert stats["completed_samples"] == 0 and stats["interrupted_sessions"] == 1
    assert stats["active_sessions"] == 0


def test_no_source_snapshot_does_not_count_placeholder_dictionary(db_session, admin, telemetry):
    row = Fields.create_candidate(db_session, dict(entity_type="competition", competition_id=1,
        title="No source", fields=[{"field_name": "description", "candidate_value": "Pending"}]))
    db_session.commit()
    session = telemetry.ReviewTelemetryService.start(db_session, row.id, {"mode": "automation"}, admin=admin)
    assert session["candidate_snapshots"][0]["source_count"] == 0


def test_batch_completion_rolls_back_with_all_review_members(db_session, admin, telemetry, clock):
    one, two = candidate(db_session), candidate(db_session)
    svc = telemetry.ReviewTelemetryService
    svc.start(db_session, one.id, {"mode": "automation", "candidate_ids": [one.id, two.id]}, admin=admin)
    db_session.commit()
    clock(10)
    decide(db_session, one, admin)
    svc.complete(db_session, one.id, admin.id, "reject")
    decide(db_session, two, admin)
    svc.complete(db_session, two.id, admin.id, "reject")
    assert svc.statistics(db_session, admin)["groups"]["automation"]["completed_candidates"] == 2
    db_session.rollback()
    assert Fields.detail(db_session, one.id)["status"] == "pending"
    assert Fields.detail(db_session, two.id)["status"] == "pending"
    assert svc.statistics(db_session, admin)["groups"]["automation"]["completed_candidates"] == 0


def test_school_mapping_snapshot_counts_its_original_source(db_session, admin, telemetry):
    import json
    row = candidate(db_session, 0)
    doc = json.loads(row.raw_value)
    doc["collection_context"] = {"kind": "school_mapping", "source_url": "https://example.edu/notice",
        "source_title": "School notice", "publisher": "Academic office"}
    row.raw_value = json.dumps(doc)
    db_session.commit()
    opened = telemetry.ReviewTelemetryService.start(db_session, row.id, {"mode": "human"}, admin=admin)
    assert opened["candidate_snapshots"][0]["kind"] == "school_mapping"
    assert opened["candidate_snapshots"][0]["source_count"] == 1


def test_reopen_partly_completed_batch_resumes_original_wall_clock(db_session, admin, telemetry, clock):
    one, two = candidate(db_session), candidate(db_session)
    svc = telemetry.ReviewTelemetryService
    payload = {"mode": "human", "candidate_ids": [one.id, two.id]}
    original = svc.start(db_session, one.id, payload, admin=admin)
    clock(10)
    decide(db_session, one, admin)
    svc.complete(db_session, one.id, admin.id, "reject")
    db_session.commit()
    clock(12)
    reopened = svc.start(db_session, one.id, payload, admin=admin)
    assert reopened["session_id"] == original["session_id"] and reopened["resumed"]
    assert reopened["elapsed_seconds"] == 12
    clock(20)
    decide(db_session, two, admin)
    result = svc.complete(db_session, two.id, admin.id, "reject")
    assert result["session"]["elapsed_seconds"] == 20


def test_concurrent_open_creates_one_session_in_isolated_sqlite(tmp_path, telemetry):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database.base import Base
    engine = create_engine("sqlite:///" + (tmp_path / "telemetry-race.sqlite").as_posix(),
        connect_args={"check_same_thread": False, "timeout": 10})
    factory = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(engine)
    try:
        with factory() as db:
            user = User(email="race@example.test", username="race", hashed_password="unused", is_admin=True)
            db.add(user)
            row = Fields.create_candidate(db, {"entity_type": "competition", "title": "Race", "fields": []})
            db.commit()
            uid, cid = user.id, row.id
        barrier = Barrier(2)
        def open_session():
            with factory() as db:
                actor = db.get(User, uid)
                barrier.wait(timeout=5)
                result = telemetry.ReviewTelemetryService.start(db, cid, {"mode": "human"}, admin=actor)
                db.commit()
                return result["session_id"]
        with ThreadPoolExecutor(max_workers=2) as executor:
            first, second = executor.submit(open_session), executor.submit(open_session)
            assert first.result(timeout=15) == second.result(timeout=15)
        with factory() as db:
            assert len([a for a in logs(db) if a.action == "review_telemetry_start"]) == 1
    finally:
        engine.dispose()


def test_origin_link_duplicate_is_one_source_in_complexity_snapshot(db_session, admin, telemetry):
    row = candidate(db_session)
    row.source_url = "https://example.test/rules"
    db_session.commit()
    opened = telemetry.ReviewTelemetryService.start(db_session, row.id, {"mode": "human"}, admin=admin)
    assert opened["candidate_snapshots"][0]["source_count"] == 1
