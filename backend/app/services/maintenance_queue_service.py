"""V14 core-library maintenance queue + per-competition refresh.

The user-facing product only shows what is proven; anything missing becomes a
maintenance task instead of a UI placeholder. `refresh_competition_facts` lets
an operator update a single Competition (and its editions) when, for example,
the 2027 edition of one event is published - no full-library rerun needed.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Competition, CompetitionEdition, CompetitionFactSource, CompetitionSource
from app.services.source_authority_service import (
    authority_level_for,
    competition_status_from_source_levels,
)


JS_SHELL_EVIDENCE = {
    "lanqiao_home",
    "3chuang_home",
    "chinaneccs_home",
    "c4best_home",
    "cubec_home3",
    "ican_details",
    "jdsxj_eduyun_home",
}


def refresh_competition_facts(db: Session, competition_id: int) -> dict:
    """Recompute authority/verification for one competition and its editions."""
    competition = db.get(Competition, competition_id)
    if competition is None:
        return {"ok": False, "error": "competition not found"}
    before = {
        "competition": competition.verification_status,
        "editions": {
            edition.year: edition.verification_status for edition in competition.editions
        },
    }
    if competition.verification_status not in {"duplicate", "non_competition"}:
        sources = [source for source in competition.sources if not source.is_demo]
        for source in sources:
            level = authority_level_for(source.source_type) or "D"
            source.authority_level = level
            source.reliability_tier = {"S": 1, "A": 2, "B": 2, "C": 3, "D": 4}.get(level, 4)
            source.verification_status = (
                "verified_official"
                if source.is_verified and level in {"S", "A"}
                else "school_confirmed"
                if source.is_verified and level in {"B", "C"}
                else "unverified"
            )
        active_sources = [s for s in sources if s.is_verified]
        proof_sources = [s for s in active_sources if s.source_type != "university_policy"]
        verified_levels = [
            s.authority_level or authority_level_for(s.source_type)
            for s in proof_sources
        ]
        status = competition_status_from_source_levels(
            verified_levels,
            has_any_source=bool(sources),
            entity_type=competition.entity_type,
        )
        if status == "unverified" and any(
            s.source_type == "university_policy" for s in active_sources
        ):
            status = "pending_verification"
        competition.verification_status = status
        competition.is_official_verified = status in {"verified_official", "authority_confirmed"}
        for edition in competition.editions:
            edition_levels = {
                s.authority_level or authority_level_for(s.source_type)
                for s in edition.sources
                if s.is_verified and not s.is_demo
            }
            relation_evidence = any(
                relation.is_verified and not relation.is_demo
                for relation in edition.university_relations
            )
            if "S" in edition_levels:
                edition.verification_status = "verified_official"
                edition.is_verified = True
            elif "A" in edition_levels:
                edition.verification_status = "authority_confirmed"
                edition.is_verified = True
            elif relation_evidence:
                edition.verification_status = "school_confirmed"
                edition.is_verified = True
            elif edition.sources or edition.source_url or edition.official_notice_url:
                edition.verification_status = "pending_verification"
                edition.is_verified = True
            else:
                edition.verification_status = "unverified"
                edition.is_verified = False
    db.flush()
    db.refresh(competition)
    after = {
        "competition": competition.verification_status,
        "editions": {
            edition.year: edition.verification_status for edition in competition.editions
        },
    }
    db.commit()
    return {
        "ok": True,
        "competition_id": competition_id,
        "before": before,
        "after": after,
    }


def generate_maintenance_queue(db: Session) -> dict:
    """Classify every frozen core competition into actionable maintenance tasks."""
    core = list(
        db.execute(
            select(Competition).where(
                Competition.is_demo.is_(False),
                Competition.is_competition.is_(True),
                Competition.verification_status.in_(
                    ("verified_official", "authority_confirmed", "association_confirmed")
                ),
            )
        ).scalars()
    )
    core.sort(key=lambda c: c.id)
    tasks: list[dict] = []
    counters: Counter[str] = Counter()
    website_evidence_shells = set()
    rows = db.execute(
        select(CompetitionSource.competition_id, CompetitionSource.metadata_json).where(
            CompetitionSource.source_type.in_(
                (
                    "competition_official_website",
                    "official_competition_website",
                    "competition_official_site",
                )
            )
        )
    ).all()
    for competition_id, metadata in rows:
        evidence = (metadata or {}).get("evidence_file") or ""
        if any(token in evidence for token in JS_SHELL_EVIDENCE):
            website_evidence_shells.add(competition_id)

    for competition in core:
        editions = list(competition.editions)
        official_years = sorted(
            {
                edition.year
                for edition in editions
                if edition.verification_status in {"verified_official", "authority_confirmed"}
            },
            reverse=True,
        )
        has_latest_official = any(
            edition.year >= 2026
            and edition.verification_status in {"verified_official", "authority_confirmed"}
            for edition in editions
        )
        item: dict = {
            "competition_id": competition.id,
            "name": competition.name,
            "verification_status": competition.verification_status,
            "tasks": [],
        }
        if not (competition.organizer or competition.co_organizers or competition.undertakers or competition.guiding_organizations):
            item["tasks"].append("missing_organizer")
            counters["missing_organizer"] += 1
        if not competition.official_website:
            item["tasks"].append("missing_official_page")
            counters["missing_official_page"] += 1
            if competition.id in website_evidence_shells:
                item["tasks"].append("official_site_js_only")
                counters["official_site_js_only"] += 1
        else:
            if competition.id in website_evidence_shells:
                item["tasks"].append("official_site_js_only")
                counters["official_site_js_only"] += 1
        if not competition.target_students:
            item["tasks"].append("missing_participant_rule")
            counters["missing_participant_rule"] += 1
        if not has_latest_official:
            item["tasks"].append("missing_latest_edition")
            counters["missing_latest_edition"] += 1
        if len(official_years) < 2:
            item["tasks"].append("missing_history")
            counters["missing_history"] += 1
        if item["tasks"]:
            tasks.append(item)

    manual_review_ids = [
        row[0]
        for row in db.execute(
            select(Competition.id)
            .where(
                Competition.is_demo.is_(False),
                Competition.verification_status.in_(
                    ("pending_verification", "school_confirmed", "suspected")
                ),
            )
            .order_by(Competition.id)
        ).all()
    ]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "core_total": len(core),
        "task_summary": dict(sorted(counters.items())),
        "maintenance_tasks": tasks,
        "manual_review_competitions": manual_review_ids,
        "note": (
            "缺失不阻塞产品上线；维护人员按 competition_id 使用 "
            "refresh_competition_facts 单赛事更新，不重跑全库。"
        ),
    }
