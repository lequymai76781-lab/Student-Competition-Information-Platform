"""V1.0 notification & competition update event service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    CompetitionEdition,
    CompetitionFactRevision,
    CompetitionUpdateEvent,
    Favorite,
    Notification,
    UniversityCompetitionEditionRelation,
    User,
    UserCompetitionStatus,
)
from app.services.deadline_resolution_service import DeadlineResolutionService
from app.services.competition_freshness_service import CompetitionFreshnessService
from app.services.user_facing_data_policy import UserFacingDataPolicy

FOLLOW_STATUSES = {"planning", "registered", "participating"}
REMINDER_STAGES = (14, 7, 3, 1, 0)

DEADLINE_FIELDS = {
    "official_registration_deadline",
    "registration_deadline",
    "university_registration_deadline",
    "official_submission_deadline",
    "submission_deadline",
    "official_competition_date",
    "competition_start",
    "competition_end",
}

EVENT_TYPE_BY_FIELD = {
    "official_registration_deadline": "deadline_changed",
    "registration_deadline": "deadline_changed",
    "university_registration_deadline": "deadline_changed",
    "official_submission_deadline": "submission_changed",
    "submission_deadline": "submission_changed",
    "official_competition_date": "competition_date_changed",
    "competition_start": "competition_date_changed",
    "competition_end": "competition_date_changed",
}

TYPE_LABELS = {
    "college_registration_deadline": "学院截止",
    "university_registration_deadline": "校内截止",
    "official_registration_deadline": "官方截止",
    "college_submission_deadline": "学院作品截止",
    "university_submission_deadline": "校内作品截止",
    "official_submission_deadline": "官方作品截止",
}


class NotificationService:
    def __init__(self) -> None:
        self.deadline_service = DeadlineResolutionService()
        self.policy = UserFacingDataPolicy

    # ------------------------------------------------------------------ #
    # Followers
    # ------------------------------------------------------------------ #
    def follow_competition_ids(self, db: Session, user: User) -> set[int]:
        ids: set[int] = set()
        for row in db.execute(
            select(Favorite).where(Favorite.user_id == user.id)
        ).scalars():
            ids.add(row.competition_id)
        for row in db.execute(
            select(UserCompetitionStatus).where(
                UserCompetitionStatus.user_id == user.id,
                UserCompetitionStatus.status.in_(FOLLOW_STATUSES),
            )
        ).scalars():
            ids.add(row.competition_id)
        return ids

    def _followers_of_competition(self, db: Session, competition_id: int) -> list[User]:
        users = list(db.execute(select(User)).scalars())
        followers = []
        for user in users:
            if competition_id in self.follow_competition_ids(db, user):
                followers.append(user)
        return followers

    # ------------------------------------------------------------------ #
    # Reminders (same deadline + same stage only once)
    # ------------------------------------------------------------------ #
    def ensure_reminders_for_user(self, db: Session, user: User, *, now: datetime | None = None) -> int:
        now = now or datetime.now(timezone.utc)
        profile = user.profile
        university_id = profile.university_id if profile else None
        college_id = profile.college_id if profile else None
        created = 0
        editions = list(db.execute(select(CompetitionEdition)).scalars())
        editions_by_competition: dict[int, list[CompetitionEdition]] = {}
        for edition in editions:
            if edition.year >= 2025:
                editions_by_competition.setdefault(edition.competition_id, []).append(edition)
        for competition_id in sorted(self.follow_competition_ids(db, user)):
            rows = editions_by_competition.get(competition_id, [])
            if not rows:
                continue
            edition = max(rows, key=lambda item: item.year)
            deadline, label, resolution = self.deadline_service.resolve_action(
                edition,
                university_id=university_id,
                college_id=college_id,
            )
            if deadline is None or self._aware(deadline) < now:
                continue
            deadline_type = resolution.effective_deadline_type or "official_registration_deadline"
            days_left = max(0, int((self._aware(deadline) - now).total_seconds() // 86400))
            stage = next(
                (value for value in REMINDER_STAGES if days_left <= value),
                None,
            )
            if stage is None:
                continue
            dedup_key = f"dl-{edition.id}-{stage}-{deadline_type}"
            existing = db.execute(
                select(Notification).where(
                    Notification.user_id == user.id,
                    Notification.dedup_key == dedup_key,
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue
            label = TYPE_LABELS.get(deadline_type, "截止")
            day_text = "今天" if stage == 0 else f"{stage}天"
            db.add(
                Notification(
                    user_id=user.id,
                    type="deadline_reminder",
                    title=f"{label}提醒",
                    content=f"距离你的{label}还有{day_text}（{self._aware(deadline).strftime('%Y-%m-%d')}）。",
                    competition_id=competition_id,
                    competition_edition_id=edition.id,
                    dedup_key=dedup_key,
                    metadata_json={"stage": stage, "deadline": self._aware(deadline).isoformat()},
                )
            )
            # SessionLocal disables autoflush. Flush so a repeated call in the
            # same transaction observes the dedup key.
            db.flush()
            created += 1
        return created

    def ensure_reminders_all(self, db: Session, *, now: datetime | None = None) -> dict[str, int]:
        now = now or datetime.now(timezone.utc)
        total = 0
        users = list(db.execute(select(User)).scalars())
        for user in users:
            total += self.ensure_reminders_for_user(db, user, now=now)
        db.commit()
        return {"users": len(users), "notifications_created": total}

    def apply_deadline_update(
        self,
        db: Session,
        edition: CompetitionEdition,
        *,
        new_deadline: datetime,
        source_url: str,
        source_name: str | None = None,
        field_name: str = "official_registration_deadline",
    ) -> CompetitionUpdateEvent | None:
        """Apply a verified deadline change: revision (old kept) -> event -> notify."""
        freshness = CompetitionFreshnessService()
        old_value = getattr(edition, field_name)
        changed = freshness.update_edition_fact(
            db,
            edition,
            field_name=field_name,
            value=new_deadline,
            changed_at=datetime.now(timezone.utc),
            source_url=source_url,
            source_name=source_name,
        )
        if not changed:
            return None
        event_type = EVENT_TYPE_BY_FIELD.get(field_name, "deadline_changed")
        existing = db.execute(
            select(CompetitionUpdateEvent).where(
                CompetitionUpdateEvent.competition_id == edition.competition_id,
                CompetitionUpdateEvent.competition_edition_id == edition.id,
                CompetitionUpdateEvent.event_type == event_type,
                CompetitionUpdateEvent.source_url == source_url,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        event = CompetitionUpdateEvent(
            competition_id=edition.competition_id,
            competition_edition_id=edition.id,
            event_type=event_type,
            field_name=field_name,
            old_value=_serialize_dt(old_value),
            new_value=_serialize_dt(new_deadline),
            source_url=source_url,
            source_name=source_name,
            changed_at=datetime.now(timezone.utc),
            observed_at=datetime.now(timezone.utc),
            notes="管理员核验/官方来源更新截止时间",
        )
        db.add(event)
        db.flush()
        self._notify_event(db, event)
        # The caller owns the transaction, including queue state and audit records.
        db.flush()
        return event

    # ------------------------------------------------------------------ #
    # Update events from fact revisions
    # ------------------------------------------------------------------ #
    def sync_update_events(self, db: Session, *, since: datetime | None = None) -> dict[str, int]:
        query = select(CompetitionFactRevision)
        if since is not None:
            query = query.where(CompetitionFactRevision.changed_at >= since)
        revisions = list(db.execute(query.order_by(CompetitionFactRevision.changed_at.asc())).scalars())
        created_events = 0
        created_notifications = 0
        for revision in revisions:
            if revision.field_name not in DEADLINE_FIELDS:
                continue
            event_type = EVENT_TYPE_BY_FIELD.get(revision.field_name, "other")
            existing = db.execute(
                select(CompetitionUpdateEvent).where(
                    CompetitionUpdateEvent.competition_id == revision.competition_id,
                    CompetitionUpdateEvent.competition_edition_id == revision.competition_edition_id,
                    CompetitionUpdateEvent.event_type == event_type,
                    CompetitionUpdateEvent.changed_at == revision.changed_at,
                    CompetitionUpdateEvent.source_url == revision.source_url,
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue
            event = CompetitionUpdateEvent(
                competition_id=revision.competition_id,
                competition_edition_id=revision.competition_edition_id,
                event_type=event_type,
                field_name=revision.field_name,
                old_value=revision.old_value,
                new_value=revision.new_value,
                source_url=revision.source_url,
                source_name=revision.source_name,
                changed_at=revision.changed_at,
                observed_at=datetime.now(timezone.utc),
            )
            db.add(event)
            db.flush()
            created_events += 1
            created_notifications += self._notify_event(db, event)
        db.commit()
        return {"events_created": created_events, "notifications_created": created_notifications}

    def _notify_event(self, db: Session, event: CompetitionUpdateEvent) -> int:
        title_map = {
            "deadline_changed": "报名截止更新",
            "submission_changed": "作品提交截止更新",
            "competition_date_changed": "比赛时间更新",
            "registration_opened": "开始报名",
            "registration_closed": "报名结束",
            "edition_created": "新增届次",
            "notice_updated": "赛事通知更新",
            "track_added": "新增赛道",
            "other": "赛事信息更新",
        }
        old_text = _value_text(event.old_value)
        new_text = _value_text(event.new_value)
        if old_text and new_text and old_text != new_text:
            content = f"赛事{title_map.get(event.event_type, '信息')}已更新：{old_text} → {new_text}。来源：{event.source_url[:80]}"
        else:
            content = f"赛事{title_map.get(event.event_type, '信息')}已更新。来源：{event.source_url[:80]}"
        created = 0
        for user in self._followers_of_competition(db, event.competition_id):
            dedup_key = f"event-{event.id}"
            existing = db.execute(
                select(Notification).where(
                    Notification.user_id == user.id,
                    Notification.dedup_key == dedup_key,
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue
            db.add(
                Notification(
                    user_id=user.id,
                    type="competition_updated",
                    title=title_map.get(event.event_type, "赛事更新"),
                    content=content,
                    competition_id=event.competition_id,
                    competition_edition_id=event.competition_edition_id,
                    source_event_id=event.id,
                    dedup_key=dedup_key,
                )
            )
            created += 1
        return created

    def ensure_event_notifications(self, db: Session) -> dict[str, int]:
        """Backfill competition_updated notifications for all followers of each event."""
        events = list(db.execute(select(CompetitionUpdateEvent)).scalars())
        created = 0
        users = list(db.execute(select(User)).scalars())
        for event in events:
            for user in users:
                if event.competition_id not in self.follow_competition_ids(db, user):
                    continue
                dedup_key = f"event-{event.id}"
                existing = db.execute(
                    select(Notification).where(
                        Notification.user_id == user.id,
                        Notification.dedup_key == dedup_key,
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    continue
                created += self._notify_event_single(db, user, event, dedup_key)
        db.commit()
        return {"notifications_created": created}

    def _notify_event_single(
        self,
        db: Session,
        user: User,
        event: CompetitionUpdateEvent,
        dedup_key: str,
    ) -> int:
        title_map = {
            "deadline_changed": "报名截止更新",
            "submission_changed": "作品提交截止更新",
            "competition_date_changed": "比赛时间更新",
            "registration_opened": "开始报名",
            "registration_closed": "报名结束",
            "edition_created": "新增届次",
            "notice_updated": "赛事通知更新",
            "track_added": "新增赛道",
            "other": "赛事信息更新",
        }
        old_text = _value_text(event.old_value)
        new_text = _value_text(event.new_value)
        if old_text and new_text and old_text != new_text:
            content = (
                f"赛事{title_map.get(event.event_type, '信息')}已更新：{old_text} → {new_text}。"
                f"来源：{event.source_url[:80]}"
            )
        else:
            content = f"赛事{title_map.get(event.event_type, '信息')}已更新。来源：{event.source_url[:80]}"
        db.add(
            Notification(
                user_id=user.id,
                type="competition_updated",
                title=title_map.get(event.event_type, "赛事更新"),
                content=content,
                competition_id=event.competition_id,
                competition_edition_id=event.competition_edition_id,
                source_event_id=event.id,
                dedup_key=dedup_key,
            )
        )
        return 1

    # ------------------------------------------------------------------ #
    # School / college notice added
    # ------------------------------------------------------------------ #
    def sync_new_relations(self, db: Session, *, since: datetime | None = None) -> dict[str, int]:
        query = select(UniversityCompetitionEditionRelation)
        if since is not None:
            query = query.where(UniversityCompetitionEditionRelation.created_at >= since)
        relations = list(db.execute(query.order_by(UniversityCompetitionEditionRelation.created_at.asc())).scalars())
        created = 0
        for relation in relations:
            if not self.policy.relation_allowed(relation):
                continue
            edition = db.get(CompetitionEdition, relation.competition_edition_id)
            if edition is None:
                continue
            notice_type = (
                "college_notice_added" if relation.college_id is not None else "school_notice_added"
            )
            users = list(db.execute(select(User)).scalars())
            for user in users:
                profile = user.profile
                if profile is None or profile.university_id != relation.university_id:
                    continue
                if edition.competition_id not in self.follow_competition_ids(db, user):
                    continue
                dedup_key = f"relation-{relation.id}"
                existing = db.execute(
                    select(Notification).where(
                        Notification.user_id == user.id,
                        Notification.dedup_key == dedup_key,
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    continue
                db.add(
                    Notification(
                        user_id=user.id,
                        type=notice_type,
                        title="学校发布了新的赛事通知" if notice_type == "school_notice_added" else "学院发布了新的赛事通知",
                        content=(relation.notice_title or "")[:120],
                        competition_id=relation.competition_id,
                        competition_edition_id=edition.id,
                        source_event_id=relation.id,
                        dedup_key=dedup_key,
                    )
                )
                created += 1
        db.commit()
        return {"notifications_created": created}

    # ------------------------------------------------------------------ #
    # Read API helpers
    # ------------------------------------------------------------------ #
    def list_for_user(
        self,
        db: Session,
        user: User,
        *,
        category: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        query = select(Notification).where(Notification.user_id == user.id)
        if category == "deadline":
            query = query.where(Notification.type == "deadline_reminder")
        elif category == "updates":
            query = query.where(
                Notification.type.in_(
                    {"competition_updated", "deadline_changed", "registration_opened", "new_edition"}
                )
            )
        elif category == "school":
            query = query.where(
                Notification.type.in_({"school_notice_added", "college_notice_added"})
            )
        rows = list(
            db.execute(
                query.order_by(Notification.created_at.desc()).limit(limit).offset(offset)
            ).scalars()
        )
        return {
            "items": [self._serialize(db, row) for row in rows],
            "unread": self.unread_count(db, user),
        }

    def unread_count(self, db: Session, user: User) -> int:
        return db.execute(
            select(func.count()).select_from(Notification).where(
                Notification.user_id == user.id,
                Notification.is_read.is_(False),
            )
        ).scalar_one()

    def mark_read(self, db: Session, user: User, notification_id: int) -> bool:
        row = db.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.user_id == user.id,
            )
        ).scalar_one_or_none()
        if row is None:
            return False
        row.is_read = True
        row.read_at = datetime.now(timezone.utc)
        db.commit()
        return True

    def _serialize(self, db: Session, row: Notification) -> dict[str, Any]:
        return {
            "id": row.id,
            "type": row.type,
            "title": row.title,
            "content": row.content,
            "competition_id": row.competition_id,
            "competition_edition_id": row.competition_edition_id,
            "is_read": row.is_read,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "read_at": row.read_at.isoformat() if row.read_at else None,
        }

    def _aware(self, value: datetime | None) -> datetime:
        if value is None:
            return datetime.now(timezone.utc)
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _value_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return self_format(value)
    if isinstance(value, dict):
        return str(value.get("value") or value)
    return str(value)


def self_format(value: datetime) -> str:
    value = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return value.strftime("%Y-%m-%d")


def _serialize_dt(value: Any) -> Any:
    if isinstance(value, datetime):
        value = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return value
