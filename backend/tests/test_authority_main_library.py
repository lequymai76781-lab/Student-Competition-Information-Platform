"""V1 authority main-library tests.

Covers the ten required behaviors:
1 university cannot verify a competition
2 ministry organizer source can verify a competition
3 association list cannot overwrite organizer
4 school deadline cannot overwrite the national deadline
5 edition authority is independent from competition authority
6 duplicate official sources are deduplicated
7 conflicting official sources generate a warning (no silent overwrite)
8 uncertain name matches require manual review
9 award/festival is not silently treated as a competition
10 rerunning the authority sync is idempotent
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from app.models import (
    Competition,
    CompetitionEdition,
    CompetitionSource,
    University,
    UniversityCompetitionEditionRelation,
)
from app.services.authority_match_service import AuthorityMatchService
from app.services.authority_sync_service import AuthoritySyncService
from app.services.fact_intelligence_service import FactIntelligenceService


def _write_registry(registry_dir: Path, registry_id: str, payload: dict) -> Path:
    registry_dir.mkdir(parents=True, exist_ok=True)
    path = registry_dir / f"{registry_id}.json"
    base = {
        "registry_id": registry_id,
        "version": 1,
        "enabled": True,
        "source_type": "government_official_notice",
        "authority_level": "S",
        "organization_name": "测试部委",
        "source_name": f"{registry_id} 通知",
        "title": f"{registry_id} 通知",
        "doc_number": None,
        "source_url": f"https://example.org/{registry_id}",
        "canonical_source_url": f"https://example.org/{registry_id}",
        "published_at": "2026-01-01",
        "local_content_path": None,
        "expected": None,
        "relationship_scope": ["competition_identity"],
        "relation_role": "organizer",
        "competition_facts": {},
        "edition": None,
        "notes": "test fixture",
    }
    base.update(payload)
    path.write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
    return path


def _add_competition(db_session, name: str, **kwargs) -> Competition:
    payload = {
        "name": name,
        "organizer": "测试组委会",
        "is_demo": False,
        "is_competition": kwargs.pop("is_competition", True),
        "entity_type": kwargs.pop("entity_type", "competition"),
        "competition_type": "competition",
        "verification_status": "unverified",
    }
    payload.update(kwargs)
    competition = Competition(**payload)
    db_session.add(competition)
    db_session.flush()
    return competition


def _run_refresh(db_session) -> None:
    service = FactIntelligenceService()
    service.refresh_source_tiers(db_session)
    service.refresh_verification(db_session)
    db_session.commit()


def test_university_source_cannot_verify_competition(db_session) -> None:
    competition = _add_competition(db_session, "高校不可核验测试竞赛")
    db_session.add(
        CompetitionSource(
            competition_id=competition.id,
            source_type="university_official_notice",
            source_name="某大学教务处",
            source_url="https://edu.example.com/notice",
            is_verified=True,
            is_official=False,
            is_demo=False,
        )
    )
    db_session.commit()
    _run_refresh(db_session)
    db_session.refresh(competition)
    assert competition.verification_status == "school_confirmed"
    assert competition.is_official_verified is False


def test_ministry_source_can_verify_competition(db_session) -> None:
    competition = _add_competition(db_session, "部委可核验测试竞赛")
    db_session.add(
        CompetitionSource(
            competition_id=competition.id,
            source_type="government_official_notice",
            source_name="教育部通知",
            source_url="https://www.moe.gov.cn/example",
            is_verified=True,
            is_official=True,
            is_demo=False,
        )
    )
    db_session.commit()
    _run_refresh(db_session)
    db_session.refresh(competition)
    assert competition.verification_status == "verified_official"
    assert competition.is_official_verified is True


def test_association_list_cannot_overwrite_organizer(db_session, tmp_path) -> None:
    competition = _add_competition(db_session, "协会目录不可改写主办方竞赛", organizer="原主办方A")
    db_session.commit()
    registry_dir = tmp_path / "registry"
    _write_registry(
        registry_dir,
        "association-entry",
        {
            "source_type": "higher_education_association",
            "authority_level": "A",
            "source_url": "https://cahe.example.com/report",
            "expected": {"competition_name": competition.name, "edition_year": None},
            "relationship_scope": ["association_directory"],
            "relation_role": None,
            "competition_facts": {"organizer": "错误改写的主办方"},
        },
    )
    report = AuthoritySyncService().run(db_session, registry_dir=registry_dir, dry_run=False)
    db_session.commit()
    db_session.refresh(competition)
    assert competition.organizer == "原主办方A"
    assert report["counters"].get("disallowed_competition_facts", 0) >= 1


def test_school_deadline_cannot_overwrite_national_deadline(db_session, tmp_path) -> None:
    competition = _add_competition(db_session, "校内截止不可覆盖测试竞赛")
    edition = CompetitionEdition(
        competition_id=competition.id,
        year=2026,
        edition_name="2026校内截止不可覆盖测试竞赛",
        official_registration_deadline=datetime(2026, 9, 25, 12, 0),
        current_status="registration_open",
        verification_status="verified_official",
    )
    db_session.add(edition)
    db_session.commit()
    registry_dir = tmp_path / "registry"
    _write_registry(
        registry_dir,
        "school-entry",
        {
            "source_type": "university_official_notice",
            "authority_level": "B",
            "source_url": "https://edu.example.com/school-notice",
            "expected": {"competition_name": competition.name, "edition_year": 2026},
            "edition": {
                "year": 2026,
                "edition_name": "2026校内截止不可覆盖测试竞赛",
                "registration_start": None,
                "official_registration_deadline": "2026-06-01T00:00:00",
                "competition_start": None,
                "competition_end": None,
                "facts": {},
            },
        },
    )
    report = AuthoritySyncService().run(db_session, registry_dir=registry_dir, dry_run=False)
    db_session.commit()
    db_session.refresh(edition)
    assert edition.official_registration_deadline == datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
    assert report["counters"].get("field_not_provable", 0) >= 1


def test_edition_authority_independent_from_competition(db_session) -> None:
    competition = _add_competition(db_session, "届次独立核验测试竞赛")
    edition = CompetitionEdition(
        competition_id=competition.id,
        year=2026,
        edition_name="2026届次独立核验测试竞赛",
        verification_status="unverified",
    )
    university = University(name="届次独立测试大学", province="湖北", city="武汉")
    db_session.add(university)
    db_session.flush()
    db_session.add(edition)
    db_session.flush()
    db_session.add_all(
        [
            CompetitionSource(
                competition_id=competition.id,
                source_type="government_official_notice",
                source_name="部委通知",
                source_url="https://www.gov.example.com/notice",
                is_verified=True,
                is_official=True,
                is_demo=False,
            ),
            CompetitionSource(
                competition_id=competition.id,
                competition_edition_id=edition.id,
                source_type="university_official_notice",
                source_name="某大学",
                source_url="https://edu.example.com/edition-notice",
                is_verified=True,
                is_official=False,
                is_demo=False,
            ),
            UniversityCompetitionEditionRelation(
                university_id=university.id,
                competition_edition_id=edition.id,
                source_type="university_official_notice",
                notice_type="registration_notice",
                internal_notice_url="https://edu.example.com/edition-notice",
                internal_registration_deadline=datetime(2026, 8, 1),
                observed_at=datetime(2026, 1, 1),
                is_verified=True,
                verification_status="school_confirmed",
                is_demo=False,
            ),
        ]
    )
    db_session.commit()
    _run_refresh(db_session)
    db_session.refresh(competition)
    db_session.refresh(edition)
    assert competition.verification_status == "verified_official"
    assert edition.verification_status == "school_confirmed"


def test_duplicate_official_sources_deduplicated(db_session, tmp_path) -> None:
    competition = _add_competition(db_session, "官方来源去重测试竞赛")
    db_session.commit()
    registry_dir = tmp_path / "registry"
    for suffix in ("a", "b"):
        _write_registry(
            registry_dir,
            f"dup-{suffix}",
            {
                "source_url": "https://example.org/dup-notice",
                "canonical_source_url": "https://example.org/dup-notice",
                "expected": {"competition_name": competition.name, "edition_year": None},
            },
        )
    AuthoritySyncService().run(db_session, registry_dir=registry_dir, dry_run=False)
    db_session.commit()
    count = db_session.scalar(
        select(func.count())
        .select_from(CompetitionSource)
        .where(
            CompetitionSource.competition_id == competition.id,
            CompetitionSource.source_url == "https://example.org/dup-notice",
        )
    )
    assert count == 1


def test_conflicting_official_sources_generate_warning(db_session, tmp_path) -> None:
    competition = _add_competition(db_session, "官方冲突测试竞赛")
    db_session.commit()
    registry_dir = tmp_path / "registry"
    _write_registry(
        registry_dir,
        "conflict-a",
        {
            "source_url": "https://example.org/conflict-a",
            "expected": {"competition_name": competition.name, "edition_year": 2026},
            "edition": {
                "year": 2026,
                "edition_name": "2026官方冲突测试竞赛",
                "registration_start": None,
                "official_registration_deadline": "2026-09-01T00:00:00",
                "competition_start": None,
                "competition_end": None,
                "facts": {},
            },
        },
    )
    _write_registry(
        registry_dir,
        "conflict-b",
        {
            "source_url": "https://example.org/conflict-b",
            "expected": {"competition_name": competition.name, "edition_year": 2026},
            "edition": {
                "year": 2026,
                "edition_name": "2026官方冲突测试竞赛",
                "registration_start": None,
                "official_registration_deadline": "2026-09-10T00:00:00",
                "competition_start": None,
                "competition_end": None,
                "facts": {},
            },
        },
    )
    report = AuthoritySyncService().run(db_session, registry_dir=registry_dir, dry_run=False)
    db_session.commit()
    edition = db_session.execute(
        select(CompetitionEdition).where(
            CompetitionEdition.competition_id == competition.id,
            CompetitionEdition.year == 2026,
        )
    ).scalars().one()
    assert report["counters"]["conflicts"] >= 1
    assert edition.official_registration_deadline == datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)


def test_uncertain_name_match_requires_review(db_session, tmp_path) -> None:
    _add_competition(db_session, "中国国际大学生创新大赛")
    db_session.commit()
    match = AuthorityMatchService().match(db_session, "全国大学生创新大赛")
    assert match.needs_manual_review is True
    registry_dir = tmp_path / "registry"
    _write_registry(
        registry_dir,
        "uncertain",
        {
            "source_url": "https://example.org/uncertain",
            "expected": {"competition_name": "全国大学生创新大赛", "edition_year": None},
        },
    )
    report = AuthoritySyncService().run(db_session, registry_dir=registry_dir, dry_run=False)
    db_session.commit()
    assert report["counters"].get("sources_added", 0) == 0
    assert report["counters"].get("manual_review", 0) + report["counters"].get("unmatched", 0) >= 1


def test_award_not_silently_treated_as_competition(db_session) -> None:
    competition = _add_competition(
        db_session,
        "某奖项评选",
        is_competition=False,
        entity_type="award",
    )
    db_session.add(
        CompetitionSource(
            competition_id=competition.id,
            source_type="government_official_notice",
            source_name="部委文件",
            source_url="https://www.gov.example.com/award",
            is_verified=True,
            is_official=True,
            is_demo=False,
        )
    )
    db_session.commit()
    _run_refresh(db_session)
    db_session.refresh(competition)
    assert competition.is_competition is False
    assert competition.entity_type == "award"
    assert competition.verification_status != "verified_official"


def test_rerunning_sync_is_idempotent(db_session, tmp_path) -> None:
    competition = _add_competition(db_session, "幂等同步测试竞赛")
    db_session.commit()
    registry_dir = tmp_path / "registry"
    _write_registry(
        registry_dir,
        "idem-entry",
        {
            "source_url": "https://example.org/idem",
            "expected": {"competition_name": competition.name, "edition_year": 2026},
            "edition": {
                "year": 2026,
                "edition_name": "2026幂等同步测试竞赛",
                "registration_start": None,
                "official_registration_deadline": "2026-09-01T00:00:00",
                "competition_start": None,
                "competition_end": None,
                "facts": {"competition_period": "2026年9月举办"},
            },
        },
    )
    first = AuthoritySyncService().run(db_session, registry_dir=registry_dir, dry_run=False)
    db_session.commit()
    second = AuthoritySyncService().run(db_session, registry_dir=registry_dir, dry_run=False)
    db_session.commit()
    assert first["counters"].get("sources_added", 0) == 1
    assert first["counters"].get("editions_created", 0) == 1
    assert second["counters"].get("sources_added", 0) == 0
    assert second["counters"].get("editions_created", 0) == 0
    assert second["counters"]["source_exists"] >= 1
    assert second["counters"].get("edition_fields_changed", 0) == 0
    assert second["counters"].get("fact_rows_added", 0) == 0
