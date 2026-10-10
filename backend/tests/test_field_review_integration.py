"""Public inputs and legacy mutations must enter the field review workflow."""
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Event, current_thread

import pytest
from sqlalchemy import create_engine, func, select

from app.api.deps import _current_user
from app.core.ratelimit import _store
from app.main import app
from app.models import BetaFeedback, Competition, CompetitionEdition, ReviewQueue, User, UserCorrectionSubmission
from conftest import temporary_dependency_override


@pytest.fixture
def actor(db_session):
    _store.clear()
    user = User(email="field-origin@test.invalid", username="field-origin", hashed_password="fixture")
    db_session.add(user)
    db_session.commit()
    with temporary_dependency_override(app, _current_user, lambda: user):
        yield user


def correction(client, **extra):
    return client.post("/api/users/me/corrections", json={
        "competition_id": 1, "competition_edition_id": 1, "correction_type": "报名截止错误",
        "description": "官方通知说明报名延期", "source_url": "https://example.edu.cn/notice",
        **extra,
    })


def test_structured_user_deadline_is_unverified_candidate_only(client, db_session, actor):
    old = db_session.get(CompetitionEdition, 1).official_registration_deadline
    response = correction(client, proposed_value="2026-10-30T23:59:59+08:00")
    assert response.status_code == 200
    review_id = response.json()["data"]["field_review_id"]
    queue = db_session.get(ReviewQueue, review_id)
    assert queue.item_type == "field_candidate"
    assert db_session.get(CompetitionEdition, 1).official_registration_deadline == old
    actor.is_admin = True
    db_session.commit()
    detail = client.get(f"/api/admin/field-reviews/{review_id}").json()["data"]
    field = detail["fields"][0]
    assert field["field_name"] == "official_registration_deadline"
    assert field["verification_state"] == "UNVERIFIED"
    assert detail["edition_id"] == 1
    assert field["proposals"][0]["source"]["verified_by"] is None


def test_free_text_correction_stays_unstructured_until_admin_prepares(client, db_session, actor):
    response = correction(client)
    assert response.status_code == 200
    review_id = response.json()["data"]["field_review_id"]
    actor.is_admin = True
    db_session.commit()
    detail = client.get(f"/api/admin/field-reviews/{review_id}").json()["data"]
    assert detail["fields"] == []
    assert detail["description"] == "官方通知说明报名延期"
    assert client.put(f'/api/admin/review/corrections/{response.json()["data"]["id"]}',
                      json={"status": "approved", "new_deadline": "2026-10-30T15:59:59Z"}).status_code == 409


def test_new_competition_supplement_creates_name_candidate_without_official_row(client, db_session, actor):
    count = db_session.scalar(select(func.count()).select_from(Competition))
    response = client.post("/api/users/me/supplements", json={"kind": "competition", "title": "未收录竞赛候选",
        "description": "请核对该赛事是否可以收录", "source_url": "https://example.test/competition"})
    assert response.status_code == 200
    review_id = response.json()["data"]["field_review_id"]
    assert db_session.scalar(select(func.count()).select_from(Competition)) == count
    actor.is_admin = True
    db_session.commit()
    detail = client.get(f"/api/admin/field-reviews/{review_id}").json()["data"]
    assert detail["entity_type"] == "competition"
    assert detail["competition_id"] is None
    assert detail["fields"][0]["candidate_value"] == "未收录竞赛候选"
    assert detail["fields"][0]["verification_state"] == "UNVERIFIED"


def test_legacy_admin_update_cannot_bypass_field_review(client, db_session, actor):
    actor.is_admin = True
    db_session.commit()
    before = db_session.get(Competition, 1).name
    response = client.put("/api/competitions/1", json={"name": "直接覆盖不允许"})
    assert response.status_code == 409
    assert db_session.get(Competition, 1).name == before


