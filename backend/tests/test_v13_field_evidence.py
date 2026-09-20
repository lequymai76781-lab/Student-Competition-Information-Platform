"""V13 field-level evidence gradient tests.

Identity verification is never weakened; display-field provenance may be
secondary, conflicts are preserved, official-homepage classification is
separate from independent-domain checks, and reruns stay idempotent.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, select

from app.models import (
    Competition,
    CompetitionEdition,
    CompetitionFactSource,
    CompetitionSource,
    SchoolCompetition,
    University,
)
from app.services.fact_intelligence_service import FactIntelligenceService
from app.services.field_evidence_service import (
    classify_homepage,
    default_evidence_level,
    evidence_allowed,
    is_identity_qualified,
)
from app.services.v12_fact_enrichment_service import V12FactEnrichmentService


EVIDENCE_FILE = "data/seeds/v081_211_radar_fix_discovery.json"


def _comp(db_session, name: str = "v13测试赛事", **kwargs) -> Competition:
    payload = {
        "name": name,
        "is_demo": False,
        "is_competition": True,
        "entity_type": "competition",
        "competition_type": "competition",
        "verification_status": "unverified",
        "status": "active",
    }
    payload.update(kwargs)
    comp = Competition(**payload)
    db_session.add(comp)
    db_session.flush()
    return comp


def _b_source(db_session, comp: Competition, url: str) -> CompetitionSource:
    source = CompetitionSource(
        competition_id=comp.id,
        source_type="university_official_notice",
        authority_level="B",
        source_name="测试高校官网",
        source_url=url,
        source_platform="university_website",
        is_official=False,
        is_verified=True,
        credibility_score=80,
        reliability_tier=2,
        verification_status="school_confirmed",
        raw_title="测试高校官方通知",
        is_demo=False,
    )
    db_session.add(source)
    db_session.flush()
    return source


def _s_source(db_session, comp: Competition, url: str) -> CompetitionSource:
    source = CompetitionSource(
        competition_id=comp.id,
        source_type="government_official_notice",
        authority_level="S",
        source_name="教育部官方通知",
        source_url=url,
        source_platform="official_website",
        is_official=True,
        is_verified=True,
        credibility_score=100,
        reliability_tier=1,
        verification_status="verified_official",
        raw_title="教育部官方通知",
        is_demo=False,
    )
    db_session.add(source)
    db_session.flush()
    return source


def _registry(tmp_path: Path, entries: list[dict]) -> Path:
    registry_dir = tmp_path / "v13-registry"
    registry_dir.mkdir(exist_ok=True)
    (registry_dir / "entries.json").write_text(
        json.dumps({"entries": entries}, ensure_ascii=False),
        encoding="utf-8",
    )
    return registry_dir


def test_secondary_source_cannot_verify_competition_identity(db_session) -> None:
    comp = _comp(db_session, "v13次级来源不可验证身份")
    _b_source(db_session, comp, "https://edu.example.com/n1")
    db_session.commit()
    assert is_identity_qualified(default_evidence_level("university_official_notice", "B")) is False
    service = FactIntelligenceService()
    service.refresh_source_tiers(db_session)
    service.refresh_verification(db_session)
    db_session.commit()
    db_session.refresh(comp)
    assert comp.verification_status != "verified_official"


def test_secondary_field_does_not_overwrite_primary_field(db_session, tmp_path) -> None:
    comp = _comp(db_session, "v13次级不覆盖主级", organizer="教育部")
    _s_source(db_session, comp, "https://gov.example.com/official")
    _b_source(db_session, comp, "https://edu.example.com/n2")
    db_session.commit()
    registry = _registry(
        tmp_path,
        [
            {
                "competition_id": comp.id,
                "name": comp.name,
                "competition_fields": {
                    "organizer": {
                        "value": "某省级协会（高校通知口径）",
                        "source_url": "https://edu.example.com/n2",
                        "source_type": "university_official_notice",
                        "authority_level": "B",
                        "evidence_level": "LEVEL_3",
                        "source_scope": "university_official_notice_quote",
                        "notes": "仅测试：不得覆盖主级事实",
                    }
                },
            }
        ],
    )
    service = V12FactEnrichmentService()
    service.run(db_session, registry_dir=registry, dry_run=False)
    db_session.commit()
    db_session.refresh(comp)
    assert comp.organizer == "教育部"
    secondary_facts = db_session.execute(
        select(CompetitionFactSource).where(
            CompetitionFactSource.competition_id == comp.id,
            CompetitionFactSource.field_name == "organizer",
            CompetitionFactSource.source_url == "https://edu.example.com/n2",
        )
    ).scalars().all()
    assert secondary_facts == []


def test_campus_deadline_remains_school_scoped(db_session, tmp_path) -> None:
    comp = _comp(db_session, "v13校内截止保持学校层")
    university = University(name="v13截止测试大学", province="北京", city="北京")
    db_session.add(university)
    db_session.flush()
    edition = CompetitionEdition(competition_id=comp.id, year=2026)
    db_session.add(edition)
    db_session.flush()
    school = _b_source(db_session, comp, "https://edu.example.com/n3")
    db_session.commit()
    # Level 3 evidence may not enter the national official deadline column.
    registry = _registry(
        tmp_path,
        [
            {
                "competition_id": comp.id,
                "name": comp.name,
                "editions": [
                    {
                        "year": 2026,
                        "fields": {"official_registration_deadline": "2026-09-30T23:59:59"},
                        "source_url": school.source_url,
                        "source_type": "university_official_notice",
                        "authority_level": "B",
                        "evidence_level": "LEVEL_3",
                        "source_scope": "campus_deadline_test",
                    }
                ],
            }
        ],
    )
    service = V12FactEnrichmentService()
    service.run(db_session, registry_dir=registry, dry_run=False)
    db_session.add(
        SchoolCompetition(
            school_id=university.id,
            competition_id=comp.id,
            competition_edition_id=edition.id,
            campus_registration_deadline=__import__("datetime").datetime(2026, 9, 30, 23, 59, 59),
            record_status="school_confirmed",
        )
    )
    db_session.commit()
    db_session.refresh(edition)
    assert edition.official_registration_deadline is None
    row = db_session.execute(
        select(SchoolCompetition).where(
            SchoolCompetition.competition_id == comp.id,
            SchoolCompetition.school_id == university.id,
        )
    ).scalar_one()
    assert row.campus_registration_deadline is not None


def test_university_notice_supports_participant_only_when_explicit(db_session, tmp_path) -> None:
    comp = _comp(db_session, "v13参赛对象需明确陈述")
    source = _b_source(db_session, comp, "https://edu.example.com/n4")
    db_session.commit()
    explicit = _registry(
        tmp_path,
        [
            {
                "competition_id": comp.id,
                "name": comp.name,
                "competition_fields": {
                    "target_students": {
                        "value": "普通高校全日制在校本专科学生（高校通知引述全国规则）",
                        "source_url": source.source_url,
                        "source_type": "university_official_notice",
                        "authority_level": "B",
                        "evidence_level": "LEVEL_3",
                        "source_scope": "university_official_notice_quoting_national_rule",
                        "notes": "原文明确引述全国参赛对象",
                    }
                },
            }
        ],
    )
    service = V12FactEnrichmentService()
    service.run(db_session, registry_dir=explicit, dry_run=False)
    db_session.commit()
    db_session.refresh(comp)
    assert comp.target_students is not None
    fact = db_session.execute(
        select(CompetitionFactSource).where(
            CompetitionFactSource.competition_id == comp.id,
            CompetitionFactSource.field_name == "target_students",
        )
    ).scalar_one()
    assert fact.source_level == "LEVEL_3"
    assert "evidence_level=LEVEL_3" in fact.notes
    # A registry entry without source_scope/notes must be refused.
    comp2 = _comp(db_session, "v13参赛对象未标注来源")
    source2 = _b_source(db_session, comp2, "https://edu.example.com/n5")
    db_session.commit()
    unmarked = _registry(
        tmp_path,
        [
            {
                "competition_id": comp2.id,
                "name": comp2.name,
                "competition_fields": {
                    "target_students": {
                        "value": "无来源标注的填写",
                        "source_url": source2.source_url,
                        "source_type": "university_official_notice",
                        "authority_level": "B",
                        "evidence_level": "LEVEL_3",
                    }
                },
            }
        ],
    )
    service.run(db_session, registry_dir=unmarked, dry_run=False)
    db_session.commit()
    db_session.refresh(comp2)
    assert comp2.target_students is None


def test_organizer_page_can_be_official_homepage() -> None:
    assert (
        evidence_allowed(
            "official_website",
            "LEVEL_3",
            spec={"homepage_type": "organizer_page"},
        )
        is True
    )
    assert (
        classify_homepage("https://www.cms.org.cn/competitions/cmc", "organizer_page")
        == "organizer_page"
    )


def test_third_party_page_cannot_become_official_homepage() -> None:
    assert (
        evidence_allowed(
            "official_website",
            "LEVEL_3",
            spec={"homepage_type": "none"},
        )
        is False
    )
    assert classify_homepage("https://www.saikr.com/viewevent/123", "third_party_platform") == "none"
    assert classify_homepage("https://baike.baidu.com/item/x", "manual") == "none"


def test_field_conflicts_are_preserved(db_session, tmp_path) -> None:
    comp = _comp(db_session, "v13冲突保留", organizer="中国官方主办")
    primary = _s_source(db_session, comp, "https://gov.example.com/primary")
    secondary = _b_source(db_session, comp, "https://edu.example.com/n6")
    db_session.commit()
    registry = _registry(
        tmp_path,
        [
            {
                "competition_id": comp.id,
                "name": comp.name,
                "competition_fields": {
                    "organizer": {
                        "value": "另一协会",
                        "source_url": secondary.source_url,
                        "source_type": "university_official_notice",
                        "authority_level": "B",
                        "evidence_level": "LEVEL_3",
                        "source_scope": "conflict_test",
                    }
                },
            }
        ],
    )
    service = V12FactEnrichmentService()
    report = service.run(db_session, registry_dir=registry, dry_run=False)
    db_session.commit()
    db_session.refresh(comp)
    assert comp.organizer == "中国官方主办"
    assert report["counters"]["competition_fields_conflict"] >= 1
    rows = db_session.execute(
        select(CompetitionFactSource).where(
            CompetitionFactSource.competition_id == comp.id,
            CompetitionFactSource.field_name == "organizer",
        )
    ).scalars().all()
    assert all(row.source_url != secondary.source_url for row in rows)


def test_rerun_is_idempotent(db_session, tmp_path) -> None:
    comp = _comp(db_session, "v13幂等")
    source = _b_source(db_session, comp, "https://edu.example.com/n7")
    db_session.commit()
    entry = {
        "competition_id": comp.id,
        "name": comp.name,
        "competition_fields": {
            "organizer": {
                "value": "由高校通知明确引述的全国主办方",
                "source_url": source.source_url,
                "source_type": "university_official_notice",
                "authority_level": "B",
                "evidence_level": "LEVEL_3",
                "source_scope": "rerun_test",
            }
        },
        "editions": [
            {
                "year": 2026,
                "fields": {"edition_name": "2026届（高校官方新闻确认）"},
                "source_url": source.source_url,
                "source_type": "university_official_notice",
                "authority_level": "B",
                "evidence_level": "LEVEL_3",
                "source_scope": "rerun_test_edition",
            }
        ],
    }
    registry = _registry(tmp_path, [entry])
    service = V12FactEnrichmentService()
    service.run(db_session, registry_dir=registry, dry_run=False)
    service.run(db_session, registry_dir=registry, dry_run=False)
    db_session.commit()
    db_session.refresh(comp)
    assert comp.organizer == "由高校通知明确引述的全国主办方"
    source_count = db_session.scalar(
        select(func.count())
        .select_from(CompetitionSource)
        .where(
            CompetitionSource.competition_id == comp.id,
            CompetitionSource.source_url == source.source_url,
        )
    )
    assert source_count == 1
    edition_count = db_session.scalar(
        select(func.count())
        .select_from(CompetitionEdition)
        .where(
            CompetitionEdition.competition_id == comp.id,
            CompetitionEdition.year == 2026,
        )
    )
    assert edition_count == 1
    fact_count = db_session.scalar(
        select(func.count())
        .select_from(CompetitionFactSource)
        .where(
            CompetitionFactSource.competition_id == comp.id,
            CompetitionFactSource.field_name == "organizer",
        )
    )
    assert fact_count == 1
