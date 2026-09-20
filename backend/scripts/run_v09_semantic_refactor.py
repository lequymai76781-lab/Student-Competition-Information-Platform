"""V0.9 semantic refactor backfill (idempotent).

Performs, against the configured database:

1. Backfill competition_sources.authority_level from source_type.
2. Recompute Competition/CompetitionEdition verification using authority rules
   (university sources can never yield verified_official on their own).
3. Demote competitions whose only evidence is a university policy catalog to
   pending_verification (entity kept, nothing deleted).
4. Rebuild the canonical school_competitions relation layer from legacy
   recognitions + notice relations.
5. Clear the legacy generic registration_deadline where it duplicated a campus
   deadline (campus value stays in university/college fields).
6. Detect duplicate leads and recompute lead review states.

Writes data/reports/v09_semantic_refactor_report.json.
"""

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models import Competition, CompetitionEdition, CompetitionLead, CompetitionSource
from app.services.competition_intelligence_service import CompetitionIntelligenceService
from app.services.competition_normalization_service import CompetitionNormalizationService
from app.services.fact_intelligence_service import FactIntelligenceService
from app.services.school_competition_service import SchoolCompetitionService
from app.services.source_authority_service import (
    authority_level_for,
    is_national_authority_source,
)


def _status_counts(db: Session, model: object, column_name: str) -> dict[str, int]:
    rows = db.execute(
        text(
            f"SELECT {column_name}, COUNT(*) FROM {model.__tablename__} "
            f"GROUP BY {column_name} ORDER BY {column_name}"
        )
    ).all()
    return dict(rows)


def _demote_policy_only_competitions(db: Session) -> list[int]:
    rows = db.execute(
        text(
            "SELECT c.id FROM competitions c "
            "WHERE EXISTS (SELECT 1 FROM competition_sources s "
            "WHERE s.competition_id = c.id AND s.source_type = 'university_policy') "
            "AND NOT EXISTS (SELECT 1 FROM competition_sources s2 "
            "WHERE s2.competition_id = c.id AND s2.source_type <> 'university_policy')"
        )
    ).scalars().all()
    ids = list(rows)
    if ids:
        competitions = db.execute(
            select(Competition).where(Competition.id.in_(ids))
        ).scalars()
        for competition in competitions:
            competition.verification_status = "pending_verification"
            competition.is_official_verified = False
    return ids


def _clear_campus_copied_generic_deadlines(db: Session) -> list[dict[str, object]]:
    rows = db.execute(
        text(
            "SELECT id, competition_id, year, registration_deadline, "
            "official_registration_deadline, university_registration_deadline "
            "FROM competition_editions "
            "WHERE registration_deadline IS NOT NULL "
            "AND university_registration_deadline IS NOT NULL "
            "AND registration_deadline = university_registration_deadline"
        )
    ).mappings().all()
    ids = [row["id"] for row in rows]
    if ids:
        db.execute(
            text(
                "UPDATE competition_editions SET registration_deadline = NULL "
                f"WHERE id IN ({','.join(str(i) for i in ids)})"
            )
        )
    return [dict(row) for row in rows]


def _detect_duplicate_leads(db: Session) -> list[int]:
    normalizer = CompetitionNormalizationService()
    leads = list(db.execute(select(CompetitionLead).order_by(CompetitionLead.id)).scalars())
    seen: dict[str, int] = {}
    duplicate_ids: list[int] = []
    for lead in leads:
        title_key = normalizer._normalize_text(lead.raw_title or "")
        name_key = normalizer._normalize_text(lead.detected_competition_name or "")
        key = f"{title_key}|{name_key}"
        if not title_key and not name_key:
            continue
        if key in seen:
            lead.duplicate_of_id = seen[key]
            lead.review_status = "duplicate"
            duplicate_ids.append(lead.id)
        else:
            seen[key] = lead.id
    return duplicate_ids


def _recompute_lead_states(db: Session) -> dict[str, int]:
    leads = list(db.execute(select(CompetitionLead)).scalars())
    comp_status = {
        competition.id: competition.verification_status
        for competition in db.execute(
            select(Competition).where(Competition.is_demo.is_(False))
        ).scalars()
    }
    counts: Counter[str] = Counter()
    for lead in leads:
        if lead.review_status == "duplicate":
            counts["duplicate"] += 1
            continue
        status = comp_status.get(lead.matched_competition_id)
        if lead.matched_competition_id is not None:
            lead.review_status = (
                "verified"
                if status in {"verified_official", "authority_confirmed"}
                and not lead.needs_review
                else "matched"
            )
            lead.verification_status = (
                "verified_official"
                if is_national_authority_source(lead.source_type)
                and status in {"verified_official", "authority_confirmed"}
                else "secondary_source_only"
            )
        else:
            lead.review_status = "pending"
        counts[lead.review_status] += 1
    return dict(sorted(counts.items()))


def main() -> None:
    with SessionLocal() as db:
        before_comp = _status_counts(db, Competition, "verification_status")
        before_edition = _status_counts(db, CompetitionEdition, "verification_status")
        before_lead = _status_counts(db, CompetitionLead, "review_status")

        fact_service = FactIntelligenceService()
        tiers = fact_service.refresh_source_tiers(db)
        verification = fact_service.refresh_verification(db)
        demoted_ids = _demote_policy_only_competitions(db)
        db.flush()

        school_stats = SchoolCompetitionService().rebuild(db)
        deadline_fixes = _clear_campus_copied_generic_deadlines(db)
        duplicate_ids = _detect_duplicate_leads(db)
        lead_states = _recompute_lead_states(db)
        intelligence = CompetitionIntelligenceService().refresh_all(db)
        db.commit()

        after_comp = _status_counts(db, Competition, "verification_status")
        after_edition = _status_counts(db, CompetitionEdition, "verification_status")
        after_lead = _status_counts(db, CompetitionLead, "review_status")
        authority_distribution = dict(
            db.execute(
                text(
                    "SELECT authority_level, COUNT(*) FROM competition_sources "
                    "GROUP BY authority_level ORDER BY authority_level"
                )
            ).all()
        )
        s_a_competitions = db.scalar(
            text(
                "SELECT COUNT(DISTINCT s.competition_id) FROM competition_sources s "
                "WHERE s.authority_level IN ('S','A') AND s.is_verified = 1 "
                "AND s.is_demo = 0"
            )
        )
        school_rows = db.scalar(text("SELECT COUNT(*) FROM school_competitions"))

        downgraded_comp = {
            status: count
            for status, count in after_comp.items()
            if count < before_comp.get(status, 0)
        }
        report = {
            "version": "v0.9",
            "stage": "semantic refactor",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_tiers": tiers,
            "authority_distribution": authority_distribution,
            "competition_verification_before": before_comp,
            "competition_verification_after": after_comp,
            "edition_verification_before": before_edition,
            "edition_verification_after": after_edition,
            "lead_review_before": before_lead,
            "lead_review_after": after_lead,
            "school_competitions": {
                **school_stats,
                "total_rows": school_rows,
            },
            "policy_only_demoted_ids": demoted_ids,
            "policy_only_demoted_count": len(demoted_ids),
            "generic_deadline_fixes": deadline_fixes,
            "duplicate_lead_ids": duplicate_ids,
            "duplicate_lead_count": len(duplicate_ids),
            "verified_official_downgrade_hint": downgraded_comp,
            "competitions_with_sa_sources": s_a_competitions,
            "verification_recompute": verification,
            "statistics_recompute": intelligence,
            "check_school_can_promote_directly": False,
        }
        report_path = PROJECT_ROOT / "data" / "reports" / "v09_semantic_refactor_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
