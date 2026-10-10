from __future__ import annotations

import logging

from fastapi import Query, APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_current_user_optional, get_db
from app.core.responses import ApiResponse, success_response
from app.services.field_review_origins import stage_correction
from app.core.ratelimit import rate_limit
from app.models import (
    BetaFeedback,
    College,
    Competition,
    CompetitionEdition,
    Favorite,
    Major,
    Notification,
    ReviewQueue,
    University,
    User,
    UserCompetitionStatus,
    UserCorrectionSubmission,
)
from app.schemas.user import FavoriteIn, ProfileUpdateIn, StatusUpdateIn
from app.schemas.v1 import CorrectionIn, FeedbackIn
from app.services.notification_service import NotificationService
from app.services.audit_service import record_metric
from app.services.personal_competition_service import (
    INTEREST_SYNONYMS,
    PersonalCompetitionService,
)

router = APIRouter(tags=["v0.9-users"])
service = PersonalCompetitionService()
notification_service = NotificationService()
logger = logging.getLogger("v1.ops")


def _profile(db: Session, user: User):
    if user.profile is None:
        from app.models import UserProfile

        profile = UserProfile(user_id=user.id)
        db.add(profile)
        db.flush()
    return user.profile


@router.get("/users/me/profile", response_model=ApiResponse)
def get_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return success_response(service.profile_context(db, user))


@router.put("/users/me/profile", response_model=ApiResponse)
def update_profile(
    payload: ProfileUpdateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit("profile_update", limit=20, window_seconds=60)),
) -> dict:
    profile = _profile(db, user)
    university_id = payload.university_id
    university_name = payload.university_name
    if university_name and university_id is None:
        university = db.execute(
            select(University).where(University.name == university_name)
        ).scalar_one_or_none()
        if university is not None:
            university_id = university.id
            university_name = university.name

    college_id = payload.college_id
    college_name = payload.college_name
    if college_name and college_id is None and university_id is not None:
        college = db.execute(
            select(College).where(
                College.university_id == university_id,
                College.name == college_name.strip(),
            )
        ).scalar_one_or_none()
        if college is not None and college.is_verified and not college.is_demo:
            college_id = college.id
            college_name = college.name

    major_id = payload.major_id
    major_name = payload.major_name
    if major_name and major_id is None:
        major = db.execute(
            select(Major).where(Major.name == major_name.strip())
        ).scalar_one_or_none()
        if major is not None:
            major_id = major.id
            major_name = major.name

    updates = {
        "university_id": university_id,
        "university_name": university_name,
        "college_id": college_id,
        "college_name": college_name,
        "major_id": major_id,
        "major_name": major_name,
        "grade": payload.grade,
        "graduation_year": payload.graduation_year or _infer_graduation(payload.grade),
        "interest_tags": payload.interest_tags,
        "skills": payload.skills,
        "preferred_team_type": payload.preferred_team_type,
        "weekly_available_hours": payload.weekly_available_hours,
        "accept_cross_major": payload.accept_cross_major,
        "accept_cross_university": payload.accept_cross_university,
    }
    # A new free-text name replaces an old directory link; it is not a request
    # to verify or create a shared directory entry.
    if college_name and payload.college_id is None:
        profile.college_id = college_id
    if major_name and payload.major_id is None:
        profile.major_id = major_id
    for key, value in updates.items():
        if value is not None:
            setattr(profile, key, value)
    if profile.university_id is not None and (payload.university_id or payload.university_name):
        record_metric(db, "profile_completed", user.id)
    db.commit()
    return success_response(
        {
            "user": service.profile_context(db, user),
            "onboarding_complete": profile.university_id is not None,
        },
        message="updated",
    )


@router.get("/users/me/overview", response_model=ApiResponse)
def overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    record_metric(db, "my_competitions_view", user.id)
    return success_response(service.overview(db, user))


