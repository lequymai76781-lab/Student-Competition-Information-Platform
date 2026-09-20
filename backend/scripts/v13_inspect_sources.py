"""Read-only inspection of source raw content for v13 field-evidence planning."""

from __future__ import annotations

import sys

BACKEND_DIR = __import__("pathlib").Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import func, select, text

from app.database.session import SessionLocal
from app.models import CompetitionSource


def main() -> None:
    with SessionLocal() as db:
        print("=== source_type stats ===")
        rows = db.execute(
            text(
                "SELECT source_type, COUNT(*), SUM(raw_content IS NOT NULL), "
                "SUM(LENGTH(raw_content) > 120) "
                "FROM competition_sources GROUP BY source_type ORDER BY 2 DESC"
            )
        ).fetchall()
        for row in rows:
            print(row)
        for keyword in ("主办", "参赛对象", "报名截止", "竞赛时间", "由.*主办"):
            sql = (
                "SELECT COUNT(*) FROM competition_sources "
                "WHERE raw_content LIKE :kw OR raw_title LIKE :kw"
            )
            print("keyword", keyword, db.execute(text(sql), {"kw": f"%{keyword}%"}).scalar())
        print("=== samples: university notices with 主办/参赛对象 in raw_content ===")
        samples = db.execute(
            text(
                "SELECT s.competition_id, c.name, s.id, s.source_url, "
                "SUBSTR(s.raw_content, 1, 220) "
                "FROM competition_sources s JOIN competitions c ON c.id=s.competition_id "
                "WHERE s.raw_content LIKE :kw AND s.authority_level IN ('B','C') "
                "LIMIT 30"
            ),
            {"kw": "%主办%"},
        ).fetchall()
        for row in samples:
            print("\n---", row[0], row[1], "source", row[2])
            print(row[3])
            print(row[4])


if __name__ == "__main__":
    main()