def test_origin_import_is_admin_only_and_idempotent(client, db_session, actor):
    response = correction(client)
    submission = response.json()["data"]
    path = f'/api/admin/field-review-origins/correction/{submission["id"]}'
    assert client.post(path).status_code == 403
    actor.is_admin = True
    db_session.commit()
    first = client.post(path)
    second = client.post(path)
    assert first.status_code == second.status_code == 200
    assert first.json()["data"]["field_review_id"] == second.json()["data"]["field_review_id"]


def _verify(client, detail, field_name):
    field = next(field for field in detail["fields"] if field["field_name"] == field_name)
    proposal = field["proposals"][0]["id"]
    response = client.post(f'/api/admin/field-reviews/{detail["id"]}/sources/{proposal}/verify',
        json={"preview_token": detail["preview_token"], "note": "已人工核对用户提供的原始来源"})
    assert response.status_code == 200, response.text
    return response.json()["data"], proposal


def test_user_candidate_partial_review_remains_reachable_and_only_approved_field_is_public(client, db_session, actor):
    original = db_session.get(Competition, 1).name
    submitted = correction(client, correction_type="其他").json()["data"]
    actor.is_admin = True
    db_session.commit()
    identity = submitted["field_review_id"]
    detail = client.get(f"/api/admin/field-reviews/{identity}").json()["data"]
    source = {"source_type": "user_submission", "source_url": "https://example.edu.cn/notice"}
    response = client.put(f"/api/admin/field-reviews/{identity}/prepare", json={
        "preview_token": detail["preview_token"], "entity_type": "competition", "competition_id": 1,
        "title": "结构化用户建议", "fields": [
            {"field_name": "organizer", "candidate_value": "人工核验后的主办方", "source": source},
            {"field_name": "name", "candidate_value": "拒绝的赛事名", "source": source},
            {"field_name": "description", "candidate_value": "待补证的简介", "source": source},
        ],
    })
    assert response.status_code == 200, response.text
    detail, proposal = _verify(client, response.json()["data"], "organizer")
    response = client.post(f"/api/admin/field-reviews/{identity}/review", json={
        "preview_token": detail["preview_token"], "note": "PRIVATE_ADMIN_NOTE",
        "decisions": [{"field_name": "organizer", "action": "approve", "proposal_id": proposal},
                      {"field_name": "name", "action": "reject"}, {"field_name": "description", "action": "defer"}],
    })
    assert response.status_code == 200, response.text
    public = client.get("/api/competitions/1").json()["data"]
    assert public["name"] == original
    assert public["organizer"] == "人工核验后的主办方"
    assert "PRIVATE_ADMIN_NOTE" not in json.dumps(public)
    history = client.get("/api/users/me/corrections").json()["data"]
    assert history[0]["status"] == "partially_approved"
    queue = client.get("/api/admin/review/corrections?status=unfinished").json()["data"]
    assert any(row["field_review_id"] == identity for row in queue)


def test_new_supplement_approval_publishes_manual_fact_and_keeps_origin_trace(client, db_session, actor):
    submitted = client.post("/api/users/me/supplements", json={"kind": "competition", "title": "人工核验新赛事",
        "description": "待人工核对的赛事资料", "source_url": "https://example.test/new"}).json()["data"]
    actor.is_admin = True
    db_session.commit()
    identity = submitted["field_review_id"]
    detail = client.get(f"/api/admin/field-reviews/{identity}").json()["data"]
    detail, proposal = _verify(client, detail, "name")
    response = client.post(f"/api/admin/field-reviews/{identity}/review", json={
        "preview_token": detail["preview_token"], "note": "来源核验后仅新增名称",
        "decisions": [{"field_name": "name", "action": "approve", "proposal_id": proposal}],
    })
    assert response.status_code == 200, response.text
    official = client.get(f'/api/competitions/{response.json()["data"]["competition_id"]}')
    assert official.status_code == 200
    data = official.json()["data"]
    assert data["name"] == "人工核验新赛事"
    assert data["verification_status"] == "verified_manual"
    assert data["official_verification_status"] == "人工核验通过"
    assert data["is_official_verified"] is False
    assert data["description"] is None
    assert any(row["id"] == data["id"] for row in client.get("/api/competitions").json()["data"])
    history = client.get("/api/users/me/supplements").json()["data"]
    assert history[0]["status"] == "approved"
    filtered = client.get("/api/admin/review/supplements?status=approved")
    assert filtered.status_code == 200
    assert filtered.json()["data"][0]["field_review_id"] == identity


