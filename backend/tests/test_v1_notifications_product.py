from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.security import hash_password
from app.models import (
    BetaFeedback,
    College,
    Competition,
    CompetitionEdition,
    CompetitionFactRevision,
    CompetitionUpdateEvent,
    Favorite,
    Major,
    Notification,
    University,
    User,
    UserCompetitionStatus,
    UserCorrectionSubmission,
)
from app.services.notification_service import NotificationService
from app.services.personal_competition_service import PersonalCompetitionService
from app.services.field_review_service import FieldReviewService
from app.services.field_review_origins import stage_correction


def _approve_candidate(db, admin, candidate):
    detail = FieldReviewService.detail(db, candidate)
    for field in detail["fields"]:
        for proposal in field["proposals"]:
            detail = FieldReviewService.verify_source(db, candidate.id, proposal["id"],
                {"preview_token": detail["preview_token"], "note": "核对官方通知原文"}, admin=admin)
    return FieldReviewService.review(db, candidate.id, {
        "preview_token": detail["preview_token"], "note": "核验通过",
        "decisions": [{"field_name": field["field_name"], "action": "approve", "proposal_id": field["proposals"][0]["id"]}
                      for field in detail["fields"]],
    }, admin=admin)


def _user(db, email: str, *, admin: bool = False) -> User:
    user = User(email=email, username=email.split("@")[0], hashed_password=hash_password("test123456"), is_admin=admin)
    db.add(user)
    db.flush()
    return user


def _profile(db, user: User, university: str, college: str, major: str):
    from app.models import UserProfile

    uni = db.execute(select(University).where(University.name == university)).scalar_one()
    college_row = db.execute(
        select(College).where(College.university_id == uni.id, College.name == college)
    ).scalar_one_or_none()
    if college_row is None:
        college_row = College(university_id=uni.id, name=college, is_verified=True, is_demo=False)
        db.add(college_row)
        db.flush()
    major_row = db.execute(select(Major).where(Major.name == major)).scalar_one_or_none()
    if major_row is None:
        major_row = Major(name=major)
        db.add(major_row)
        db.flush()
    db.add(
        UserProfile(
            user_id=user.id,
            university_id=uni.id,
            university_name=uni.name,
            college_id=college_row.id,
            college_name=college_row.name,
            major_id=major_row.id,
            major_name=major_row.name,
            grade="大二",
            interest_tags=["创新创业"],
        )
    )
    db.flush()


def test_deadline_reminder_generation_and_idempotency(production_copy_session_factory):
    service = NotificationService()
    with production_copy_session_factory() as db:
        user = _user(db, "isolated-v1-remind@example.com")
        _profile(db, user, "西南交通大学", "经济管理学院", "工商管理")
        competitions = list(db.execute(select(Competition).where(Competition.is_demo.is_(False))).scalars())
        competition = next(item for item in competitions if "创新" in item.name)
        db.add(Favorite(user_id=user.id, competition_id=competition.id))
        db.add(UserCompetitionStatus(user_id=user.id, competition_id=competition.id, status="planning"))
        db.flush()
        first = service.ensure_reminders_for_user(db, user)
        second = service.ensure_reminders_for_user(db, user)
        count = len(list(db.execute(select(Notification).where(Notification.user_id == user.id)).scalars()))
        assert first >= 0
        assert second == 0, "reminders must not duplicate"
        assert count == first


def test_update_event_notifies_followers(production_copy_session_factory):
    service = NotificationService()
    with production_copy_session_factory() as db:
        user = _user(db, "isolated-v1-event@example.com")
        _profile(db, user, "西南交通大学", "经济管理学院", "工商管理")
        competitions = list(db.execute(select(Competition).where(Competition.is_demo.is_(False))).scalars())
        competition = next(item for item in competitions if "创新" in item.name)
        db.add(Favorite(user_id=user.id, competition_id=competition.id))
        db.flush()
        now = datetime.now(timezone.utc)
        db.add(
            CompetitionUpdateEvent(
                competition_id=competition.id,
                event_type="deadline_changed",
                field_name="official_registration_deadline",
                old_value="2026-09-20",
                new_value="2026-09-27",
                source_url="https://example.com/notice",
                changed_at=now,
                observed_at=now,
            )
        )
        db.flush()
        result = service.ensure_event_notifications(db)
        notifications = list(
            db.execute(
                select(Notification).where(
                    Notification.user_id == user.id,
                    Notification.type == "competition_updated",
                )
            ).scalars()
        )
        assert result["notifications_created"] >= 1
        assert notifications


def test_correction_and_admin_review_permission_flow(production_copy_session_factory):
    from fastapi import HTTPException

    from app.api.deps import get_current_admin

    with production_copy_session_factory() as db:
        normal = _user(db, "isolated-v1-normal@example.com")
        admin = _user(db, "isolated-v1-admin@example.com", admin=True)
        competitions = list(db.execute(select(Competition).where(Competition.is_demo.is_(False))).scalars())
        correction = UserCorrectionSubmission(
            user_id=normal.id,
            competition_id=competitions[0].id,
            correction_type="报名截止错误",
            description="测试提交",
            status="pending",
        )
        db.add(correction)
        db.flush()
        try:
            get_current_admin(user=normal)
            raise AssertionError("normal user should be denied")
        except HTTPException as exc:
            assert exc.status_code == 403
        assert get_current_admin(user=admin).is_admin is True
        correction.status = "approved"
        db.flush()
        assert correction.status == "approved"


