from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Competition,
    CompetitionFactRevision,
    CompetitionPolicyRecognition,
    PolicyDocument,
    University,
)
from app.services.home_data_service import HomeDataService


def test_home_api_returns_five_real_sections_and_readiness(client: TestClient) -> None:
    response = client.get("/api/home")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["decision"] == "FRONTEND_NOT_READY"
    assert len(data["blockers"]) <= 3
    assert set(data) >= {
        "current_recognitions",
        "open_registrations",
        "upcoming_deadlines",
        "recent_updates",
        "conferences",
    }
    for section_name in (
        "current_recognitions",
        "open_registrations",
        "upcoming_deadlines",
        "recent_updates",
        "conferences",
    ):
        section = data[section_name]
        assert section["readiness"]["status"] in {"READY", "PARTIAL", "BLOCKED"}
        assert section["readiness"]["record_count"] >= len(section["items"])
        assert len(section["items"]) <= 10


def test_home_deadline_keeps_school_scope_and_requires_official_proof(db_session: Session) -> None:
    result = HomeDataService().build(db_session)

    assert result.upcoming_deadlines.readiness.record_count == 1
    node = result.upcoming_deadlines.items[0]
    assert node.scope_type == "university"
    assert node.deadline_type == "university_registration_deadline"
    assert node.source_url == "https://example.edu.cn/notice"
    assert not any(item.scope_type == "official" for item in result.upcoming_deadlines.items)


def test_home_current_recognition_requires_current_verified_document(db_session: Session) -> None:
    university = db_session.scalar(select(University))
    competition = db_session.scalar(select(Competition))
    document = PolicyDocument(
        university_id=university.id,
        title="测试大学现行竞赛目录",
        policy_type="competition_catalog",
        year=2026,
        publisher="测试大学教务处",
        source_url="https://example.edu.cn/current-catalog",
        authority_level="A2",
        published_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        is_current=True,
        is_verified=True,
        verification_status="school_confirmed",
        source_type="university",
        is_demo=False,
    )
    db_session.add(document)
    db_session.flush()
    db_session.add(
        CompetitionPolicyRecognition(
            competition_id=competition.id,
            policy_document_id=document.id,
            university_id=university.id,
            year=2026,
            recognition_status="recognized",
            recognition_level="校级A类",
            usage_type="competition_catalog",
            evidence_text="正式目录第1项",
            evidence_hash="home-current-recognition-test",
            confidence=1.0,
            needs_manual_review=False,
            is_demo=False,
        )
    )
    db_session.commit()

    service = HomeDataService()
    current = service.build(db_session).current_recognitions
    assert current.readiness.record_count == 1
    assert current.items[0].evidence_url == document.source_url

    document.is_current = False
    db_session.commit()
    assert service.build(db_session).current_recognitions.readiness.record_count == 0


def test_home_recent_updates_dedupes_and_excludes_null_corrections(db_session: Session) -> None:
    competition = db_session.scalar(select(Competition))
    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            CompetitionFactRevision(
                competition_id=competition.id,
                field_name="official_url",
                old_value="https://old.example.com",
                new_value="https://new.example.com",
                changed_at=now - timedelta(hours=2),
                source_url="https://source.example.com/first",
                source_name="测试官方来源",
                verification_status="verified_official",
            ),
            CompetitionFactRevision(
                competition_id=competition.id,
                field_name="official_url",
                old_value="https://new.example.com",
                new_value="https://latest.example.com",
                changed_at=now - timedelta(hours=1),
                source_url="https://source.example.com/latest",
                source_name="测试官方来源",
                verification_status="verified_official",
            ),
            CompetitionFactRevision(
                competition_id=competition.id,
                field_name="organizer",
                old_value="错误主办方",
                new_value=None,
                changed_at=now,
                source_url="https://source.example.com/correction",
                source_name="测试官方来源",
                verification_status="verified_official",
            ),
        ]
    )
    db_session.commit()

    recent = HomeDataService().build(db_session, now=now).recent_updates
    assert recent.readiness.record_count == 1
    assert recent.items[0].entity_type == "competition"
    assert recent.items[0].entity_id == competition.id
    assert recent.items[0].changed_fields == ["official_url"]
    assert recent.items[0].field_name == "official_url"
    assert recent.items[0].new_value == "https://latest.example.com"
    assert recent.items[0].source_url == "https://source.example.com/latest"


def test_home_conferences_use_empty_state_instead_of_mock_data(db_session: Session) -> None:
    conferences = HomeDataService().build(db_session).conferences

    assert conferences.readiness.status == "BLOCKED"
    assert conferences.readiness.record_count == 0
    assert conferences.items == []