@pytest.mark.parametrize("value,edition_id", [("无效的日期", 1), ("2026-10-30T23:59:00", 1), ("2026-10-30T23:59:00+08:00", None)])
def test_invalid_structured_correction_rolls_back_submission_and_both_queues(client, db_session, actor, value, edition_id):
    response = correction(client, proposed_value=value, competition_edition_id=edition_id)
    assert response.status_code == 422
    assert db_session.scalar(select(func.count()).select_from(UserCorrectionSubmission)) == 0
    assert db_session.scalar(select(func.count()).select_from(ReviewQueue)) == 0


def test_legacy_create_is_closed_but_requires_admin_first(client, db_session, actor):
    assert client.post("/api/competitions", json={"name": "不能直写"}).status_code == 403
    actor.is_admin = True
    db_session.commit()
    count = db_session.scalar(select(func.count()).select_from(Competition))
    assert client.post("/api/competitions", json={"name": "不能直写"}).status_code == 409
    assert db_session.scalar(select(func.count()).select_from(Competition)) == count


def test_free_text_origin_retains_unverified_original_source(client, db_session, actor):
    submitted = correction(client).json()["data"]
    candidate = db_session.get(ReviewQueue, submitted["field_review_id"])
    assert candidate.source_url == "https://example.edu.cn/notice"


@pytest.mark.parametrize("kind", ["correction", "supplement"])
def test_concurrent_legacy_transfer_creates_only_one_candidate(db_session, actor, tmp_path, monkeypatch, kind):
    from app.database.session import SessionLocal
    from app.services import field_review_origins as origins
    if kind == "correction":
        row = UserCorrectionSubmission(user_id=actor.id, competition_id=1, correction_type="其他",
                                      description="并发转入的原始证据", status="pending")
        db_session.add(row)
    else:
        submission = BetaFeedback(user_id=actor.id, category="数据补充", content="并发转入原始证据", status="pending")
        db_session.add(submission)
        db_session.flush()
        row = ReviewQueue(item_type="user_supplement", item_id=submission.id, reason="并发赛事",
                          suggested_value="competition", status="pending")
        db_session.add(row)
    db_session.commit()
    model, row_id = type(row), row.id
    path = tmp_path / "concurrent-origin.sqlite"
    raw = db_session.get_bind().raw_connection()
    try:
        with sqlite3.connect(path) as copy:
            raw.driver_connection.backup(copy)
    finally:
        raw.close()
    engine = create_engine(f"sqlite:///{path.as_posix()}", connect_args={"timeout": 10})
    first_read, second_read, first_committed = Event(), Event(), Event()
    real_lookup = origins.linked_field_review

    def controlled_lookup(db, origin_kind, origin_id):
        result = real_lookup(db, origin_kind, origin_id)
        if current_thread().name.endswith("_0"):
            first_read.set()
            second_read.wait(0.3)
        else:
            second_read.set()
            if result is None:
                assert first_committed.wait(5)
        return result

    monkeypatch.setattr(origins, "linked_field_review", controlled_lookup)
    def transfer(first):
        with SessionLocal(bind=engine) as db:
            original = db.get(model, row_id)
            candidate = origins.stage_correction(db, original) if kind == "correction" else origins.stage_supplement(db, original)
            identity = candidate.id
            db.commit()
            if first:
                first_committed.set()
            return identity
    try:
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="origin") as pool:
            first = pool.submit(transfer, True)
            assert first_read.wait(5)
            second = pool.submit(transfer, False)
            assert first.result(timeout=10) == second.result(timeout=10)
        with SessionLocal(bind=engine) as db:
            assert db.scalar(select(func.count()).select_from(ReviewQueue).where(ReviewQueue.item_type == "field_candidate")) == 1
    finally:
        engine.dispose()
