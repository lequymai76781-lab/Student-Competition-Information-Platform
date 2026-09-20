"""V1.0 product ops scheduler: reminders, update events, notice sync, freshness.

Run periodically (e.g. daily). Never deletes existing facts when a check fails;
only creates notifications/events and refreshes freshness statuses.
"""

import sys
import time
import logging
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database.session import SessionLocal
from app.services.competition_freshness_service import CompetitionFreshnessService
from app.services.notification_service import NotificationService
from app.core.logging_setup import configure_logging

logger = logging.getLogger("v1.scheduler")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop-minutes", type=int, default=0, help="重复运行间隔（分钟），0=运行一次")
    args = parser.parse_args()
    configure_logging(str(ROOT / "data" / "logs"))
    last_run_file = ROOT / "data" / ".v1_last_ops_run"
    try:
        last_run = datetime.fromisoformat(last_run_file.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        last_run = datetime.now(timezone.utc) - timedelta(days=30)
    if last_run.tzinfo is None:
        last_run = last_run.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)

    while True:
        results: dict = {}
        with SessionLocal() as db:
            service = NotificationService()
            for step, call in (
                ("update_events", lambda: service.sync_update_events(db, since=last_run)),
                ("relations", lambda: service.sync_new_relations(db, since=last_run)),
                ("reminders", lambda: service.ensure_reminders_all(db, now=now)),
                ("freshness", lambda: CompetitionFreshnessService().refresh_all(db)),
            ):
                try:
                    results[step] = call()
                    db.commit()
                except Exception:  # noqa: BLE001 - one step must not kill the whole task
                    logger.exception("scheduler step failed: %s", step)
                    db.rollback()
                    results[step] = {"error": True}
        last_run_file.write_text(now.isoformat(), encoding="utf-8")
        print("== V1.0 ops run ==", results)
        logger.info("ops run %s", results)
        if not args.loop_minutes:
            break
        time.sleep(args.loop_minutes * 60)


if __name__ == "__main__":
    main()
