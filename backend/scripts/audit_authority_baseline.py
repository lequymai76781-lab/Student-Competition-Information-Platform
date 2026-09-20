"""V0.9 authority baseline audit (read-only data snapshot).

Answers the Section-1 questions about current authority coverage before any
new collector runs. Writes data/reports/v09_authority_baseline.json.
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

from sqlalchemy import func, select, text

from app.database.session import SessionLocal
from app.models import Competition, CompetitionEdition


def main() -> None:
    with SessionLocal() as db:
        total_competitions = db.scalar(select(func.count()).select_from(Competition))
        total_editions = db.scalar(select(func.count()).select_from(CompetitionEdition))

        def one(sql: str):
            return db.execute(text(sql)).scalar()

        verified_official = one(
            "SELECT COUNT(*) FROM competitions WHERE verification_status='verified_official'"
        )
        pending_verification = one(
            "SELECT COUNT(*) FROM competitions WHERE verification_status='pending_verification'"
        )
        school_confirmed = one(
            "SELECT COUNT(*) FROM competitions WHERE verification_status='school_confirmed'"
        )
        unverified = one("SELECT COUNT(*) FROM competitions WHERE verification_status='unverified'")
        with_s_source = one(
            "SELECT COUNT(DISTINCT competition_id) FROM competition_sources "
            "WHERE authority_level='S' AND is_verified=1 AND is_demo=0"
        )
        with_a_source = one(
            "SELECT COUNT(DISTINCT competition_id) FROM competition_sources "
            "WHERE authority_level='A' AND is_verified=1 AND is_demo=0"
        )
        only_university_college = one(
            "SELECT COUNT(*) FROM competitions c WHERE NOT EXISTS "
            "(SELECT 1 FROM competition_sources s WHERE s.competition_id=c.id "
            "AND s.authority_level IN ('S','A') AND s.is_verified=1 AND s.is_demo=0) "
            "AND EXISTS (SELECT 1 FROM competition_sources s2 WHERE s2.competition_id=c.id "
            "AND s2.authority_level IN ('B','C') AND s2.is_verified=1 AND s2.is_demo=0)"
        )
        no_source = one(
            "SELECT COUNT(*) FROM competitions c WHERE NOT EXISTS "
            "(SELECT 1 FROM competition_sources s WHERE s.competition_id=c.id AND s.is_demo=0)"
        )
        duplicate_source_rows = db.execute(
            text(
                "SELECT competition_id, source_url, COUNT(*) AS cnt "
                "FROM competition_sources GROUP BY competition_id, source_url "
                "HAVING cnt > 1 ORDER BY cnt DESC"
            )
        ).all()
        duplicate_url_total = db.execute(
            text(
                "SELECT source_url, COUNT(DISTINCT competition_id) AS comp_cnt, COUNT(*) AS cnt "
                "FROM competition_sources GROUP BY source_url HAVING cnt > 1 ORDER BY cnt DESC"
            )
        ).all()
        multi_official_url = db.execute(
            text(
                "SELECT competition_id, COUNT(DISTINCT source_url) AS urls "
                "FROM competition_sources "
                "WHERE authority_level IN ('S','A') AND is_verified=1 AND is_demo=0 "
                "GROUP BY competition_id HAVING urls > 1 ORDER BY urls DESC"
            )
        ).all()
        source_type_dist = dict(
            db.execute(
                text("SELECT source_type, COUNT(*) FROM competition_sources GROUP BY source_type")
            ).all()
        )
        authority_dist = dict(
            db.execute(
                text(
                    "SELECT authority_level, COUNT(*) FROM competition_sources "
                    "GROUP BY authority_level ORDER BY authority_level"
                )
            ).all()
        )
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "competitions_total": total_competitions,
            "editions_total": total_editions,
            "status_counts": {
                "verified_official": verified_official,
                "pending_verification": pending_verification,
                "school_confirmed": school_confirmed,
                "unverified": unverified,
            },
            "competitions_with_s_source": with_s_source,
            "competitions_with_a_source": with_a_source,
            "competitions_only_university_college_sources": only_university_college,
            "competitions_without_any_source": no_source,
            "duplicate_source_rows_per_competition": len(duplicate_source_rows),
            "duplicate_source_rows_detail": [
                {"competition_id": row[0], "url": row[1], "count": row[2]}
                for row in duplicate_source_rows
            ],
            "url_used_by_multiple_competitions": len(duplicate_url_total),
            "url_multi_competition_detail": [
                {"url": row[0], "competitions": row[1], "count": row[2]}
                for row in duplicate_url_total
            ],
            "competitions_with_multiple_sa_official_urls": len(multi_official_url),
            "multi_sa_url_detail": [
                {"competition_id": row[0], "distinct_urls": row[1]} for row in multi_official_url
            ],
            "source_type_distribution": source_type_dist,
            "authority_level_distribution": authority_dist,
        }
        path = PROJECT_ROOT / "data" / "reports" / "v09_authority_baseline.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
