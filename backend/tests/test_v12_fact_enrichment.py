"""V12 evidence-grounded enrichment tests.

Covers the ten acceptance checks from the v12 round:
edition facts do not leak into permanent fields, campus facts cannot drive
official fields, official website requires S/A evidence, empty display fields
stay empty, history uses CompetitionEdition, dedupe is idempotent, sources are
not duplicated on rerun, unofficial URLs are refused, current-edition status
requires official evidence, and every change keeps a revision trail.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from app.models import (
    Competition,
    CompetitionEdition,
    CompetitionFactRevision,
    CompetitionFactSource,
    CompetitionSource,
    University,
    UniversityCompetitionEditionRelation,
)
from app.services.fact_intelligence_service import FactIntelligenceService
from app.services.source_authority_service import can_prove
from app.services.v12_fact_enrichment_service import V12FactEnrichmentService


def _comp(db_session, name: str = "v12测试赛事", **kwargs) -> Competition:
    payload = {
        "name": name,
        "organizer": "稳定主办单位",
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


def _add_source(
    db_session,
    competition: Competition,
    *,
    source_type: str,
    url: str,
    level: str,
    verified: bool = True,
) -> CompetitionSource:
    source = CompetitionSource(
        competition_id=competition.id,
        source_type=source_type,
        authority_level=level,
        source_name="测试来源",
        source_url=url,
        source_platform="official_website",
        is_official=level in {"S", "A"},
        is_verified=verified,
        credibility_score=100 if level == "S" else 80,
        reliability_tier={"S": 1, "A": 2, "B": 2, "C": 3}.get(level, 4),
        verification_status="verified_official" if level in {"S", "A"} else "school_confirmed",
        raw_title="测试来源标题",
        is_demo=False,
    )
    db_session.add(source)
    db_session.flush()
    return source


def _registry(tmp_path: Path, entries: list[dict]) -> Path:
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir(exist_ok=True)
    (registry_dir / "entries.json").write_text(
        json.dumps({"entries": entries}, ensure_ascii=False),
        encoding="utf-8",
    )
    return registry_dir


def test_edition_facts_do_not_overwrite_permanent_organizer(db_session, tmp_path) -> None:
    comp = _comp(db_session, "届次不污染永久主办测试")
    source = _add_source(
        db_session,
        comp,
        source_type="competition_official_website",
        url="https://official.example.com/",
        level="S",
    )
    db_session.commit()
    registry = _registry(
        tmp_path,
        [
            {
                "competition_id": comp.id,
                "name": comp.name,
                "editions": [
                    {
                        "year": 2025,
                        "fields": {
                            "edition_name": "2025届测试（某大学承办）",
                            "host_location": "某大学",
                        },
                        "source_url": source.source_url,
                    }
                ],
            }
        ],
    )
    service = V12FactEnrichmentService()
    service.run(db_session, registry_dir=registry, dry_run=False)
    db_session.commit()
    db_session.refresh(comp)
    assert comp.organizer == "稳定主办单位"
    edition = db_session.execute(
        select(CompetitionEdition).where(
            CompetitionEdition.competition_id == comp.id,
            CompetitionEdition.year == 2025,
        )
    ).scalar_one()
    assert edition.host_location == "某大学"
    assert edition.verification_status == "verified_official"


def test_campus_deadline_cannot_drive_official_deadline(db_session, tmp_path) -> None:
    comp = _comp(db_session, "校内截止不覆盖官方截止测试")
    source = _add_source(
        db_session,
        comp,
        source_type="university_official_notice",
        url="https://edu.example.com/notice",
        level="B",
    )
    db_session.add(
        CompetitionEdition(
            competition_id=comp.id,
            year=2026,
            official_registration_deadline=None,
        )
    )
    db_session.commit()
    registry = _registry(
        tmp_path,
        [
            {
                "competition_id": comp.id,
                "name": comp.name,
                "editions": [
                    {
                        "year": 2026,
                        "fields": {
                            "official_registration_deadline": "2026-09-01T23:59:59"
                        },
                        "source_url": source.source_url,
                    }
                ],
            }
        ],
    )
    assert can_prove("university_official_notice", "official_registration_deadline") is False
    service = V12FactEnrichmentService()
    service.run(db_session, registry_dir=registry, dry_run=False)
    db_session.commit()
    edition = db_session.execute(
        select(CompetitionEdition).where(
            CompetitionEdition.competition_id == comp.id,
            CompetitionEdition.year == 2026,
        )
    ).scalar_one()
    assert edition.official_registration_deadline is None


def test_missing_official_website_remains_null_without_official_source(db_session, tmp_path) -> None:
    comp = _comp(db_session, "无官网来源保持空值测试")
    source = _add_source(
        db_session,
        comp,
        source_type="university_official_notice",
        url="https://edu.example.com/notice2",
        level="B",
    )
    db_session.commit()
    registry = _registry(
        tmp_path,
        [
            {
                "competition_id": comp.id,
                "name": comp.name,
                "competition_fields": {
                    "official_website": {
                        "value": "https://not-official.example.com/",
                        "source_url": source.source_url,
                    }
                },
            }
        ],
    )
    service = V12FactEnrichmentService()
    service.run(db_session, registry_dir=registry, dry_run=False)
    db_session.commit()
    db_session.refresh(comp)
    assert comp.official_website is None


def test_empty_co_organizer_fields_stay_hidden_in_detail_api(client, db_session) -> None:
    comp = _comp(db_session, "无联合主办渲染空安全测试")
    db_session.commit()
    detail = client.get(f"/api/competitions/{comp.id}").json()["data"]
    assert detail["co_organizers"] == []
    assert detail["undertakers"] == []
    assert detail["guiding_organizations"] == []


def test_history_uses_competition_edition(client, db_session) -> None:
    comp = _comp(
        db_session,
        "历史读取真实届次测试",
        history_timeline=[{"year": 2020, "title": "旧文本历史（仅作fallback）"}],
    )
    db_session.add(
        CompetitionEdition(
            competition_id=comp.id,
            year=2026,
            edition_name="2026届官方记录",
            official_notice_url="https://official.example.com/2026",
            verification_status="verified_official",
            is_verified=True,
        )
    )
    db_session.commit()
    detail = client.get(f"/api/competitions/{comp.id}").json()["data"]
    assert any(edition["year"] == 2026 for edition in detail["editions"])
    # legacy text fields remain available only as fallback, never removed
    assert "history_timeline" in detail


def test_duplicate_edition_not_created_on_rerun(db_session, tmp_path) -> None:
    comp = _comp(db_session, "重复届次不创建测试")
    source = _add_source(
        db_session,
        comp,
        source_type="official_notice",
        url="https://official.example.com/2025-notice",
        level="S",
    )
    db_session.commit()
    entry = {
        "competition_id": comp.id,
        "name": comp.name,
        "editions": [
            {
                "year": 2025,
                "fields": {"edition_name": "2025届官方记录"},
                "source_url": source.source_url,
            }
        ],
    }
    registry = _registry(tmp_path, [entry])
    service = V12FactEnrichmentService()
    service.run(db_session, registry_dir=registry, dry_run=False)
    service.run(db_session, registry_dir=registry, dry_run=False)
    db_session.commit()
    count = db_session.scalar(
        select(func.count())
        .select_from(CompetitionEdition)
        .where(
            CompetitionEdition.competition_id == comp.id,
            CompetitionEdition.year == 2025,
        )
    )
    assert count == 1


def test_rerun_does_not_duplicate_sources(db_session, tmp_path) -> None:
    comp = _comp(db_session, "来源不重复测试")
    source = _add_source(
        db_session,
        comp,
        source_type="official_notice",
        url="https://official.example.com/notice-x",
        level="S",
    )
    db_session.commit()
    entry = {
        "competition_id": comp.id,
        "name": comp.name,
        "editions": [
            {
                "year": 2026,
                "fields": {"edition_name": "2026届"},
                "source_url": source.source_url,
            }
        ],
    }
    registry = _registry(tmp_path, [entry])
    service = V12FactEnrichmentService()
    service.run(db_session, registry_dir=registry, dry_run=False)
    service.run(db_session, registry_dir=registry, dry_run=False)
    db_session.commit()
    count = db_session.scalar(
        select(func.count())
        .select_from(CompetitionSource)
        .where(
            CompetitionSource.competition_id == comp.id,
            CompetitionSource.source_url == source.source_url,
        )
    )
    assert count == 1


def test_unofficial_url_cannot_become_official_website(db_session) -> None:
    comp = _comp(db_session, "非官方网址拒绝测试")
    source = _add_source(
        db_session,
        comp,
        source_type="university_official_notice",
        url="https://edu.example.com/policy",
        level="B",
    )
    db_session.commit()
    assert can_prove(source.source_type, "official_website") is False
    service = FactIntelligenceService()
    service.refresh_source_tiers(db_session)
    service.refresh_verification(db_session)
    db_session.commit()
    db_session.refresh(comp)
    assert comp.official_website is None
    assert comp.verification_status != "verified_official"


def test_current_edition_requires_official_evidence(db_session) -> None:
    comp = _comp(db_session, "当前届需官方证据测试")
    university = University(name="v12测试大学", province="湖北", city="武汉")
    db_session.add(university)
    db_session.flush()
    edition = CompetitionEdition(
        competition_id=comp.id,
        year=2026,
        current_status="registration_open",
    )
    db_session.add(edition)
    db_session.flush()
    school = _add_source(
        db_session,
        comp,
        source_type="university_official_notice",
        url="https://edu.example.com/current-notice",
        level="B",
    )
    school.competition_edition_id = edition.id
    db_session.add(
        UniversityCompetitionEditionRelation(
            university_id=university.id,
            competition_edition_id=edition.id,
            source_type="university_official_notice",
            source_platform="university_website",
            source_name="v12测试大学本科生院",
            notice_type="registration_notice",
            notice_title="v12测试大学校内报名通知",
            internal_notice_url="https://edu.example.com/current-notice",
            organizing_department="v12测试大学本科生院",
            observed_at=datetime.now(timezone.utc),
            is_verified=True,
            is_demo=False,
        )
    )
    db_session.commit()
    service = FactIntelligenceService()
    service.refresh_source_tiers(db_session)
    service.refresh_verification(db_session)
    db_session.commit()
    db_session.refresh(edition)
    assert edition.verification_status == "school_confirmed"
    official = _add_source(
        db_session,
        comp,
        source_type="competition_official_website",
        url="https://official.example.com/current-site",
        level="S",
    )
    official.competition_edition_id = edition.id
    db_session.commit()
    service.refresh_source_tiers(db_session)
    service.refresh_verification(db_session)
    db_session.commit()
    db_session.refresh(edition)
    assert edition.verification_status == "verified_official"


def test_history_changes_keep_provenance_revision(db_session, tmp_path) -> None:
    comp = _comp(db_session, "修订溯源保留测试", target_students="旧的未经核验概括")
    source = _add_source(
        db_session,
        comp,
        source_type="government_official_notice",
        url="https://gov.example.com/notice",
        level="S",
    )
    db_session.commit()
    registry = _registry(
        tmp_path,
        [
            {
                "competition_id": comp.id,
                "name": comp.name,
                "competition_fields": {
                    "target_students": {
                        "value": "官方规则明确的参赛对象",
                        "source_url": source.source_url,
                        "allow_overwrite": True,
                        "overwrite_reason": "测试覆盖旧值",
                    }
                },
            }
        ],
    )
    service = V12FactEnrichmentService()
    service.run(db_session, registry_dir=registry, dry_run=False)
    db_session.commit()
    revision = db_session.execute(
        select(CompetitionFactRevision).where(
            CompetitionFactRevision.competition_id == comp.id,
            CompetitionFactRevision.field_name == "target_students",
        )
    ).scalar_one()
    assert revision.old_value == "旧的未经核验概括"
    assert revision.new_value == "官方规则明确的参赛对象"
    assert revision.source_url == source.source_url
    fact_row = db_session.execute(
        select(CompetitionFactSource).where(
            CompetitionFactSource.competition_id == comp.id,
            CompetitionFactSource.field_name == "target_students",
            CompetitionFactSource.source_url == source.source_url,
        )
    ).scalar_one()
    assert fact_row.fact_value == "官方规则明确的参赛对象"
