"""V0.9 final-state snapshot used to answer refactor acceptance questions."""

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text

from app.database.session import SessionLocal


def main() -> None:
    with SessionLocal() as db:
        def q(sql: str):
            return db.execute(text(sql)).scalar()

        report = {
            "users": q("SELECT COUNT(*) FROM users"),
            "competitions": q("SELECT COUNT(*) FROM competitions"),
            "editions": q("SELECT COUNT(*) FROM competition_editions"),
            "notice_relations": q("SELECT COUNT(*) FROM university_competition_edition_relations"),
            "policy_recognitions": q("SELECT COUNT(*) FROM competition_policy_recognitions"),
            "leads": q("SELECT COUNT(*) FROM competition_leads"),
            "sources": q("SELECT COUNT(*) FROM competition_sources"),
            "school_competition_rows": q("SELECT COUNT(*) FROM school_competitions"),
            "competitions_without_sa_verified_source": q(
                "SELECT COUNT(*) FROM competitions c WHERE NOT EXISTS "
                "(SELECT 1 FROM competition_sources s WHERE s.competition_id = c.id "
                "AND s.authority_level IN ('S','A') AND s.is_verified = 1 AND s.is_demo = 0)"
            ),
            "competitions_only_university_policy_source": q(
                "SELECT COUNT(*) FROM competitions c WHERE EXISTS "
                "(SELECT 1 FROM competition_sources s WHERE s.competition_id = c.id "
                "AND s.source_type = 'university_policy') AND NOT EXISTS "
                "(SELECT 1 FROM competition_sources s2 WHERE s2.competition_id = c.id "
                "AND s2.source_type <> 'university_policy')"
            ),
            "competitions_school_confirmed": q(
                "SELECT COUNT(*) FROM competitions WHERE verification_status = 'school_confirmed'"
            ),
            "competitions_pending_verification": q(
                "SELECT COUNT(*) FROM competitions WHERE verification_status = 'pending_verification'"
            ),
            "competitions_verified_official": q(
                "SELECT COUNT(*) FROM competitions WHERE verification_status = 'verified_official'"
            ),
            "school_level_rows": q(
                "SELECT COUNT(*) FROM school_competitions WHERE school_level IS NOT NULL"
            ),
            "school_notice_rows": q(
                "SELECT COUNT(*) FROM school_competitions WHERE notice_url IS NOT NULL"
            ),
            "schools_with_notice_relations": q(
                "SELECT COUNT(DISTINCT university_id) FROM university_competition_edition_relations"
            ),
        }
        path = PROJECT_ROOT / "data" / "reports" / "v09_final_state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
