from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CompetitionEdition, CompetitionFactRevision
from app.services.competition_freshness_service import CompetitionFreshnessService


def test_registration_open_freshness_degrades_by_cadence(db_session: Session) -> None:
    edition = db_session.execute(select(CompetitionEdition)).scalar_one()
    service = CompetitionFreshnessService()
    verified_at = datetime(2026, 9, 1, 8, tzinfo=timezone.utc)

    service.mark_verified(edition, observed_at=verified_at)
    assert edition.freshness_status == "fresh"
    assert service.refresh(edition, now=verified_at + timedelta(hours=25)) == "due_for_check"
    assert service.refresh(edition, now=verified_at + timedelta(hours=74)) == "stale"


def test_verified_deadline_change_creates_revision(db_session: Session) -> None:
    edition = db_session.execute(select(CompetitionEdition)).scalar_one()
    service = CompetitionFreshnessService()
    old_value = edition.official_registration_deadline
    new_value = datetime.now(timezone.utc) + timedelta(days=45)

    changed = service.update_edition_fact(
        db_session,
        edition,
        field_name="official_registration_deadline",
        value=new_value,
        changed_at=datetime.now(timezone.utc),
        source_url="https://official.example.com/update",
        source_name="赛事主办方",
    )
    db_session.flush()
    revision = db_session.execute(select(CompetitionFactRevision)).scalar_one()

    assert changed is True
    assert revision.old_value == old_value.replace(tzinfo=timezone.utc).isoformat()
    assert revision.new_value == new_value.isoformat()
    assert revision.field_name == "official_registration_deadline"
