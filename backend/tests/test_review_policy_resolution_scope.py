"""Public resolution must not call a reviewed scoped/history policy current silence."""
from hashlib import sha256
from datetime import datetime, timedelta, timezone

import pytest
from app.models import CompetitionPolicyRecognition, PolicyDocument
from app.services.policy_resolution_service import PolicyResolutionService


def policy(db, *, student_scope="undergraduate", current=False, year=2019, status=None):
    digest = sha256(f"{student_scope}/{current}/{year}/{status}".encode()).hexdigest()
    document = PolicyDocument(university_id=1, scope_type="university", title="Explicit scoped policy",
        policy_type="award_policy", year=year, source_url="https://example.test/" + digest,
        document_hash=digest, content_text="This policy explicitly names the competition for its stated scope.",
        is_current=current, is_verified=True, verification_status="human_verified", is_demo=False,
        source_type="university_policy", metadata_json={"relation_scope": {
            "scope_type": "university", "student_scope": student_scope,
            "current_validity_confirmed": current, "recognition_evidence": "Explicit named competition",
            "applicability_text": "Only the stated population and period", "revoked": False}})
    db.add(document)
    db.flush()
    if status:
        db.add(CompetitionPolicyRecognition(university_id=1, competition_id=1,
            policy_document_id=document.id, year=year, recognition_status=status,
            usage_type="award_policy", evidence_text="Explicit named competition", evidence_hash=digest,
            confidence=1, needs_manual_review=False, is_demo=False))
        db.flush()
    return document


@pytest.mark.parametrize("status,students,current,year", [
    ("historical_recognition", "undergraduate", False, 2019),
    ("historical_recognition", "graduate", False, 2025),
    ("scoped_recognition", "graduate", True, 2026),
])
def test_public_resolution_does_not_turn_scoped_positive_evidence_into_current_silence(
        db_session, client, status, students, current, year):
    document = policy(db_session, status=status, student_scope=students, current=current, year=year)
    response = client.get("/api/v0.2/policies/resolve?competition_id=1&university_id=1")
    assert response.status_code == 200
    result = response.json()["data"]
    assert result["effective_status"] == "insufficient_evidence", result
    assert result["effective_policy_document_id"] is None
    assert result["needs_manual_review"] is True
    assert "未提及" not in result["reason"]
    # A historical/scoped record remains available to explicit internal analysis.
    internal = PolicyResolutionService().resolve(db_session, competition_id=1, university_id=1)
    assert internal.effective_policy_document_id == document.id
    assert internal.effective_status == status


@pytest.mark.parametrize("students", ["undergraduate", "all"])
def test_current_general_policy_keeps_public_positive_result(db_session, client, students):
    document = policy(db_session, status="recognized", student_scope=students, current=True, year=2026)
    data = client.get("/api/v0.2/policies/resolve?competition_id=1&university_id=1").json()["data"]
    assert data["effective_status"] == "recognized"
    assert data["effective_policy_document_id"] == document.id


def test_scoped_newer_document_does_not_hide_applicable_general_document(db_session, client):
    general = policy(db_session, current=True, year=2025)
    policy(db_session, current=True, year=2026, student_scope="graduate", status="scoped_recognition")
    data = client.get("/api/v0.2/policies/resolve?competition_id=1&university_id=1").json()["data"]
    assert data["effective_status"] == "not_mentioned"
    assert data["effective_policy_document_id"] == general.id


def test_requested_historical_year_does_not_imply_current_policy_scope(db_session, client):
    policy(db_session, status="historical_recognition", year=2019)
    data = client.get("/api/v0.2/policies/resolve?competition_id=1&university_id=1&year=2019").json()["data"]
    assert data["effective_status"] == "insufficient_evidence"
    assert data["needs_manual_review"] is True


@pytest.mark.parametrize("status", ["recognized", None], ids=["positive", "fallback"])
@pytest.mark.parametrize("period", ["expired", "future"])
def test_public_resolution_rechecks_reviewed_policy_time_window(db_session, client, status, period):
    document = policy(db_session, current=True, year=2026, status=status)
    now = datetime.now(timezone.utc)
    start, end = ((now - timedelta(days=365), now - timedelta(days=1)) if period == "expired"
                  else (now + timedelta(days=1), now + timedelta(days=365)))
    document.effective_from, document.effective_until = start, end
    document.metadata_json = {**document.metadata_json, "relation_scope": {
        **document.metadata_json["relation_scope"], "effective_from": start.isoformat(),
        "effective_until": end.isoformat()}}
    db_session.flush()
    data = client.get("/api/v0.2/policies/resolve?competition_id=1&university_id=1").json()["data"]
    assert data["effective_status"] == "insufficient_evidence", data
    assert data["effective_policy_document_id"] is None
    assert data["needs_manual_review"] is True


@pytest.mark.parametrize("status,expected", [("recognized", "recognized"), (None, "not_mentioned")])
def test_current_reviewed_policy_with_live_window_remains_applicable(db_session, client, status, expected):
    document = policy(db_session, current=True, year=2026, status=status)
    now = datetime.now(timezone.utc)
    document.metadata_json = {**document.metadata_json, "relation_scope": {
        **document.metadata_json["relation_scope"], "effective_from": (now - timedelta(days=1)).isoformat(),
        "effective_until": (now + timedelta(days=1)).isoformat()}}
    db_session.flush()
    data = client.get("/api/v0.2/policies/resolve?competition_id=1&university_id=1").json()["data"]
    assert data["effective_status"] == expected
    assert data["effective_policy_document_id"] == document.id
