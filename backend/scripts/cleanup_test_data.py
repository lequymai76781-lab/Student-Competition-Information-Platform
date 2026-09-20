"""V1.0.1 production hygiene: remove all demo/test records.

Deletes test users (case*, v1test-*, temp-*), demo corrections/feedback,
demo notifications, and demo update events. Safe to run on any environment.
"""

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import delete, func, or_, select

from app.database.session import SessionLocal
from app.models import (
    BetaFeedback,
    CompetitionUpdateEvent,
    Notification,
    User,
    UserCorrectionSubmission,
)


def main() -> None:
    with SessionLocal() as db:
        users = list(
            db.execute(
                select(User).where(
                    or_(
                        User.email.like("case%@test.local"),
                        User.email.like("v1test-%"),
                        User.email.like("temp-%@test.local"),
                        User.email == "admin@test.local",
                    )
                )
            ).scalars()
        )
        user_ids = [user.id for user in users]
        for user in users:
            db.delete(user)
        db.flush()

        corrections = list(
            db.execute(
                select(UserCorrectionSubmission).where(
                    UserCorrectionSubmission.description.like("%演示%")
                    | (UserCorrectionSubmission.source_url == "https://example.com/notice")
                )
            ).scalars()
        )
        for row in corrections:
            db.delete(row)
        feedback = list(
            db.execute(
                select(BetaFeedback).where(BetaFeedback.content.like("%演示%"))
            ).scalars()
        )
        for row in feedback:
            db.delete(row)

        events = list(
            db.execute(
                select(CompetitionUpdateEvent).where(
                    (CompetitionUpdateEvent.source_url == "https://example.com/official-notice")
                    | (CompetitionUpdateEvent.source_url == "https://example.com/notice")
                    | (CompetitionUpdateEvent.notes.like("%演示%"))
                )
            ).scalars()
        )
        event_ids = [event.id for event in events]
        if event_ids:
            db.execute(
                delete(Notification).where(Notification.source_event_id.in_(event_ids))
            )
        for event in events:
            db.delete(event)
        db.commit()

        remaining_users = db.scalar(select(func.count()).select_from(User))
        remaining_notifications = db.scalar(select(func.count()).select_from(Notification))
        remaining_events = db.scalar(select(func.count()).select_from(CompetitionUpdateEvent))
        remaining_corrections = db.scalar(select(func.count()).select_from(UserCorrectionSubmission))
        remaining_feedback = db.scalar(select(func.count()).select_from(BetaFeedback))
        report = {
            "deleted_test_users": len(users),
            "deleted_demo_corrections": len(corrections),
            "deleted_demo_feedback": len(feedback),
            "deleted_demo_events": len(events),
            "remaining_users": remaining_users,
            "remaining_notifications": remaining_notifications,
            "remaining_update_events": remaining_events,
            "remaining_corrections": remaining_corrections,
            "remaining_feedback": remaining_feedback,
        }
    (ROOT / "data" / "reports" / "v101_cleanup_result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
