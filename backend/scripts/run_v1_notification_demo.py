"""V1.0 notification demo: 10 beta users follow competitions -> reminders/updates."""

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select

from app.database.session import SessionLocal
from datetime import datetime, timezone

from app.models import (
    BetaFeedback,
    CompetitionUpdateEvent,
    Favorite,
    User,
    UserCompetitionStatus,
    UserCorrectionSubmission,
)
from app.services.notification_service import NotificationService
from app.services.personal_competition_service import PersonalCompetitionService


def main() -> None:
    service = NotificationService()
    personal = PersonalCompetitionService()
    report = []
    with SessionLocal() as db:
        users = list(db.execute(select(User).where(User.email.like("case%@test.local"))).scalars())
        for user in users:
            overview = personal.overview(db, user)
            pool = overview["now_available"] or overview["direction_related"] or overview["upcoming_deadline"]
            picked = pool[:3]
            for item in picked:
                if db.execute(
                    select(Favorite).where(
                        Favorite.user_id == user.id,
                        Favorite.competition_id == item["competition_id"],
                    )
                ).scalar_one_or_none() is None:
                    db.add(Favorite(user_id=user.id, competition_id=item["competition_id"]))
            if picked:
                first = picked[0]
                if db.execute(
                    select(UserCompetitionStatus).where(
                        UserCompetitionStatus.user_id == user.id,
                        UserCompetitionStatus.competition_id == first["competition_id"],
                    )
                ).scalar_one_or_none() is None:
                    db.add(
                        UserCompetitionStatus(
                            user_id=user.id,
                            competition_id=first["competition_id"],
                            status="planning",
                        )
                    )
            db.commit()
            created = service.ensure_reminders_for_user(db, user)
            notifications = service.list_for_user(db, user, limit=100)
            report.append(
                {
                    "email": user.email,
                    "followed": [item["competition_id"] for item in picked],
                    "reminders_created_now": created,
                    "total_notifications": len(notifications["items"]),
                }
            )
            print(
                user.email,
                "followed",
                len(picked),
                "reminders created",
                created,
                "total notifications",
                len(notifications["items"]),
            )
        service.ensure_event_notifications(db)
        # demo update event on the first user's followed competition
        target_competition_id = report[0]["followed"][0] if report[0]["followed"] else 143
        existing_event = db.execute(
            select(CompetitionUpdateEvent).where(
                CompetitionUpdateEvent.competition_id == target_competition_id,
                CompetitionUpdateEvent.event_type == "deadline_changed",
            )
        ).scalar_one_or_none()
        if existing_event is None:
            now = datetime.now(timezone.utc)
            db.add(
                CompetitionUpdateEvent(
                    competition_id=target_competition_id,
                    event_type="deadline_changed",
                    field_name="official_registration_deadline",
                    old_value="2026-09-20",
                    new_value="2026-09-27",
                    source_url="https://example.com/official-notice",
                    source_name="演示来源",
                    changed_at=now,
                    observed_at=now,
                    notes="V1.0 演示事件：报名截止由9月20日延期至9月27日。",
                )
            )
            db.flush()
        service.ensure_event_notifications(db)
        # demo correction + feedback from first user
        first_user = users[0]
        target_competition_id = report[0]["followed"][0] if report[0]["followed"] else 143
        correction_exists = db.execute(
            select(UserCorrectionSubmission).where(
                UserCorrectionSubmission.user_id == first_user.id,
                UserCorrectionSubmission.competition_id == target_competition_id,
                UserCorrectionSubmission.status == "pending",
            )
        ).scalar_one_or_none()
        if correction_exists is None:
            db.add(
                UserCorrectionSubmission(
                    user_id=first_user.id,
                    competition_id=target_competition_id,
                    correction_type="报名截止错误",
                    description="演示：官方页面显示的截止日期与页面公告不一致，请复核。",
                    source_url="https://example.com/notice",
                    status="pending",
                )
            )
        feedback_exists = db.execute(
            select(BetaFeedback).where(
                BetaFeedback.user_id == first_user.id,
                BetaFeedback.content == "演示反馈：希望支持自定义提醒提前天数。",
                BetaFeedback.status == "pending",
            )
        ).scalar_one_or_none()
        if feedback_exists is None:
            db.add(
                BetaFeedback(
                    user_id=first_user.id,
                    category="使用建议",
                    content="演示反馈：希望支持自定义提醒提前天数。",
                    status="pending",
                )
            )
        db.commit()
    (ROOT / "data" / "reports" / "v1_notification_demo.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("wrote v1_notification_demo.json")


if __name__ == "__main__":
    main()
