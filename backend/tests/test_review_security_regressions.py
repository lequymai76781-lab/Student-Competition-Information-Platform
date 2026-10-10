"""Real-token privacy, atomic review, stale-state and pagination regressions."""
from datetime import datetime, timezone
import sqlite3

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.routes import admin as admin_routes
from app.core.config import get_settings
from app.core.ratelimit import _store
from app.core.security import create_token
from app.main import app
from app.models import (AdminAuditLog, BetaFeedback, CandidateFact, Competition, CompetitionEdition,
                        CompetitionFactRevision, CompetitionFactSource, CompetitionLead, CompetitionUpdateEvent,
                        Favorite, Notification, ReviewQueue, User, UserCorrectionSubmission)
from app.schemas.field_review import FieldReviewIn
from app.services import field_review_service
from app.services.field_review_service import FieldReviewService

STAMP = datetime(2026, 9, 1, tzinfo=timezone.utc)
STATUSES = ["pending", "needs_more_evidence", "approved", "rejected", "duplicate", "verified_pending_import"]
ADMIN_LISTS = ["corrections", "supplements", "leads", "candidate-facts", "updates", "feedback"]
PAGED_PATHS = [f"/api/admin/review/{name}" for name in ADMIN_LISTS] + [
    "/api/users/me/corrections", "/api/users/me/supplements", "/api/v0.2/policies/review-queue"]


@pytest.fixture()
def actors(db_session):
    _store.clear()
    users = {name: User(email=f"{name}@security.test", username=f"security-{name}",
                        hashed_password="unused", is_admin=name == "admin")
             for name in ("a", "b", "admin")}
    db_session.add_all(users.values())
    db_session.commit()
    return {name: (user.id, {"Authorization": "Bearer " + create_token(user.id, get_settings().app_secret)})
            for name, user in users.items()}


def correction(db, owner, status="pending", *, deadline=False):
    row = UserCorrectionSubmission(user_id=owner, competition_id=1, competition_edition_id=1,
        correction_type="报名截止错误" if deadline else "信息错误", description="PRIVATE_CORRECTION",
        source_url="https://example.test/private-source", contact_note="PRIVATE_CONTACT",
        status=status, review_note="PRIVATE_REVIEW_NOTE", created_at=STAMP)
    db.add(row)
    db.flush()
    queue = ReviewQueue(item_type="user_correction", item_id=row.id, reason="private",
        evidence_text=row.description, status=status, reviewer_notes=row.review_note, created_at=STAMP)
    db.add(queue)
    db.flush()
    return row, queue


def supplement(db, owner, status="pending"):
    feedback = BetaFeedback(user_id=owner, category="数据补充", content="PRIVATE_SUPPLEMENT",
                            status=status, created_at=STAMP)
    db.add(feedback)
    db.flush()
    queue = ReviewQueue(item_type="user_supplement", item_id=feedback.id, reason="private",
        suggested_value="competition", evidence_text=feedback.content, source_url="https://example.test/private",
        status=status, reviewer_notes="PRIVATE_REVIEW_NOTE", created_at=STAMP)
    db.add(queue)
    db.flush()
    return queue, feedback


