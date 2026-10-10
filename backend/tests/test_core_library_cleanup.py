"""V11 core-library cleanup tests (display rules + data integrity)."""

from datetime import datetime, timezone

from sqlalchemy import func, select

from app.models import (
    Competition,
    CompetitionAlias,
    CompetitionEdition,
    CompetitionSource,
)
from app.repositories.competition_repository import CompetitionRepository
from app.services.authority_match_service import AuthorityMatchService
from app.services.competition_normalization_service import CompetitionNormalizationService
from app.services.fact_intelligence_service import FactIntelligenceService
from app.services.source_authority_service import can_prove


def _comp(db_session, name: str, **kwargs) -> Competition:
    payload = {
        "name": name,
        "organizer": "测试主办",
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


def test_pending_competition_cannot_masquerade_as_verified(db_session) -> None:
    comp = _comp(db_session, "待核验不可冒充正式测试")
    db_session.add(
        CompetitionSource(
            competition_id=comp.id,
            source_type="university_official_notice",
            source_url="https://edu.example.com/n",
            is_verified=True,
            is_official=False,
            is_demo=False,
        )
    )
    db_session.commit()
    service = FactIntelligenceService()
    service.refresh_source_tiers(db_session)
    service.refresh_verification(db_session)
    db_session.commit()
    db_session.refresh(comp)
    assert comp.verification_status != "verified_official"
    assert comp.is_official_verified is False


def test_duplicate_cannot_enter_official_hall(db_session) -> None:
    dup = _comp(db_session, "大厅排除重复测试", verification_status="duplicate")
    db_session.commit()
    rows = CompetitionRepository().list_competitions(db_session, limit=200, offset=0)
    ids = [row.id for row in rows]
    assert dup.id not in ids


def test_non_competition_cannot_enter_competition_hall(db_session) -> None:
    exhibition = _comp(
        db_session,
        "大厅排除展览测试",
        is_competition=False,
        entity_type="exhibition",
    )
    db_session.commit()
    rows = CompetitionRepository().list_competitions(db_session, limit=200, offset=0)
    ids = [row.id for row in rows]
    assert exhibition.id not in ids


def test_university_level_cannot_overwrite_competition_authority(db_session) -> None:
    comp = _comp(db_session, "高校等级不可污染测试")
    db_session.add(
        CompetitionSource(
            competition_id=comp.id,
            source_type="university_policy",
            source_url="https://edu.example.com/policy",
            is_verified=True,
            is_official=True,
            is_demo=False,
        )
    )
    db_session.commit()
    assert can_prove("university_policy", "competition_level") is False
    service = FactIntelligenceService()
    service.refresh_source_tiers(db_session)
    service.refresh_verification(db_session)
    db_session.commit()
    db_session.refresh(comp)
    assert comp.competition_level is None
    assert comp.verification_status != "verified_official"


def test_campus_deadline_cannot_overwrite_official_deadline(db_session) -> None:
    comp = _comp(db_session, "校内截止不可覆盖官方测试")
    edition = CompetitionEdition(
        competition_id=comp.id,
        year=2026,
        edition_name="2026校内截止不可覆盖官方测试",
        official_registration_deadline=datetime(2026, 9, 25, 12, 0),
        verification_status="verified_official",
    )
    db_session.add(edition)
    db_session.commit()
    assert can_prove("university_official_notice", "official_registration_deadline") is False
    assert can_prove("university_official_notice", "campus_registration_deadline") is True
    db_session.refresh(edition)
    assert edition.official_registration_deadline == datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)


def test_empty_co_organizers_are_render_safe(client, db_session) -> None:
    comp = _comp(db_session, "无联合主办渲染安全测试", verification_status="verified_official")
    db_session.commit()
    detail = client.get(f"/api/competitions/{comp.id}").json()["data"]
    assert detail["co_organizers"] == []
    assert detail["undertakers"] == []


def test_historical_alias_does_not_create_duplicate(db_session) -> None:
    comp = _comp(db_session, "别名不重复测试竞赛")
    normalizer = CompetitionNormalizationService()
    first = normalizer.ensure_alias(
        db_session,
        comp,
        "别名不重复旧称",
        source="test",
        confidence=1.0,
        is_verified=True,
    )
    second = normalizer.ensure_alias(
        db_session,
        comp,
        "别名不重复旧称",
        source="test",
        confidence=1.0,
        is_verified=True,
    )
    db_session.commit()
    assert first.id == second.id
    count = db_session.scalar(
        select(func.count())
        .select_from(CompetitionAlias)
        .where(CompetitionAlias.competition_id == comp.id)
    )
    assert count == 1


def test_child_track_does_not_become_independent_competition(db_session) -> None:
    parent = _comp(db_session, "系列赛事主体测试")
    child = _comp(
        db_session,
        "系列赛事子赛道测试",
        parent_competition_id=parent.id,
        entity_type="track",
        competition_type="track",
    )
    db_session.commit()
    match = AuthorityMatchService().match(db_session, "系列赛事主体测试")
    assert match.competition is not None
    assert match.competition.id == parent.id
    assert match.competition.id != child.id


def test_rerun_cleanup_is_idempotent(db_session) -> None:
    comp = _comp(db_session, "幂等清理测试竞赛")
    normalizer = CompetitionNormalizationService()
    alias = "幂等清理旧称"
    normalizer.ensure_alias(db_session, comp, alias, source="core", is_verified=True)
    db_session.commit()
    before = db_session.scalar(
        select(func.count())
        .select_from(CompetitionAlias)
        .where(CompetitionAlias.competition_id == comp.id)
    )
    normalizer.ensure_alias(db_session, comp, alias, source="core", is_verified=True)
    db_session.commit()
    after = db_session.scalar(
        select(func.count())
        .select_from(CompetitionAlias)
        .where(CompetitionAlias.competition_id == comp.id)
    )
    assert before == after == 1


def test_provenance_remains_intact_after_refresh(db_session) -> None:
    comp = _comp(db_session, "来源溯源保持测试")
    source = CompetitionSource(
        competition_id=comp.id,
        source_type="competition_official_website",
        source_url="https://official.example.com/",
        source_name="官方站",
        raw_title="官方站标题",
        metadata_json={"evidence_file": "data/raw/authority/official_sites/example.html"},
        is_verified=True,
        is_official=True,
        is_demo=False,
    )
    db_session.add(source)
    db_session.commit()
    service = FactIntelligenceService()
    service.refresh_source_tiers(db_session)
    service.refresh_verification(db_session)
    db_session.commit()
    db_session.refresh(source)
    assert source.source_url == "https://official.example.com/"
    assert source.source_name == "官方站"
    assert source.raw_title == "官方站标题"
    assert source.metadata_json == {"evidence_file": "data/raw/authority/official_sites/example.html"}