@router.get("/users/me/competitions/{competition_id}/context", response_model=ApiResponse)
def competition_context(
    competition_id: int,
    edition_id: int | None = None,
    university_id: int | None = None,
    college_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return success_response(service.competition_context(db, user, competition_id,
        edition_id=edition_id, university_id=university_id, college_id=college_id,
        use_profile_scope=university_id is None and college_id is None))


@router.get("/users/me/calendar-events", response_model=ApiResponse)
def calendar_events(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    record_metric(db, "calendar_view", user.id)
    return success_response(service.upcoming_events(db, user))


@router.get("/users/me/favorites", response_model=ApiResponse)
def list_favorites(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    rows = db.execute(
        select(Competition)
        .join(Favorite, Favorite.competition_id == Competition.id)
        .where(Favorite.user_id == user.id, Competition.is_demo.is_(False))
    ).scalars().all()
    return success_response(
        [
            {"competition_id": row.id, "name": row.name, "short_name": row.short_name}
            for row in rows
        ]
    )


@router.post("/users/me/favorites", response_model=ApiResponse)
def add_favorite(
    payload: FavoriteIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if db.get(Competition, payload.competition_id) is None:
        raise HTTPException(status_code=404, detail="赛事不存在")
    existing = db.execute(
        select(Favorite).where(
            Favorite.user_id == user.id,
            Favorite.competition_id == payload.competition_id,
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(Favorite(user_id=user.id, competition_id=payload.competition_id))
        record_metric(db, "favorited", user.id)
        db.commit()
    return success_response({"competition_id": payload.competition_id, "favorite": True})


@router.delete("/users/me/favorites/{competition_id}", response_model=ApiResponse)
def remove_favorite(
    competition_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    row = db.execute(
        select(Favorite).where(
            Favorite.user_id == user.id,
            Favorite.competition_id == competition_id,
        )
    ).scalar_one_or_none()
    if row is not None:
        db.delete(row)
        db.commit()
    return success_response({"competition_id": competition_id, "favorite": False})


@router.put("/users/me/competitions/{competition_id}/status", response_model=ApiResponse)
def set_status(
    competition_id: int,
    payload: StatusUpdateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if db.get(Competition, competition_id) is None:
        raise HTTPException(status_code=404, detail="赛事不存在")
    row = db.execute(
        select(UserCompetitionStatus).where(
            UserCompetitionStatus.user_id == user.id,
            UserCompetitionStatus.competition_id == competition_id,
        )
    ).scalar_one_or_none()
    if row is None:
        row = UserCompetitionStatus(
            user_id=user.id,
            competition_id=competition_id,
            status=payload.status,
            notes=payload.notes,
        )
        db.add(row)
    else:
        row.status = payload.status
        if payload.notes is not None:
            row.notes = payload.notes
    db.commit()
    return success_response({"competition_id": competition_id, "status": payload.status})


@router.get("/directory/interest-options", response_model=ApiResponse)
def interest_options() -> dict:
    options = [
        {"label": label, "tags": sorted(set(targets))}
        for label, targets in INTEREST_SYNONYMS.items()
    ]
    return success_response(options)


@router.get("/directory/universities/{university_id}/colleges", response_model=ApiResponse)
def university_colleges(university_id: int, db: Session = Depends(get_db)) -> dict:
    rows = db.execute(
        select(College)
        .where(College.university_id == university_id, College.is_demo.is_(False), College.is_verified.is_(True))
        .order_by(College.name.asc())
    ).scalars().all()
    return success_response([{"id": row.id, "name": row.name} for row in rows])


@router.get("/directory/colleges/{college_id}/majors", response_model=ApiResponse)
def college_majors(college_id: int, db: Session = Depends(get_db)) -> dict:
    college = db.get(College, college_id)
    if college is None:
        return success_response([])
    rows = db.execute(select(Major).order_by(Major.name.asc())).scalars().all()
    return success_response([{"id": row.id, "name": row.name} for row in rows])


def _infer_graduation(grade: str | None) -> int | None:
    if not grade:
        return None
    grade_map = {
        "大一": 2030,
        "大二": 2029,
        "大三": 2028,
        "大四": 2027,
    }
    for key, year in grade_map.items():
        if key in grade:
            return year
    if "研一" in grade or "研二" in grade or "研三" in grade or "研究生" in grade:
        return None
    return None


# --------------------------------------------------------------------------- #
# V1.0 notifications
# --------------------------------------------------------------------------- #
@router.get("/users/me/notifications", response_model=ApiResponse)
def list_notifications(
    category: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit("notifications_read", limit=120, window_seconds=60)),
) -> dict:
    record_metric(db, "notifications_view", user.id)
    data = notification_service.list_for_user(
        db,
        user,
        category=category,
        limit=min(limit, 100),
        offset=offset,
    )
    return success_response(data)


@router.post("/users/me/notifications/{notification_id}/read", response_model=ApiResponse)
def read_notification(
    notification_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return success_response({"updated": notification_service.mark_read(db, user, notification_id)})


@router.get("/users/me/notifications/unread-count", response_model=ApiResponse)
def unread_count(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit("notifications_read", limit=120, window_seconds=60)),
) -> dict:
    return success_response({"unread": notification_service.unread_count(db, user)})


# --------------------------------------------------------------------------- #
# V1.0 corrections & feedback
# --------------------------------------------------------------------------- #
@router.post("/users/me/corrections", response_model=ApiResponse)
def submit_correction(
    payload: CorrectionIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit("corrections_submit", limit=5, window_seconds=60)),
) -> dict:
    competition = db.get(Competition, payload.competition_id)
    if competition is None:
        raise HTTPException(status_code=404, detail="赛事不存在")
    if payload.competition_edition_id is not None:
        edition = db.get(CompetitionEdition, payload.competition_edition_id)
        if edition is None or edition.competition_id != payload.competition_id:
            raise HTTPException(status_code=422, detail="届次不属于此赛事")
    row = UserCorrectionSubmission(
        user_id=user.id,
        competition_id=payload.competition_id,
        competition_edition_id=payload.competition_edition_id,
        correction_type=payload.correction_type,
        description=payload.description,
        source_url=payload.source_url,
        contact_note=payload.contact_note,
        status="pending",
    )
    try:
        db.add(row)
        db.flush()
        db.add(ReviewQueue(item_type="user_correction", item_id=row.id, competition_id=row.competition_id,
            reason=row.correction_type, evidence_text=row.description, source_url=row.source_url,
            status="pending", is_demo=False))
        candidate = stage_correction(db, row, proposed_value=payload.proposed_value)
        record_metric(db, "correction_submitted", user.id)
        result = {"id": row.id, "status": "pending", "field_review_id": candidate.id}
        db.commit()
    except Exception:
        db.rollback()
        raise
    return success_response(result, message="submitted")


@router.get("/users/me/corrections", response_model=ApiResponse)
def my_corrections(
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
) -> dict:
    rows = db.execute(
        select(UserCorrectionSubmission)
        .where(UserCorrectionSubmission.user_id == user.id)
        .order_by(UserCorrectionSubmission.created_at.desc(), UserCorrectionSubmission.id.desc())
        .limit(limit).offset(offset)
    ).scalars().all()
    return success_response(
        [
            {
                "id": row.id,
                "competition_id": row.competition_id,
                "correction_type": row.correction_type,
                "competition_edition_id": row.competition_edition_id,
                "source_url": row.source_url,
                "review_note": row.review_note,
                "description": row.description,
                "status": row.status,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
    )


@router.post("/beta-feedback", response_model=ApiResponse)
def submit_feedback(
    payload: FeedbackIn,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
    _: None = Depends(rate_limit("feedback_submit", limit=3, window_seconds=60)),
) -> dict:
    row = BetaFeedback(
        user_id=user.id if user else None,
        category=payload.category,
        content=payload.content,
        url=payload.url,
        status="pending",
    )
    db.add(row)
    record_metric(db, "feedback_submitted", user.id if user else None)
    db.commit()
    return success_response({"id": row.id}, message="submitted")
