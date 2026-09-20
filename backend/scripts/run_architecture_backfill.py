"""V0.9 data-architecture backfill (idempotent, additive).

- populates organizations + competition_organizations from free-text fields
- backfills competition_leads.review_status
- reports (does NOT auto-rewrite) deadline semantic anomalies and
  directory-discovered entities that should be demoted to the discovery pool
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

from sqlalchemy import text

from app.database.session import SessionLocal
from app.services.organization_service import OrganizationService


def main() -> None:
    service = OrganizationService()
    with SessionLocal() as db:
        organization_stats = service.sync_competition_organizations(db)
        review_stats = service.backfill_lead_review_status(db)
        db.commit()

        anomalies = {
            "deadline_order_violations": rows(
                db,
                """
                SELECT e.id, c.name, e.year, e.official_registration_deadline,
                       e.university_registration_deadline
                FROM competition_editions e
                JOIN competitions c ON c.id = e.competition_id
                WHERE e.official_registration_deadline IS NOT NULL
                  AND e.university_registration_deadline IS NOT NULL
                  AND e.university_registration_deadline > e.official_registration_deadline
                """,
            ),
            "generic_deadline_matches_university": rows(
                db,
                """
                SELECT e.id, c.name, e.year, e.registration_deadline,
                       e.official_registration_deadline, e.university_registration_deadline
                FROM competition_editions e
                JOIN competitions c ON c.id = e.competition_id
                WHERE e.registration_deadline IS NOT NULL
                  AND e.university_registration_deadline IS NOT NULL
                  AND e.registration_deadline = e.university_registration_deadline
                  AND (e.official_registration_deadline IS NULL
                       OR e.official_registration_deadline <> e.registration_deadline)
                """,
            ),
            "policy_only_competitions": rows(
                db,
                """
                SELECT c.id, c.name, c.entity_type
                FROM competitions c
                WHERE EXISTS (SELECT 1 FROM competition_sources s
                              WHERE s.competition_id = c.id
                                AND s.source_type = 'university_policy')
                  AND NOT EXISTS (SELECT 1 FROM competition_sources s2
                                  WHERE s2.competition_id = c.id
                                    AND s2.source_type <> 'university_policy')
                ORDER BY c.id
                """,
            ),
        }
        lead_counts = dict(
            db.execute(
                text(
                    "SELECT review_status, COUNT(*) FROM competition_leads "
                    "GROUP BY review_status ORDER BY review_status"
                )
            ).all()
        )
        org_type_counts = dict(
            db.execute(
                text("SELECT org_type, COUNT(*) FROM organizations GROUP BY org_type ORDER BY org_type")
            ).all()
        )
        report = {
            "version": "v0.9",
            "stage": "architecture foundation backfill",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "organization": organization_stats,
            "review_status": review_stats,
            "lead_status_counts": lead_counts,
            "organization_type_counts": org_type_counts,
            "anomalies": anomalies,
            "anomaly_counts": {key: len(value) for key, value in anomalies.items()},
        }
        report_path = PROJECT_ROOT / "data" / "reports" / "v09_architecture_backfill_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


def rows(db, sql: str) -> list[dict]:
    result = db.execute(text(sql))
    return [dict(zip(result.keys(), row)) for row in result.all()]


if __name__ == "__main__":
    main()
