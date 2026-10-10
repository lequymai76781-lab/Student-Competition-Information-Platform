from datetime import datetime, timedelta, timezone

from app.models import College, CompetitionEdition, University, UniversityCompetitionEditionRelation
from app.services.deadline_resolution_service import DeadlineResolutionService


def test_deadline_resolution_prefers_college_then_university_then_official() -> None:
    now = datetime.now(timezone.utc)
    university = University(id=1, name="测试大学")
    college = College(id=2, university_id=1, name="测试学院")
    university_relation = UniversityCompetitionEditionRelation(
        id=10,
        is_verified=True,
        verification_status="verified_official",
        university_id=1,
        competition_edition_id=1,
        notice_type="registration_notice",
        internal_notice_url="https://example.edu.cn/university",
        internal_registration_deadline=now + timedelta(days=20),
        observed_at=now,
    )
    university_relation.university = university
    college_relation = UniversityCompetitionEditionRelation(
        id=11,
        is_verified=True,
        verification_status="verified_official",
        university_id=1,
        college_id=2,
        competition_edition_id=1,
        notice_type="internal_selection",
        internal_notice_url="https://example.edu.cn/college",
        college_registration_deadline=now + timedelta(days=10),
        observed_at=now,
    )
    college_relation.university = university
    college_relation.college = college
    edition = CompetitionEdition(
        id=1,
        competition_id=1,
        year=2026,
        official_registration_deadline=now + timedelta(days=30),
        current_status="registration_open",
        is_verified=True,
        university_relations=[university_relation, college_relation],
    )

    result = DeadlineResolutionService().resolve_registration(
        edition,
        university_id=1,
        college_id=2,
    )

    assert result.official_deadline == now + timedelta(days=30)
    assert result.university_deadline == now + timedelta(days=20)
    assert result.college_deadline == now + timedelta(days=10)
    assert result.effective_deadline == result.college_deadline
    assert result.effective_deadline_type == "college_registration_deadline"


def test_deadline_resolution_ignores_award_news() -> None:
    now = datetime.now(timezone.utc)
    relation = UniversityCompetitionEditionRelation(
        id=12,
        university_id=1,
        competition_edition_id=1,
        notice_type="award_news",
        internal_notice_url="https://example.edu.cn/award",
        internal_registration_deadline=now + timedelta(days=5),
        observed_at=now,
    )
    edition = CompetitionEdition(
        id=1,
        competition_id=1,
        year=2026,
        official_registration_deadline=now + timedelta(days=30),
        current_status="registration_open",
        is_verified=True,
        university_relations=[relation],
    )

    result = DeadlineResolutionService().resolve_registration(edition, university_id=1)

    assert result.university_deadline is None
    assert result.effective_deadline == result.official_deadline
    assert result.effective_deadline_type == "official_registration_deadline"


def test_generic_registration_deadline_is_not_labeled_official() -> None:
    now = datetime.now(timezone.utc)
    edition = CompetitionEdition(
        id=1,
        competition_id=1,
        year=2026,
        registration_deadline=now + timedelta(days=30),
        current_status="registration_open",
        is_verified=True,
        university_relations=[],
    )

    service = DeadlineResolutionService()
    result = service.resolve_registration(edition)
    action_deadline, action_label, _ = service.resolve_action(edition)

    assert result.official_deadline is None
    assert result.effective_deadline is None
    assert action_deadline == edition.registration_deadline
    assert action_label == "报名截止"