def ready_field_review(client, headers, kind, origin_id):
    response = client.post(f"/api/admin/field-review-origins/{kind}/{origin_id}", headers=headers)
    assert response.status_code == 200, response.text
    field_id = response.json()["data"]["field_review_id"]
    response = client.get(f"/api/admin/field-reviews/{field_id}", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    if not data["fields"]:
        body = {"preview_token": data["preview_token"], "title": "待人工审核字段", "entity_type": "edition" if kind == "correction" else "competition",
            "competition_id": 1 if kind == "correction" else None, "edition_id": 1 if kind == "correction" else None,
            "fields": [{"field_name": "official_registration_deadline" if kind == "correction" else "name",
                "candidate_value": "2026-10-06T15:59:59Z" if kind == "correction" else "待审核新赛事",
                "source": {"source_type": "organizer_notice", "source_url": "https://example.test/verified-source"}}]}
        response = client.put(f"/api/admin/field-reviews/{field_id}/prepare", headers=headers, json=body)
        assert response.status_code == 200, response.text
        data = response.json()["data"]
    for field in data["fields"]:
        for proposal in field["proposals"]:
            response = client.post(f"/api/admin/field-reviews/{field_id}/sources/{proposal['id']}/verify", headers=headers,
                json={"preview_token": data["preview_token"], "note": "先行核验来源"})
            assert response.status_code == 200, response.text
            data = response.json()["data"]
    return data


def field_decision(data, decision, note="verified"):
    field = data["fields"][0]
    return {"preview_token": data["preview_token"], "note": note, "decisions": [{
        "field_name": field["field_name"], "action": "approve" if decision == "approved" else "reject",
        "proposal_id": field["proposals"][0]["id"] if decision == "approved" else None,
    }]}


@pytest.mark.parametrize("status", STATUSES + [""])
@pytest.mark.parametrize("actor", [None, "a", "b"])
def test_legacy_queue_blocks_private_data_in_every_state(client, db_session, actors, status, actor):
    for state in STATUSES:
        correction(db_session, actors["a"][0], state)
        supplement(db_session, actors["a"][0], state)
    db_session.commit()
    response = client.get("/api/v0.2/policies/review-queue", params={"status": status},
                          headers={} if actor is None else actors[actor][1])
    assert response.status_code in {401, 403}
    assert "PRIVATE_" not in response.text


@pytest.mark.parametrize("path", PAGED_PATHS + ["/api/admin/review/summary", "/api/admin/field-reviews", "/api/admin/field-reviews/config"])
def test_private_reads_require_real_authorization(client, actors, path):
    assert client.get(path).status_code in {401, 403}
    if "/admin/" in path or "/v0.2/" in path:
        for actor in ("a", "b"):
            assert client.get(path, headers=actors[actor][1]).status_code == 403
    assert client.get(path, headers=actors["admin"][1]).status_code == 200


def test_owner_history_and_review_writes_are_isolated(client, db_session, actors):
    row, queue = correction(db_session, actors["a"][0])
    sup, feedback = supplement(db_session, actors["a"][0])
    db_session.commit()
    for kind, expected_id in (("corrections", row.id), ("supplements", sup.id)):
        path = f"/api/users/me/{kind}"
        own = client.get(path, headers=actors["a"][1]).json()["data"]
        assert [item["id"] for item in own] == [expected_id]
        assert own[0]["review_note"] == "PRIVATE_REVIEW_NOTE"
        assert client.get(path, headers=actors["b"][1], params={"user_id": actors["a"][0]}).json()["data"] == []
        for header in ({}, actors["a"][1], actors["b"][1]):
            result = client.put(f"/api/admin/review/{kind}/{expected_id}", headers=header,
                                json={"status": "rejected", "note": "PRIVATE_REVIEW_NOTE"})
            assert result.status_code in {401, 403}
    assert client.put(f"/api/admin/review/feedback/{feedback.id}", headers=actors["b"][1],
                      json={"status": "approved"}).status_code == 403
    for kind, identity in (("correction", row.id), ("supplement", sup.id)):
        for header in ({}, actors["a"][1], actors["b"][1]):
            result = client.post(f"/api/admin/field-review-origins/{kind}/{identity}", headers=header)
            assert result.status_code in {401, 403}
            assert "PRIVATE_" not in result.text
    db_session.expire_all()
    assert row.status == queue.status == sup.status == feedback.status == "pending"


@pytest.mark.parametrize("actor", ["a", "admin"])
def test_inactive_token_cannot_read_or_review(client, db_session, actors, actor):
    user = db_session.get(User, actors[actor][0])
    user.is_active = False
    db_session.commit()
    for path in ("/api/users/me/corrections", "/api/users/me/supplements", "/api/admin/review/supplements",
                 "/api/v0.2/policies/review-queue"):
        assert client.get(path, headers=actors[actor][1]).status_code in {401, 403}
    assert client.put("/api/admin/review/supplements/1", headers=actors[actor][1],
                      json={"status": "rejected", "note": "inactive"}).status_code in {401, 403}


@pytest.mark.parametrize("kind", ["corrections", "supplements"])
def test_submission_cannot_spoof_owner_admin_or_approval(client, actors, kind):
    body = {"user_id": actors["b"][0], "is_admin": True, "status": "approved",
            "description": "PRIVATE_SUBMISSION", "title": "Private title", "kind": "competition",
            "competition_id": 1, "correction_type": "信息错误"}
    response = client.post(f"/api/users/me/{kind}", headers=actors["a"][1], json=body)
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "pending"
    assert len(client.get(f"/api/users/me/{kind}", headers=actors["a"][1]).json()["data"]) == 1
    assert client.get(f"/api/users/me/{kind}", headers=actors["b"][1]).json()["data"] == []


def seed_page(db, name, owner, count):
    ids = []
    for index in range(count):
        if name == "corrections":
            row, _ = correction(db, owner)
        elif name == "supplements":
            row, _ = supplement(db, owner)
        elif name == "review-queue":
            row = ReviewQueue(item_type="policy", reason=f"reason-{index}", created_at=STAMP)
        elif name == "leads":
            row = CompetitionLead(raw_title=f"lead-{index}", source_type="official",
                                  source_url=f"https://example.test/{index}", discovered_at=STAMP)
        elif name == "candidate-facts":
            row = CandidateFact(field_name="name", candidate_value=str(index), source_type="official",
                                source_url=f"https://example.test/{index}", reliability_tier=1, created_at=STAMP)
        elif name == "updates":
            row = CompetitionUpdateEvent(competition_id=1, event_type="deadline_changed",
                source_url=f"https://example.test/{index}", changed_at=STAMP, observed_at=STAMP)
        else:
            row = BetaFeedback(user_id=owner, category="其他", content=f"feedback-{index}", created_at=STAMP)
        db.add(row)
        db.flush()
        ids.append(row.id)
    return list(reversed(ids))


@pytest.mark.parametrize("count", [0, 1, 49, 50, 51, 101])
@pytest.mark.parametrize("path", PAGED_PATHS)
def test_pages_reach_every_row_with_stable_ties_and_owner_filter(client, db_session, actors, path, count):
    name = path.rsplit("/", 1)[1]
    expected = seed_page(db_session, name, actors["a"][0], count)
    if "/users/" in path:
        seed_page(db_session, name, actors["b"][0], 3)
    db_session.commit()
    header = actors["a" if "/users/" in path else "admin"][1]
    visible = []
    for offset in range(0, count + 1, 20):
        response = client.get(path, headers=header, params={"limit": 21, "offset": offset})
        assert response.status_code == 200
        page = [row["id"] for row in response.json()["data"]]
        assert page == expected[offset:offset + 21]
        visible.extend(page[:20])
    assert visible == expected
    default = client.get(path, headers=header).json()["data"]
    assert [row["id"] for row in default] == expected[:50]


@pytest.mark.parametrize("path", PAGED_PATHS)
@pytest.mark.parametrize("query", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
def test_pagination_rejects_invalid_bounds(client, actors, path, query):
    assert client.get(path, headers=actors["admin"][1], params=query).status_code == 422


def test_supplement_filters_keep_unfinished_reachable_after_50_verified(client, db_session, actors):
    pending, _ = supplement(db_session, actors["a"][0])
    evidence, _ = supplement(db_session, actors["a"][0], "needs_more_evidence")
    for _ in range(50):
        supplement(db_session, actors["a"][0], "verified_pending_import")
    rejected, _ = supplement(db_session, actors["a"][0], "rejected")
    db_session.commit()
    path = "/api/admin/review/supplements"
    header = actors["admin"][1]
    assert [r["id"] for r in client.get(path, headers=header).json()["data"]] == [evidence.id, pending.id]
    assert [r["id"] for r in client.get(path, headers=header, params={"status": "rejected"}).json()["data"]] == [rejected.id]
    assert len(client.get(path, headers=header, params={"status": "all", "limit": 100}).json()["data"]) == 53
    assert len(client.get(path, headers=header, params={"status": "verified_pending_import"}).json()["data"]) == 50
    assert client.get(path, headers=header, params={"status": "invalid"}).status_code == 422


def test_corrections_unfinished_retains_needs_more_evidence(client, db_session, actors):
    pending, _ = correction(db_session, actors["a"][0])
    evidence, _ = correction(db_session, actors["a"][0], "needs_more_evidence")
    correction(db_session, actors["a"][0], "approved")
    db_session.commit()
    result = client.get("/api/admin/review/corrections", headers=actors["admin"][1], params={"status": "unfinished"})
    assert [r["id"] for r in result.json()["data"]] == [evidence.id, pending.id]


@pytest.mark.parametrize("decision", ["approved", "rejected"])
@pytest.mark.parametrize("failure", ["audit", "database", "commit"])
def test_correction_failure_rolls_back_every_table_and_allows_retry(client, db_session, actors, monkeypatch, decision, failure):
    row, queue = correction(db_session, actors["a"][0], deadline=True)
    db_session.add(Favorite(user_id=actors["a"][0], competition_id=1))
    db_session.commit()
    row_id, queue_id = row.id, queue.id
    old_deadline = db_session.get(CompetitionEdition, 1).official_registration_deadline
    data = ready_field_review(client, actors["admin"][1], "correction", row_id)
    field_id = data["id"]
    audit_before = db_session.scalar(select(func.count()).select_from(AdminAuditLog))
    def fail(*args, **kwargs):
        if failure == "database":
            db_session.add(AdminAuditLog(action=None, object_type="private", created_at=STAMP))
            db_session.flush()
        raise OperationalError("PRIVATE_SQL", {"private": "PRIVATE_PARAMETER"}, Exception("PRIVATE_DB_PATH"))
    with monkeypatch.context() as patch:
        patch.setattr(db_session if failure == "commit" else field_review_service,
                      "commit" if failure == "commit" else "_history", fail)
        with TestClient(app, raise_server_exceptions=False) as safe_client:
            result = safe_client.post(f"/api/admin/field-reviews/{field_id}/review", headers=actors["admin"][1],
                json=field_decision(data, decision))
        assert result.status_code == 500
        assert db_session.is_active
        with Session(db_session.get_bind()) as fresh:
            assert fresh.get(UserCorrectionSubmission, row_id).status == "pending"
            assert fresh.get(ReviewQueue, queue_id).status == "pending"
            assert fresh.get(ReviewQueue, field_id).status == "pending"
            assert fresh.get(CompetitionEdition, 1).official_registration_deadline == old_deadline
            for model in (CompetitionFactSource, CompetitionFactRevision, CompetitionUpdateEvent, Notification):
                assert fresh.scalar(select(func.count()).select_from(model)) == 0
            assert fresh.scalar(select(func.count()).select_from(AdminAuditLog)) == audit_before
        assert "PRIVATE_" not in result.text
    result = client.post(f"/api/admin/field-reviews/{field_id}/review", headers=actors["admin"][1], json=field_decision(data, decision))
    assert result.status_code == 200, result.text
    for repeated in ("approved", "rejected"):
        assert client.post(f"/api/admin/field-reviews/{field_id}/review", headers=actors["admin"][1],
                           json=field_decision(data, repeated)).status_code == 409
        assert client.put(f"/api/admin/review/corrections/{row_id}", headers=actors["admin"][1],
                          json={"status": repeated}).status_code == 409
    with Session(db_session.get_bind()) as fresh:
        assert fresh.get(UserCorrectionSubmission, row_id).status == fresh.get(ReviewQueue, queue_id).status == decision
        assert fresh.get(ReviewQueue, field_id).status == decision
        for model in (CompetitionFactSource, CompetitionFactRevision, CompetitionUpdateEvent, Notification):
            assert fresh.scalar(select(func.count()).select_from(model)) == (1 if decision == "approved" else 0)
        assert fresh.scalar(select(func.count()).select_from(AdminAuditLog)) == audit_before + 1


@pytest.mark.parametrize("decision", ["approved", "rejected"])
@pytest.mark.parametrize("failure", ["audit", "database", "commit"])
def test_supplement_failure_rolls_back_queue_feedback_and_audit(client, db_session, actors, monkeypatch, decision, failure):
    row, feedback = supplement(db_session, actors["a"][0])
    db_session.commit()
    row_id, feedback_id = row.id, feedback.id
    data = ready_field_review(client, actors["admin"][1], "supplement", row_id)
    field_id = data["id"]
    audit_before = db_session.scalar(select(func.count()).select_from(AdminAuditLog))
    competitions_before = db_session.scalar(select(func.count()).select_from(Competition))
    def fail(*args, **kwargs):
        if failure == "database":
            db_session.add(AdminAuditLog(action=None, object_type="private", created_at=STAMP))
            db_session.flush()
        raise RuntimeError("PRIVATE_AUDIT_FAILURE")
    with monkeypatch.context() as patch:
        patch.setattr(db_session if failure == "commit" else field_review_service,
                      "commit" if failure == "commit" else "_history", fail)
        with TestClient(app, raise_server_exceptions=False) as safe_client:
            result = safe_client.post(f"/api/admin/field-reviews/{field_id}/review", headers=actors["admin"][1],
                                   json=field_decision(data, decision))
        assert result.status_code == 500
        assert db_session.is_active
        assert not db_session.dirty
        with Session(db_session.get_bind()) as fresh:
            assert fresh.get(ReviewQueue, row_id).status == fresh.get(BetaFeedback, feedback_id).status == "pending"
            assert fresh.get(ReviewQueue, field_id).status == "pending"
            assert fresh.scalar(select(func.count()).select_from(AdminAuditLog)) == audit_before
            assert fresh.scalar(select(func.count()).select_from(CompetitionFactRevision)) == 0
            assert fresh.scalar(select(func.count()).select_from(CompetitionFactSource)) == 0
            assert fresh.scalar(select(func.count()).select_from(CompetitionUpdateEvent)) == 0
            assert fresh.scalar(select(func.count()).select_from(Competition)) == competitions_before
        assert "PRIVATE_" not in result.text
    assert client.post(f"/api/admin/field-reviews/{field_id}/review", headers=actors["admin"][1],
                      json=field_decision(data, decision)).status_code == 200
    assert client.post(f"/api/admin/field-reviews/{field_id}/review", headers=actors["admin"][1],
                      json=field_decision(data, decision)).status_code == 409
    assert client.put(f"/api/admin/review/supplements/{row_id}", headers=actors["admin"][1],
                      json={"status": "verified_pending_import", "note": "verified"}).status_code == 409
    with Session(db_session.get_bind()) as fresh:
        assert fresh.get(ReviewQueue, row_id).status == fresh.get(BetaFeedback, feedback_id).status == decision
        assert fresh.scalar(select(func.count()).select_from(Competition)) == competitions_before + (decision == "approved")
        assert fresh.scalar(select(func.count()).select_from(AdminAuditLog)) == audit_before + 1


@pytest.mark.parametrize("kind", ["correction", "supplement"])
def test_stale_reviewer_cannot_overwrite_a_terminal_decision(client, db_session, actors, kind, tmp_path):
    if kind == "correction":
        row, queue = correction(db_session, actors["a"][0])
        origin_model = UserCorrectionSubmission
        linked_model, linked_id = ReviewQueue, queue.id
    else:
        row, feedback = supplement(db_session, actors["a"][0])
        origin_model = ReviewQueue
        linked_model, linked_id = BetaFeedback, feedback.id
    db_session.commit()
    row_id = row.id
    data = ready_field_review(client, actors["admin"][1], kind, row_id)
    field_id = data["id"]
    audit_before = db_session.scalar(select(func.count()).select_from(AdminAuditLog))
    db_session.commit()
    # Clone only the seeded in-memory fixture, so reviewers use separate real DB connections.
    copied_path = tmp_path / "concurrent-review.sqlite"
    raw = db_session.get_bind().raw_connection()
    try:
        with sqlite3.connect(copied_path) as destination:
            raw.driver_connection.backup(destination)
    finally:
        raw.close()
    engine = create_engine(f"sqlite:///{copied_path.as_posix()}")
    try:
        with Session(engine, autoflush=False) as stale, Session(engine, autoflush=False) as first:
            held_snapshot = stale.get(ReviewQueue, field_id)
            stale_admin = stale.get(User, actors["admin"][0])
            reviewer = first.get(User, actors["admin"][0])
            FieldReviewService.review(first, field_id, FieldReviewIn(**field_decision(data, "rejected", "first decision")), admin=reviewer)
            first.commit()
            assert held_snapshot.status == "pending"
            with pytest.raises(HTTPException) as conflict:
                FieldReviewService.review(stale, field_id, FieldReviewIn(**field_decision(data, "approved", "stale decision")), admin=stale_admin)
            assert conflict.value.status_code == 409
        with Session(engine) as fresh:
            assert fresh.get(origin_model, row_id).status == fresh.get(linked_model, linked_id).status == "rejected"
            assert fresh.get(ReviewQueue, field_id).status == "rejected"
            assert fresh.scalar(select(func.count()).select_from(AdminAuditLog)) == audit_before + 1
    finally:
        engine.dispose()


@pytest.mark.parametrize("kind", ["corrections", "supplements"])
def test_needs_more_evidence_can_be_migrated_and_reviewed_again(client, db_session, actors, kind):
    if kind == "corrections":
        row, _ = correction(db_session, actors["a"][0], "needs_more_evidence")
        origin = "correction"
    else:
        row, _ = supplement(db_session, actors["a"][0], "needs_more_evidence")
        origin = "supplement"
    db_session.commit()
    assert row.status == "needs_more_evidence"
    data = ready_field_review(client, actors["admin"][1], origin, row.id)
    response = client.post(f"/api/admin/field-reviews/{data['id']}/review", headers=actors["admin"][1],
        json=field_decision(data, "approved", "补齐并核验来源后再次审核"))
    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == row.status == "approved"
    assert db_session.scalar(select(func.count()).select_from(AdminAuditLog).where(AdminAuditLog.action == "field_review")) == 1


@pytest.mark.parametrize("decision", ["rejected", "needs_more_evidence"])
@pytest.mark.parametrize("failure", ["audit", "database", "commit"])
def test_unlinked_correction_legacy_nonapproval_is_atomic(client, db_session, actors, monkeypatch, decision, failure):
    """Legacy nonapproval remains available until explicit candidate transfer."""
    row, queue = correction(db_session, actors["a"][0], deadline=True)
    db_session.commit()
    row_id, queue_id = row.id, queue.id
    old_deadline = db_session.get(CompetitionEdition, 1).official_registration_deadline
    def fail(*args, **kwargs):
        if failure == "database":
            db_session.add(AdminAuditLog(action=None, object_type="private", created_at=STAMP))
            db_session.flush()
        raise RuntimeError("PRIVATE_LEGACY_REVIEW_FAILURE")
    with monkeypatch.context() as patch:
        patch.setattr(db_session if failure == "commit" else admin_routes,
            "commit" if failure == "commit" else "record_admin_action", fail)
        with TestClient(app, raise_server_exceptions=False) as safe_client:
            response = safe_client.put(f"/api/admin/review/corrections/{row_id}", headers=actors["admin"][1],
                json={"status": decision, "note": "PRIVATE_REVIEW_NOTE"})
        assert response.status_code == 500
        assert "PRIVATE_" not in response.text
        assert db_session.is_active
        with Session(db_session.get_bind()) as fresh:
            assert fresh.get(UserCorrectionSubmission, row_id).status == fresh.get(ReviewQueue, queue_id).status == "pending"
            assert fresh.get(CompetitionEdition, 1).official_registration_deadline == old_deadline
            for model in (AdminAuditLog, CompetitionFactRevision, CompetitionUpdateEvent):
                assert fresh.scalar(select(func.count()).select_from(model)) == 0
    response = client.put(f"/api/admin/review/corrections/{row_id}", headers=actors["admin"][1],
        json={"status": decision, "note": "PRIVATE_REVIEW_NOTE"})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == decision
    assert client.put(f"/api/admin/review/corrections/{row_id}", headers=actors["admin"][1],
        json={"status": "approved", "new_deadline": "2026-10-06T15:59:59Z"}).status_code == 409
    assert db_session.get(UserCorrectionSubmission, row_id).status == decision
