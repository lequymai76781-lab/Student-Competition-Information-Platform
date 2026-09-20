from types import SimpleNamespace

from app.services.school_competition_service import SchoolCompetitionService


def _row(notice_type: str) -> dict:
    return {"relation": SimpleNamespace(notice_type=notice_type)}


def test_notification_does_not_imply_participation() -> None:
    service = SchoolCompetitionService()
    assert service._participation_status([_row("registration_notice")]) == "notified"


def test_participation_evidence_is_explicit() -> None:
    service = SchoolCompetitionService()
    assert service._participation_status([_row("participation_news")]) == "participated"
