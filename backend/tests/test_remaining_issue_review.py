"""R06: homepage counters count the same competitions as the status filter."""
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Competition, CompetitionEdition


def set_open_edition(db, status):
    now = datetime.now(timezone.utc)
    edition = db.get(CompetitionEdition, 1)
    edition.year = now.year
    edition.registration_deadline = now + timedelta(days=7 if status == "registration_open" else -1)
    edition.official_registration_deadline = edition.registration_deadline
    edition.official_submission_deadline = now + timedelta(days=7) if status == "submission_open" else None
    edition.current_status = status
    return now, edition


def assert_count_matches_filter(client, status, expected):
    response = client.get("/api/competitions", params={"edition_status": status, "limit": 100})
    assert response.status_code == 200
    rows = response.json()["data"]
    assert len({row["id"] for row in rows}) == expected
    response = client.get("/api/stats")
    assert response.status_code == 200
    assert response.json()["data"][status] == expected
    return rows


@pytest.mark.parametrize("status", ["registration_open", "submission_open"])
def test_r06_open_edition_is_counted_even_when_another_edition_starts_sooner(client, db_session, status):
    now, edition = set_open_edition(db_session, status)
    db_session.add(CompetitionEdition(
        competition_id=edition.competition_id, year=now.year + 1,
        is_verified=True, registration_start=now + timedelta(days=1),
        official_registration_deadline=now + timedelta(days=20),
        current_status="registration_upcoming",
    ))
    db_session.commit()
    unfiltered = client.get("/api/competitions").json()["data"]
    assert unfiltered[0]["current_status"] == "registration_upcoming"
    rows = assert_count_matches_filter(client, status, 1)
    assert rows[0]["current_edition_id"] == edition.id


@pytest.mark.parametrize("status", ["registration_open", "submission_open"])
def test_r06_multiple_matching_editions_count_one_competition(client, db_session, status):
    now, edition = set_open_edition(db_session, status)
    db_session.add(CompetitionEdition(
        competition_id=edition.competition_id, year=now.year + 1, is_verified=True,
        official_registration_deadline=edition.official_registration_deadline,
        official_submission_deadline=edition.official_submission_deadline, current_status=status,
    ))
    db_session.commit()
    assert_count_matches_filter(client, status, 1)


@pytest.mark.parametrize("excluded", ["pending_edition", "pending_competition", "demo", "expired"])
def test_r06_ineligible_or_closed_rows_are_not_counted(client, db_session, excluded):
    now, edition = set_open_edition(db_session, "registration_open")
    competition = db_session.get(Competition, edition.competition_id)
    if excluded == "pending_edition":
        edition.verification_status = "pending"
    elif excluded == "pending_competition":
        competition.verification_status = "pending"
    elif excluded == "demo":
        competition.is_demo = True
    else:
        edition.registration_deadline = now - timedelta(days=1)
        edition.official_registration_deadline = edition.registration_deadline
    db_session.commit()
    assert_count_matches_filter(client, "registration_open", 0)


def test_r06_counts_are_not_capped_at_default_page_size(client, db_session):
    now, _ = set_open_edition(db_session, "registration_open")
    for index in range(51):
        competition = Competition(name=f"R06 pagination {index}", is_demo=False,
                                  is_competition=True, verification_status="verified_official")
        competition.editions.append(CompetitionEdition(
            year=now.year, is_verified=True, official_registration_deadline=now + timedelta(days=5),
        ))
        db_session.add(competition)
    db_session.commit()
    assert_count_matches_filter(client, "registration_open", 52)
