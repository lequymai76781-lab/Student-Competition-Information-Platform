"""V0.9 architecture foundation tests (additive models + backfill helpers)."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone

from app.models import (
    Competition,
    CompetitionEdition,
    CompetitionLead,
    CompetitionOrganization,
    ConferenceEdition,
    ConferenceSeries,
    Organization,
    SchoolConference,
    University,
)
from app.services.organization_service import (
    OrganizationService,
    lead_review_status,
    normalize_org_name,
    split_org_names,
)


def test_split_org_names() -> None:
    assert split_org_names("教育部、工业和信息化部；江苏省人民政府") == [
        "教育部",
        "工业和信息化部",
        "江苏省人民政府",
    ]
    assert split_org_names("教育部、教育部") == ["教育部"]
    assert split_org_names("") == []
    assert split_org_names(None) == []


def test_normalize_org_name() -> None:
    assert normalize_org_name(" 教育部 （高等教育司） ") == "教育部(高等教育司)"
    assert normalize_org_name("工业和信息化部 人才交流中心") == "工业和信息化部人才交流中心"


def test_lead_review_status_mapping() -> None:
    assert lead_review_status(matched_competition_id=1, matched_edition_id=2, needs_review=False) == "verified"
    assert lead_review_status(matched_competition_id=1, matched_edition_id=None, needs_review=True) == "matched"
    assert lead_review_status(matched_competition_id=None, matched_edition_id=2, needs_review=False) == "matched"
    assert lead_review_status(matched_competition_id=None, matched_edition_id=None, needs_review=True) == "pending"


def test_organization_sync_is_idempotent(db_session) -> None:
    service = OrganizationService()
    first = service.sync_competition_organizations(db_session)
    db_session.commit()
    second = service.sync_competition_organizations(db_session)
    db_session.commit()

    assert first["links_created"] >= 1
    assert second["links_created"] == 0
    org_count = db_session.scalar(select(func.count()).select_from(Organization))
    link_count = db_session.scalar(select(func.count()).select_from(CompetitionOrganization))
    assert org_count == first["organizations_created"]
    assert link_count == first["links_created"]

    test_org = db_session.execute(select(Organization).where(Organization.name == "测试主办方")).scalar_one()
    link = db_session.execute(
        select(CompetitionOrganization).where(CompetitionOrganization.organization_id == test_org.id)
    ).scalar_one()
    assert link.role == "organizer"
    assert link.display_name == "测试主办方"


def test_lead_review_status_backfill(db_session) -> None:
    competition = db_session.execute(select(Competition)).scalars().first()
    db_session.add_all(
        [
            CompetitionLead(
                raw_title="已匹配线索",
                source_url="https://example.com/a",
                source_type="university_official_notice",
                discovered_at=datetime.now(timezone.utc),
                matched_competition_id=competition.id,
                needs_review=False,
                verification_status="verified_official",
            ),
            CompetitionLead(
                raw_title="疑似线索",
                source_url="https://example.com/b",
                source_type="third_party_platform",
                discovered_at=datetime.now(timezone.utc),
                matched_competition_id=competition.id,
                needs_review=True,
                verification_status="unverified",
            ),
            CompetitionLead(
                raw_title="未匹配线索",
                source_url="https://example.com/c",
                source_type="third_party_platform",
                discovered_at=datetime.now(timezone.utc),
                needs_review=True,
                verification_status="unverified",
            ),
        ]
    )
    db_session.commit()
    stats = OrganizationService().backfill_lead_review_status(db_session)
    db_session.commit()
    assert stats == {"matched": 1, "pending": 1, "verified": 1}


def test_competition_edition_new_columns(db_session) -> None:
    competition = db_session.execute(select(Competition)).scalars().first()
    edition = CompetitionEdition(
        competition_id=competition.id,
        year=2027,
        edition_name="2027届",
        host_location="北京",
        edition_rules_url="https://example.com/rules",
        edition_status="announced",
    )
    db_session.add(edition)
    db_session.commit()
    db_session.refresh(edition)
    assert edition.host_location == "北京"
    assert edition.edition_status == "announced"


def test_conference_models_and_unique_year(db_session) -> None:
    university = University(name="会议测试大学", province="湖北", city="武汉")
    series = ConferenceSeries(name="测试学术年会", short_name="TAC")
    db_session.add_all([university, series])
    db_session.flush()
    edition = ConferenceEdition(conference_series_id=series.id, year=2026, city="北京")
    db_session.add(edition)
    db_session.flush()
    relation = SchoolConference(
        school_id=university.id,
        conference_series_id=series.id,
        conference_edition_id=edition.id,
        relation_type="participation_notice",
        notice_url="https://example.com/notice",
    )
    db_session.add(relation)
    db_session.commit()

    duplicate = ConferenceEdition(conference_series_id=series.id, year=2026)
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

    assert db_session.scalar(select(func.count()).select_from(ConferenceEdition)) == 1
    assert db_session.scalar(select(func.count()).select_from(SchoolConference)) == 1
