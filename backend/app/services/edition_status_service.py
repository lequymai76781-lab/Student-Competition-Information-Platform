"""Read-time lifecycle calculation. Never updates the stored source facts."""
from datetime import datetime, timezone

from app.models import CompetitionEdition
from app.services.user_facing_data_policy import UserFacingDataPolicy

ACTIONABLE_STATUSES = {"registration_open", "registration_upcoming", "submission_open"}
TERMINAL_STATUSES = {"finished", "ended", "archived", "result_announced", "cancelled", "canceled", "suspended", "postponed"}
_UNSET = object()


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def edition_status(
    edition: CompetitionEdition | None,
    *,
    now: datetime | None = None,
    registration_start: datetime | None | object = _UNSET,
    registration_deadline: datetime | None = None,
    submission_deadline: datetime | None = None,
) -> str:
    if edition is None:
        return "unknown"
    if not UserFacingDataPolicy.verified_record(edition):
        return "unknown"
    if edition.current_status in TERMINAL_STATUSES:
        return edition.current_status
    at = aware(now or datetime.now(timezone.utc))
    start = edition.registration_start if registration_start is _UNSET else registration_start
    deadline = registration_deadline or edition.official_registration_deadline or edition.registration_deadline
    submission = submission_deadline or edition.official_submission_deadline or edition.submission_deadline
    if edition.competition_end and aware(edition.competition_end) < at:
        return "finished"
    if edition.competition_end and any(
        value is not None and aware(value) > aware(edition.competition_end)
        for value in (start, deadline, submission, edition.competition_start)
    ):
        return "unknown"
    # A contradictory start/deadline cannot advertise an actionable window.
    if start and deadline and aware(start) > aware(deadline):
        return "unknown"
    if start and at < aware(start):
        return "registration_upcoming"
    if deadline and at <= aware(deadline):
        return "registration_open"
    if submission and at <= aware(submission):
        return "submission_open"
    if edition.competition_start and at >= aware(edition.competition_start):
        return "ongoing" if edition.competition_end else "unknown"
    if deadline or submission:
        return "registration_closed"
    return "unknown"
