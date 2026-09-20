"""Read-only check for 大小挑 entity separation + manual-review rows."""

from __future__ import annotations

import sys

BACKEND_DIR = __import__("pathlib").Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select, text

from app.database.session import SessionLocal
from app.models import Competition, CompetitionAlias


def main() -> None:
    with SessionLocal() as db:
        for competition_id in (2, 3):
            competition = db.get(Competition, competition_id)
            aliases = list(
                db.execute(
                    select(CompetitionAlias).where(CompetitionAlias.competition_id == competition_id)
                ).scalars()
            )
            print(
                competition_id,
                competition.name,
                "parent=",
                competition.parent_competition_id,
                "type=",
                competition.competition_type,
                "verification=",
                competition.verification_status,
            )
            print("former_names=", competition.former_names)
            print("aliases=", [alias.alias for alias in aliases])
        print(
            "review_queue pending=",
            db.execute(text("SELECT COUNT(*) FROM review_queue WHERE status='pending'")).scalar(),
        )
        print("candidate_fact conflicts=", db.execute(text("SELECT COUNT(*) FROM candidate_facts")).scalar())
        rows = db.execute(
            text(
                "SELECT id, name, verification_status FROM competitions "
                "WHERE name LIKE '%RoboTac%' OR name LIKE '%CURC%' OR name LIKE '%机器人大赛%' "
                "ORDER BY id"
            )
        ).fetchall()
        print("robotic-family rows=", rows)


if __name__ == "__main__":
    main()
