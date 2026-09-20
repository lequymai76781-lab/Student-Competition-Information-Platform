from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_db
from app.core.responses import ApiResponse, success_response
from app.models import (
    BetaFeedback,
    CandidateFact,
    Competition,
    CompetitionEdition,
    CompetitionLead,
    CompetitionUpdateEvent,
    User,
    UserCorrectionSubmission,
    UserCorrectionSubmission as _Correction,
)
from app.schemas.v1 import ReviewActionIn
from app.services.audit_service import record_admin_action
from app.services.notification_service import NotificationService

router = APIRouter(tags=["v1.0-admin"])
notification_service = NotificationService()


@router.get("/admin/review/summary", response_model=ApiResponse)
def review_summary(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)) -> dict:
    def count(model, *criteria):
        query = select(func.count()).select_from(model)
        for criterion in criteria:
            query = query.where(criterion)
        return db.execute(query).scalar_one()

    return success_response(
        {
            "corrections_pending": count(UserCorrectionSubmission, UserCorrectionSubmission.status == "pending"),
            "leads_needs_review": count(CompetitionLead, CompetitionLead.needs_review.is_(True)),
            "candidate_facts_needs_review": count(CandidateFact, CandidateFact.needs_review.is_(True)),
            "update_events": count(CompetitionUpdateEvent),
            "beta_feedback_pending": count(BetaFeedback, BetaFeedback.status == "pending"),
        }
    )


