"""V0.9 semantic refactor tests: authority rules, school layer, promotion fix."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.models import (
    Competition,
    CompetitionEdition,
    CompetitionLead,
    CompetitionPolicyRecognition,
    CompetitionSource,
    SchoolCompetition,
    University,
    UniversityCompetitionEditionRelation,
)
from app.services.competition_discovery_import_service import CompetitionDiscoveryImportService
from app.services.fact_intelligence_service import FactIntelligenceService
from app.services.school_competition_service import SchoolCompetitionService
from app.services.source_authority_service import (
    authority_level_for,
    can_prove,
    competition_status_from_source_levels,
    is_national_authority_source,
)


def _base_objects(db_session):
    university = University(name="语义测试大学", province="湖北", city="武汉")
    competition = Competition(
        name="语义重构测试竞赛",
        organizer="测试组委会",
        is_demo=False,
        is_competition=True,
        entity_type="competition",
        competition_type="competition",
        verification_status="unverified",
    )
    db_session.add_all([university, competition])
    db_session.flush()
    edition = CompetitionEdition(
        competition_id=competition.id,
        year=2026,
        edition_name="2026语义重构测试竞赛",
        current_status="registration_open",
        is_verified=True,
        verification_status="school_confirmed",
    )
    db_session.add(edition)
    db_session.flush()
    return university, competition, edition


def test_authority_level_rules() -> None:
    assert authority_level_for("university_official_notice") == "B"
    assert authority_level_for("organizer_official_notice") == "S"
    assert authority_level_for("college_official_notice") == "C"
    assert authority_level_for("github_seed") == "D"
    assert is_national_authority_source("government_official_notice")
    assert not is_national_authority_source("university_official_notice")
    assert can_prove("university_official_notice", "campus_registration_deadline")
    assert not can_prove("university_official_notice", "official_registration_deadline")
    assert can_prove("organizer_official_notice", "official_registration_deadline")
    assert competition_status_from_source_levels(["B"], has_any_source=True) == "school_confirmed"
    assert competition_status_from_source_levels(["S"], has_any_source=True) == "verified_official"
    assert competition_status_from_source_levels([], has_any_source=True) == "pending_verification"


def test_verification_recompute_blocks_school_promotion(db_session) -> None:
    university, competition, edition = _base_objects(db_session)
    school_source = CompetitionSource(
        competition_id=competition.id,
        competition_edition_id=edition.id,
        source_type="university_official_notice",
        source_name="语义测试大学教务处",
        source_url="https://edu.example.com/notice",
        is_verified=True,
        is_official=False,
        is_demo=False,
    )
    db_session.add(school_source)
    db_session.add(
        UniversityCompetitionEditionRelation(
            university_id=university.id,
            competition_edition_id=edition.id,
            source_type="university_official_notice",
            notice_type="registration_notice",
            internal_notice_url="https://edu.example.com/notice",
            internal_registration_deadline=datetime.now(timezone.utc) + timedelta(days=10),
            observed_at=datetime.now(timezone.utc),
            is_verified=True,
            verification_status="school_confirmed",
            is_demo=False,
        )
    )
    db_session.commit()

    service = FactIntelligenceService()
    service.refresh_source_tiers(db_session)
    service.refresh_verification(db_session)
    db_session.commit()

    db_session.refresh(competition)
    assert competition.verification_status == "school_confirmed"
    assert competition.is_official_verified is False
    db_session.refresh(edition)
    assert edition.verification_status == "school_confirmed"

    official = CompetitionSource(
        competition_id=competition.id,
        competition_edition_id=edition.id,
        source_type="organizer_official_notice",
        source_name="赛事组委会",
        source_url="https://organizer.example.com/notice",
        is_verified=True,
        is_official=True,
        is_demo=False,
    )
    db_session.add(official)
    db_session.commit()
    service.refresh_source_tiers(db_session)
    service.refresh_verification(db_session)
    db_session.commit()
    db_session.refresh(competition)
    assert competition.verification_status == "verified_official"


def test_school_competition_rebuild_merges_evidence(db_session) -> None:
    university, competition, edition = _base_objects(db_session)
    policy = db_session.execute(
        select(CompetitionPolicyRecognition).where(
            CompetitionPolicyRecognition.competition_id == competition.id
        )
    ).scalars().first()
    if policy is None:
        # No policy document in base fixture; skip recognition half for this test.
        pass
    relation = UniversityCompetitionEditionRelation(
        university_id=university.id,
        competition_edition_id=edition.id,
        source_type="university_official_notice",
        notice_type="registration_notice",
        internal_notice_url="https://edu.example.com/notice",
        organizing_department="语义测试大学教务处",
        internal_registration_deadline=datetime(2026, 9, 10, tzinfo=timezone.utc),
        observed_at=datetime.now(timezone.utc),
        is_verified=True,
        is_demo=False,
    )
    db_session.add(relation)
    db_session.commit()

    service = SchoolCompetitionService()
    first = service.rebuild(db_session)
    db_session.commit()
    second = service.rebuild(db_session)
    db_session.commit()

    assert first["school_competition_rows"] >= 1
    assert second["school_competition_rows"] == first["school_competition_rows"]
    row = db_session.execute(
        select(SchoolCompetition).where(
            SchoolCompetition.school_id == university.id,
            SchoolCompetition.competition_id == competition.id,
        )
    ).scalars().first()
    assert row is not None
    assert row.school_id == university.id
    assert row.competition_id == competition.id
    assert row.competition_edition_id == edition.id
    stored = row.campus_registration_deadline
    if stored is not None and stored.tzinfo is None:
        stored = stored.replace(tzinfo=timezone.utc)
    assert stored == datetime(2026, 9, 10, tzinfo=timezone.utc)
    assert row.notice_url == "https://edu.example.com/notice"
    assert row.provenance["university_competition_edition_relation_ids"] == [relation.id]


def test_university_notice_cannot_create_edition(db_session) -> None:
    university, competition, _ = _base_objects(db_session)
    observed_at = datetime.now(timezone.utc)
    item = {
        "university": university.name,
        "competition_name": competition.name,
        "year": 2027,
        "notice_type": "registration_notice",
        "internal_registration_deadline": "2027-05-01T00:00:00+00:00",
        "internal_notice_url": "https://edu.example.com/2027",
        "raw_title": "关于参加2027年语义重构测试竞赛的通知",
        "source_type": "university_official_notice",
    }
    result = CompetitionDiscoveryImportService()._upsert_relation(db_session, item, observed_at)
    db_session.commit()
    assert result is None
    edition_count = db_session.scalar(
        select(func.count())
        .select_from(CompetitionEdition)
        .where(CompetitionEdition.competition_id == competition.id, CompetitionEdition.year == 2027)
    )
    assert edition_count == 0
    lead = db_session.execute(
        select(CompetitionLead).where(CompetitionLead.source_url == item["internal_notice_url"])
    ).scalars().first()
    assert lead is not None
    assert lead.review_status == "matched"
    assert lead.needs_review is True
