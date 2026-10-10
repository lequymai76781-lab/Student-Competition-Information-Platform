from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import CompetitionEdition, CompetitionFactRevision


class CompetitionFreshnessService:
    """Calculates edition freshness and records verified fact changes."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def interval_for(self, current_status: str | None) -> timedelta:
        hours = {
            "registration_open": self.settings.freshness_registration_open_hours,
            "submission_open": self.settings.freshness_submission_open_hours,
            "registration_upcoming": self.settings.freshness_upcoming_hours,
            "upcoming": self.settings.freshness_upcoming_hours,
            "finished": self.settings.freshness_finished_hours,
            "ended": self.settings.freshness_finished_hours,
            "result_announced": self.settings.freshness_finished_hours,
            "archived": self.settings.freshness_finished_hours,
        }.get(current_status or "unknown", self.settings.freshness_unknown_hours)
        return timedelta(hours=max(1, hours))

    def refresh_all(self, db: Session, *, now: datetime | None = None) -> dict[str, int]:
        checked_at = self._aware(now or datetime.now(timezone.utc))
        counts = {status: 0 for status in ("fresh", "due_for_check", "stale", "archived", "unknown")}
        editions = list(db.execute(select(CompetitionEdition)).scalars())
        for edition in editions:
            status = self.refresh(edition, now=checked_at)
            counts[status] += 1
        return {"total": len(editions), **counts}

    def refresh(self, edition: CompetitionEdition, *, now: datetime | None = None) -> str:
        checked_at = self._aware(now or datetime.now(timezone.utc))
        interval = self.interval_for(edition.current_status)
        if edition.current_status == "archived" or (
            edition.current_status in {"finished", "ended", "result_announced"}
            and edition.year < checked_at.year
        ):
            edition.freshness_status = "archived"
            edition.next_check_at = edition.next_check_at or checked_at + interval
            return edition.freshness_status

        if edition.last_verified_at is None:
            edition.freshness_status = "unknown"
            edition.next_check_at = edition.next_check_at or checked_at
            return edition.freshness_status

        last_verified = self._aware(edition.last_verified_at)
        next_check = self._aware(edition.next_check_at) if edition.next_check_at else last_verified + interval
        edition.next_check_at = next_check
        if checked_at <= next_check:
            edition.freshness_status = "fresh"
        elif checked_at <= next_check + interval * self.settings.freshness_stale_multiplier:
            edition.freshness_status = "due_for_check"
        else:
            edition.freshness_status = "stale"
        return edition.freshness_status

    def mark_verified(
        self,
        edition: CompetitionEdition,
        *,
        observed_at: datetime,
        source_updated_at: datetime | None = None,
    ) -> None:
        observed = self._aware(observed_at)
        edition.last_verified_at = observed
        edition.last_seen_at = observed
        if source_updated_at is not None:
            published = self._aware(source_updated_at)
            if edition.source_updated_at is None or published > self._aware(edition.source_updated_at):
                edition.source_updated_at = published
        edition.next_check_at = observed + self.interval_for(edition.current_status)
        edition.freshness_status = "archived" if edition.current_status == "archived" else "fresh"

    def update_edition_fact(
        self,
        db: Session,
        edition: CompetitionEdition,
        *,
        field_name: str,
        value: Any,
        changed_at: datetime,
        source_url: str,
        source_name: str | None = None,
        verification_status: str = "verified_official",
    ) -> bool:
        if isinstance(value, datetime):
            value = self._aware(value)
        old_value = getattr(edition, field_name)
        if self._comparable(old_value) == self._comparable(value):
            return False
        is_initial_status = field_name == "current_status" and old_value == "unknown"
        if old_value is not None and not is_initial_status:
            db.add(
                CompetitionFactRevision(
                    competition_id=edition.competition_id,
                    competition_edition_id=edition.id,
                    field_name=field_name,
                    old_value=self._serializable(old_value),
                    new_value=self._serializable(value),
                    changed_at=self._aware(changed_at),
                    source_url=source_url,
                    source_name=source_name,
                    verification_status=verification_status,
                )
            )
        setattr(edition, field_name, value)
        return True

    def _comparable(self, value: Any) -> Any:
        return self._aware(value) if isinstance(value, datetime) else value

    def _serializable(self, value: Any) -> Any:
        return self._aware(value).isoformat() if isinstance(value, datetime) else value

    def _aware(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