@router.get("/admin/review/corrections", response_model=ApiResponse)
def list_corrections(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    query = select(UserCorrectionSubmission).order_by(UserCorrectionSubmission.created_at.desc())
    if status:
        query = query.where(UserCorrectionSubmission.status == status)
    rows = db.execute(query.limit(limit).offset(offset)).scalars().all()
    competitions = {c.id: c.name for c in db.execute(select(Competition)).scalars()}
    return success_response(
        [
            {
                "id": row.id,
                "competition_id": row.competition_id,
                "competition_name": competitions.get(row.competition_id),
                "correction_type": row.correction_type,
                "description": row.description,
                "source_url": row.source_url,
                "status": row.status,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
    )


@router.put("/admin/review/corrections/{correction_id}", response_model=ApiResponse)
def review_correction(
    correction_id: int,
    payload: ReviewActionIn,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    row = db.get(UserCorrectionSubmission, correction_id)
    if row is None:
        raise HTTPException(status_code=404, detail="纠错不存在")
    from datetime import datetime, timezone

    row.status = payload.status
    row.reviewed_by = admin.id
    row.reviewed_at = datetime.now(timezone.utc)
    row.review_note = payload.note
    before = {"status": "pending", "id": row.id}
    if payload.status == "approved" and payload.new_deadline is not None and "截止" in (row.correction_type or ""):
        editions = list(
            db.execute(
                select(CompetitionEdition)
                .where(CompetitionEdition.competition_id == row.competition_id)
            ).scalars()
        )
        if editions:
            edition = max(editions, key=lambda item: item.year)
            old_value = edition.official_registration_deadline
            notification_service.apply_deadline_update(
                db,
                edition,
                new_deadline=payload.new_deadline,
                source_url=row.source_url or "https://platform.local/correction",
                source_name="用户纠错经管理员核验",
                field_name="official_registration_deadline",
            )
            after_deadline = {
                "old": old_value.isoformat() if old_value else None,
                "new": payload.new_deadline.isoformat(),
            }
            record_admin_action(
                db,
                admin_id=admin.id,
                action="correction_approved_apply_deadline",
                object_type="competition_edition",
                object_id=edition.id,
                before=before,
                after={"deadline": after_deadline, "status": payload.status},
            )
    record_admin_action(
        db,
        admin_id=admin.id,
        action=f"correction_{payload.status}",
        object_type="user_correction_submission",
        object_id=row.id,
        before=before,
        after={"status": payload.status},
    )
    db.commit()
    return success_response({"id": row.id, "status": row.status}, message="reviewed")


@router.get("/admin/review/leads", response_model=ApiResponse)
def list_leads(
    limit: int = 50,
    offset: int = 0,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.execute(
        select(CompetitionLead)
        .where(CompetitionLead.needs_review.is_(True))
        .order_by(CompetitionLead.discovered_at.desc())
        .limit(limit)
        .offset(offset)
    ).scalars().all()
    return success_response(
        [
            {
                "id": row.id,
                "title": row.raw_title,
                "classification": row.classification,
                "source_url": row.source_url,
                "verification_status": row.verification_status,
                "discovered_at": row.discovered_at.isoformat() if row.discovered_at else None,
            }
            for row in rows
        ]
    )


@router.put("/admin/review/leads/{lead_id}", response_model=ApiResponse)
def review_lead(
    lead_id: int,
    payload: ReviewActionIn,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    row = db.get(CompetitionLead, lead_id)
    if row is None:
        raise HTTPException(status_code=404, detail="线索不存在")
    row.needs_review = payload.status != "approved"
    row.metadata_json = dict(row.metadata_json or {})
    row.metadata_json["review_note"] = payload.note
    row.metadata_json["reviewed_by"] = admin.id
    record_admin_action(
        db,
        admin_id=admin.id,
        action=f"lead_{payload.status}",
        object_type="competition_lead",
        object_id=row.id,
        before={"needs_review": True},
        after={"needs_review": row.needs_review},
    )
    db.commit()
    return success_response({"id": row.id, "needs_review": row.needs_review})


@router.get("/admin/review/candidate-facts", response_model=ApiResponse)
def list_candidate_facts(
    limit: int = 50,
    offset: int = 0,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.execute(
        select(CandidateFact)
        .where(CandidateFact.needs_review.is_(True))
        .order_by(CandidateFact.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).scalars().all()
    return success_response(
        [
            {
                "id": row.id,
                "field_name": row.field_name,
                "candidate_value": row.candidate_value,
                "source_url": row.source_url,
                "confidence": row.confidence,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
    )


@router.get("/admin/review/updates", response_model=ApiResponse)
def list_updates(
    limit: int = 50,
    offset: int = 0,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.execute(
        select(CompetitionUpdateEvent)
        .order_by(CompetitionUpdateEvent.changed_at.desc())
        .limit(limit)
        .offset(offset)
    ).scalars().all()
    competitions = {c.id: c.name for c in db.execute(select(Competition)).scalars()}
    return success_response(
        [
            {
                "id": row.id,
                "competition_id": row.competition_id,
                "competition_name": competitions.get(row.competition_id),
                "event_type": row.event_type,
                "old_value": row.old_value,
                "new_value": row.new_value,
                "source_url": row.source_url,
                "changed_at": row.changed_at.isoformat() if row.changed_at else None,
            }
            for row in rows
        ]
    )


@router.get("/admin/review/feedback", response_model=ApiResponse)
def list_feedback(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    query = select(BetaFeedback).order_by(BetaFeedback.created_at.desc())
    if status:
        query = query.where(BetaFeedback.status == status)
    rows = db.execute(query.limit(limit).offset(offset)).scalars().all()
    return success_response(
        [
            {
                "id": row.id,
                "category": row.category,
                "content": row.content,
                "url": row.url,
                "status": row.status,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
    )


@router.put("/admin/review/feedback/{feedback_id}", response_model=ApiResponse)
def review_feedback(
    feedback_id: int,
    payload: ReviewActionIn,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    row = db.get(BetaFeedback, feedback_id)
    if row is None:
        raise HTTPException(status_code=404, detail="反馈不存在")
    row.status = payload.status
    record_admin_action(
        db,
        admin_id=admin.id,
        action=f"feedback_{payload.status}",
        object_type="beta_feedback",
        object_id=row.id,
        after={"status": payload.status},
    )
    db.commit()
    return success_response({"id": row.id, "status": row.status})
