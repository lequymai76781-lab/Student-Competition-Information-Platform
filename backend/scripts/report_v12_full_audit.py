"""V12 final full audit (read-mostly; writes reports only)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select, text

from app.database.session import SessionLocal
from app.models import Competition, CompetitionEdition
from app.services.authority_audit_service import run_authority_audit


def main() -> None:
    report_dir = PROJECT_ROOT / "data" / "reports"
    with SessionLocal() as db:
        audit = run_authority_audit(db)
        comp_statuses = dict(
            db.execute(
                text(
                    "SELECT verification_status, COUNT(*) FROM competitions "
                    "WHERE is_demo=0 GROUP BY verification_status"
                )
            ).fetchall()
        )
        edition_statuses = dict(
            db.execute(
                text(
                    "SELECT verification_status, COUNT(*) FROM competition_editions "
                    "GROUP BY verification_status"
                )
            ).fetchall()
        )
        total_editions = db.execute(text("SELECT COUNT(*) FROM competition_editions")).scalar()
        edition_years = db.execute(
            text("SELECT year, COUNT(*) FROM competition_editions GROUP BY year ORDER BY year")
        ).fetchall()
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
        core_completeness = {
            "core_total": len(core),
            "with_organizer": sum(
                1
                for c in core
                if c.organizer or c.co_organizers or c.guiding_organizations or c.undertakers
            ),
            "with_website": sum(1 for c in core if c.official_website),
            "with_target_students": sum(1 for c in core if c.target_students),
            "with_edition": sum(1 for c in core if c.editions),
        }
        comps_with_2024_2025_2026 = 0
        for c in core:
            years = {e.year for e in c.editions}
            if {2024, 2025, 2026} <= years:
                comps_with_2024_2025_2026 += 1
        core_completeness["with_2024_2025_2026"] = comps_with_2024_2025_2026
        report = {
            "round": "v12 full audit",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "competition_statuses": comp_statuses,
            "edition_statuses": edition_statuses,
            "edition_total": total_editions,
            "edition_year_distribution": dict(edition_years),
            "core_completeness": core_completeness,
            "audit": audit,
            "violation_keys": [
                key
                for key, value in audit.items()
                if isinstance(value, list) and value
            ],
        }
    out = report_dir / "v12_full_audit.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
