import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Competition
from app.services.competition_normalization_service import CompetitionNormalizationService
from app.services.school_competition_service import SchoolCompetitionService
from scripts.import_recognition_batch_01 import (
    is_recognition_evidence,
    preserve_school_specific_level,
    recognition_status_for,
)


SEED = Path(__file__).resolve().parents[2] / "data" / "seeds" / "recognition_batch_01.json"


def test_notification_cannot_be_recognition_evidence() -> None:
    assert is_recognition_evidence("notification") is False
    assert is_recognition_evidence("registration_notice") is False


def test_participation_cannot_be_recognition_evidence() -> None:
    assert is_recognition_evidence("participation") is False
    assert is_recognition_evidence("participation_news") is False


def test_historical_directory_is_not_current_recognition() -> None:
    assert recognition_status_for("current_recognition") == "recognized"
    assert recognition_status_for("historical_recognition") == "expired"
    assert recognition_status_for("unknown_validity") == "uncertain"

    historical = SimpleNamespace(
        year=2025,
        id=1,
        recognition_status="expired",
        recognition_level="A类",
        usage_type="recommendation",
        award_requirement=None,
    )
    latest = SchoolCompetitionService()._latest_recognition([historical])
    assert latest is not None
    assert latest["recognition_status"] == "expired"


def test_school_specific_level_is_preserved_verbatim() -> None:
    assert preserve_school_specific_level(" A/B/C ") == "A/B/C"
    assert preserve_school_specific_level("Ⅰ级甲等") == "Ⅰ级甲等"
    assert preserve_school_specific_level("一级") == "一级"


def test_recognition_api_accepts_unknown_validity_filter(client: TestClient) -> None:
    response = client.get("/api/v0.2/policies/recognitions", params={"recognition_status": "uncertain"})
    assert response.status_code == 200


def test_batch_seed_contains_only_formal_recognition_evidence() -> None:
    payload = json.loads(SEED.read_text(encoding="utf-8"))
    for document in payload["documents"]:
        assert is_recognition_evidence(document["evidence_type"])
        if document["validity_status"] == "historical_recognition":
            assert document["is_current"] is False
        for row in document["rows"]:
            assert row["school_specific_level"]


def test_directory_name_variants_do_not_create_duplicate_competitions(db_session: Session) -> None:
    competition = Competition(name="中国国际大学生创新大赛", is_demo=False)
    db_session.add(competition)
    db_session.flush()
    before = db_session.scalar(select(func.count()).select_from(Competition))

    normalizer = CompetitionNormalizationService()
    current = normalizer.normalize(db_session, "中国国际大学生创新大赛")
    historical = normalizer.normalize(db_session, "中国“互联网+”大学生创新创业大赛")

    assert current.competition is not None
    assert historical.competition is not None
    assert current.competition.id == historical.competition.id == competition.id
    assert db_session.scalar(select(func.count()).select_from(Competition)) == before