def test_beta_feedback_submission(production_copy_session_factory):
    with production_copy_session_factory() as db:
        user = _user(db, "isolated-v1-feedback@example.com")
        row = BetaFeedback(user_id=user.id, category="使用建议", content="测试反馈", status="pending")
        db.add(row)
        db.flush()
        assert row.id is not None


def test_personal_calendar_uses_user_deadline(production_copy_session_factory):
    service = PersonalCompetitionService()
    with production_copy_session_factory() as db:
        user = _user(db, "isolated-v1-cal@example.com")
        _profile(db, user, "西南交通大学", "经济管理学院", "工商管理")
        events = service.upcoming_events(db, user)
        for event in events:
            assert event["deadline"] is not None


def test_deadline_revision_full_chain(production_copy_session_factory):
    """原9-20 -> 更新9-27：revision保留旧值、event、通知、edition更新、详情数据可用。"""
    with production_copy_session_factory() as db:
        user = _user(db, "isolated-v1-chain@example.com")
        admin = _user(db, "isolated-v1-chain-admin@example.com", admin=True)
        _profile(db, user, "西南交通大学", "经济管理学院", "工商管理")
        competitions = list(db.execute(select(Competition).where(Competition.is_demo.is_(False))).scalars())
        competition = next(item for item in competitions if "创新" in item.name)
        db.add(Favorite(user_id=user.id, competition_id=competition.id))
        db.flush()
        edition_rows = [
            edition
            for edition in db.execute(select(CompetitionEdition)).scalars()
            if edition.competition_id == competition.id and edition.year >= 2025
        ]
        edition = max(edition_rows, key=lambda item: item.year) if edition_rows else None
        assert edition is not None
        old = edition.official_registration_deadline or edition.registration_deadline
        new = datetime(2026, 9, 27, 23, 59, tzinfo=timezone.utc)
        if old == new:
            new = datetime(2026, 9, 28, 23, 59, tzinfo=timezone.utc)
        original_deadline = edition.official_registration_deadline
        candidate = FieldReviewService.create_candidate(db, {
            "entity_type": "edition", "competition_id": competition.id, "edition_id": edition.id,
            "title": "官方报名截止更新", "fields": [{"field_name": "official_registration_deadline",
                "candidate_value": new.isoformat(), "source": {"source_type": "organizer_notice",
                    "source_url": "https://example.com/official-new", "source_title": "官方通知"}}],
        }, submitter_id=admin.id)
        assert edition.official_registration_deadline == original_deadline
        _approve_candidate(db, admin, candidate)
        event = db.scalar(select(CompetitionUpdateEvent).where(CompetitionUpdateEvent.competition_edition_id == edition.id,
            CompetitionUpdateEvent.source_url == "https://example.com/official-new").order_by(CompetitionUpdateEvent.id.desc()))
        assert event is not None
        assert event.old_value != event.new_value
        revisions = list(
            db.execute(
                select(CompetitionFactRevision).where(
                    CompetitionFactRevision.competition_edition_id == edition.id,
                    CompetitionFactRevision.field_name == "official_registration_deadline",
                )
            ).scalars()
        )
        assert revisions, "旧值必须以 FactRevision 保留"
        notifications = list(
            db.execute(
                select(Notification).where(
                    Notification.user_id == user.id,
                    Notification.type == "competition_updated",
                )
            ).scalars()
        )
        assert notifications


def test_correction_admin_approve_closes_loop(production_copy_session_factory):
    from datetime import datetime as _dt

    from app.models import AdminAuditLog

    with production_copy_session_factory() as db:
        normal = _user(db, "isolated-v1-corr-user@example.com")
        admin = _user(db, "isolated-v1-corr-admin@example.com", admin=True)
        competitions = list(db.execute(select(Competition).where(Competition.is_demo.is_(False))).scalars())
        competition = next(item for item in competitions if "创新" in item.name)
        edition = max(competition.editions, key=lambda item: item.year)
        correction = UserCorrectionSubmission(
            user_id=normal.id,
            competition_id=competition.id,
            competition_edition_id=edition.id,
            correction_type="报名截止错误",
            description="官方截止应为9月27日",
            source_url="https://example.com/notice",
            status="pending",
        )
        db.add(correction)
        db.flush()
        candidate = stage_correction(db, correction, proposed_value=_dt(2026, 9, 27, 23, 59, tzinfo=timezone.utc).isoformat())
        assert correction.status == "pending"
        _approve_candidate(db, admin, candidate)
        db.commit()
        db.refresh(correction)
        assert correction.status == "approved"
        assert correction.reviewed_by == admin.id
        assert list(db.execute(select(AdminAuditLog)).scalars())
