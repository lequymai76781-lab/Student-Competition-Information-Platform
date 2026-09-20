"""V14 Release-Candidate acceptance tests (hall display + on-demand refresh)."""

from __future__ import annotations

from sqlalchemy import select

from app.models import Competition, CompetitionEdition, CompetitionSource
from app.repositories.competition_repository import CompetitionRepository
from app.services.maintenance_queue_service import (
    generate_maintenance_queue,
    refresh_competition_facts,
)


def _comp(db_session, name: str = "v14测试赛事", **kwargs) -> Competition:
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


def _add_source(db_session, comp: Competition, level: str, url: str) -> CompetitionSource:
    source = CompetitionSource(
        competition_id=comp.id,
        source_type=(
            "competition_official_website"
            if level == "S"
            else "university_official_notice"
        ),
        authority_level=level,
        source_name="测试来源",
        source_url=url,
        is_official=level == "S",
        is_verified=True,
        credibility_score=100 if level == "S" else 80,
        reliability_tier=1 if level == "S" else 2,
        verification_status="verified_official" if level == "S" else "school_confirmed",
        is_demo=False,
    )
    db_session.add(source)
    db_session.flush()
    return source


def test_hall_hides_no_evidence_unverified_but_keeps_pending(db_session) -> None:
    no_evidence = _comp(db_session, "v14无证据实体不进大厅")
    pending = _comp(
        db_session,
        "v14信息核验中允许带标签展示",
        verification_status="pending_verification",
    )
    _add_source(db_session, pending, "B", "https://edu.example.com/v14-a")
    db_session.add(
        CompetitionEdition(
            competition_id=pending.id,
            year=2026,
            verification_status="pending_verification",
        )
    )
    db_session.commit()
    rows = CompetitionRepository().list_competitions(db_session, limit=200, offset=0)
    ids = [row.id for row in rows]
    assert no_evidence.id not in ids
    assert pending.id in ids


def test_hall_excludes_duplicate_and_non_competition(db_session) -> None:
    dup = _comp(db_session, "v14重复不进大厅", verification_status="duplicate")
    award = _comp(
        db_session,
        "v14奖项不进大厅",
        verification_status="non_competition",
        is_competition=False,
        entity_type="award",
    )
    db_session.commit()
    rows = CompetitionRepository().list_competitions(db_session, limit=200, offset=0)
    ids = [row.id for row in rows]
    assert dup.id not in ids
    assert award.id not in ids


def test_refresh_competition_facts_is_single_scope(db_session) -> None:
    target = _comp(db_session, "v14单赛刷新目标")
    _add_source(db_session, target, "S", "https://official.example.com/v14-s")
    target.verification_status = "pending_verification"
    untouched = _comp(
        db_session,
        "v14不应被触碰赛事",
        verification_status="pending_verification",
    )
    _add_source(db_session, untouched, "S", "https://official.example.com/v14-other")
    db_session.commit()
    result = refresh_competition_facts(db_session, target.id)
    db_session.expire_all()
    db_session.refresh(target)
    db_session.refresh(untouched)
    assert result["ok"] is True
    assert target.verification_status == "verified_official"
    # The second competition must remain untouched (no global recompute).
    assert untouched.verification_status == "pending_verification"


def test_maintenance_queue_only_covers_confirmed_core(db_session) -> None:
    core = _comp(
        db_session,
        "v14核心维护任务",
        verification_status="authority_confirmed",
        organizer=None,
        official_website=None,
    )
    _add_source(db_session, core, "A", "https://cahe.example.com/directory")
    non_core = _comp(
        db_session,
        "v14不进入维护队列",
        verification_status="pending_verification",
    )
    db_session.commit()
    queue = generate_maintenance_queue(db_session)
    ids = {row["competition_id"] for row in queue["maintenance_tasks"]}
    assert core.id in ids
    assert non_core.id not in ids
    assert "missing_organizer" in {
        task
        for row in queue["maintenance_tasks"]
        if row["competition_id"] == core.id
        for task in row["tasks"]
    }
