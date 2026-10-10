from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
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
    ReviewQueue,
    UserCorrectionSubmission,
    UserCorrectionSubmission as _Correction,
)
from app.schemas.v1 import ReviewActionIn
from app.services.audit_service import record_admin_action
from app.services.field_review_origins import linked_field_review, require_field_review

router = APIRouter(tags=["v1.0-admin"])


def _supplement_feedback_ids():
    return select(ReviewQueue.item_id).where(ReviewQueue.item_type == "user_supplement")


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
            "beta_feedback_pending": count(BetaFeedback, BetaFeedback.status == "pending",
                                            BetaFeedback.id.not_in(_supplement_feedback_ids())),
        }
    )


@router.get("/admin/review/corrections", response_model=ApiResponse)
def list_corrections(
    status: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    query = select(UserCorrectionSubmission).order_by(UserCorrectionSubmission.created_at.desc(), UserCorrectionSubmission.id.desc())
    if status == "unfinished":
        query = query.where(UserCorrectionSubmission.status.in_(["pending", "needs_more_evidence", "partially_approved"]))
    elif status and status != "all":
        query = query.where(UserCorrectionSubmission.status == status)
    rows = db.execute(query.limit(limit).offset(offset)).scalars().all()
    competitions = {c.id: c.name for c in db.execute(select(Competition)).scalars()}
    editions = list(db.scalars(select(CompetitionEdition)).all())
    return success_response(
        [
            {
                "id": row.id,
                "competition_id": row.competition_id,
                "field_review_id": linked.id if (linked := linked_field_review(db, "user_correction", row.id)) else None,
                "competition_name": competitions.get(row.competition_id),
                "competition_edition_id": row.competition_edition_id,
                "editions": [{"id": edition.id, "name": edition.edition_name or str(edition.year)}
                             for edition in editions if edition.competition_id == row.competition_id],
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
    from datetime import datetime, timezone

    try:
        row = db.get(UserCorrectionSubmission, correction_id)
        if row is None:
            raise HTTPException(status_code=404, detail="纠错不存在")
        require_field_review(db, "user_correction", row.id)
        if row.status in {"approved", "rejected", "duplicate"}:
            raise HTTPException(status_code=409, detail="该纠错已处理")
        if payload.status == "approved":
            raise HTTPException(409, "纠错批准须先转入 /admin/field-review 核验来源并逐字段处理")
        before = {"status": row.status, "id": row.id}
        reviewed_at = datetime.now(timezone.utc)
        # Claim the observed version before mutating any facts or notifications.
        changed = db.execute(update(UserCorrectionSubmission).where(
            UserCorrectionSubmission.id == row.id,
            UserCorrectionSubmission.status == row.status,
            UserCorrectionSubmission.reviewed_at == row.reviewed_at,
        ).values(status=payload.status, reviewed_by=admin.id, reviewed_at=reviewed_at,
                 review_note=payload.note)
          .execution_options(synchronize_session=False))
        if changed.rowcount != 1:
            raise HTTPException(status_code=409, detail="该纠错已被其他管理员处理，请刷新")
        db.refresh(row)
        queue = db.scalar(select(ReviewQueue).where(ReviewQueue.item_type == "user_correction", ReviewQueue.item_id == row.id))
        if queue is not None:
            queue.status = row.status
            queue.reviewed_at = row.reviewed_at
            queue.reviewer_notes = row.review_note
            queue.assigned_to = str(admin.id)
        record_admin_action(
            db, admin_id=admin.id, action=f"correction_{payload.status}",
            object_type="user_correction_submission", object_id=row.id,
            before=before, after={"status": payload.status},
        )
        result = {"id": row.id, "status": row.status}
        db.commit()
    except Exception:
        db.rollback()
        raise
    return success_response(result, message="reviewed")


@router.get("/admin/review/leads", response_model=ApiResponse)
def list_leads(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.execute(
        select(CompetitionLead)
        .where(CompetitionLead.needs_review.is_(True))
        .order_by(CompetitionLead.discovered_at.desc(), CompetitionLead.id.desc())
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
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.execute(
        select(CandidateFact)
        .where(CandidateFact.needs_review.is_(True))
        .order_by(CandidateFact.created_at.desc(), CandidateFact.id.desc())
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
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.execute(
        select(CompetitionUpdateEvent)
        .order_by(CompetitionUpdateEvent.changed_at.desc(), CompetitionUpdateEvent.id.desc())
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
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    query = select(BetaFeedback).where(BetaFeedback.id.not_in(_supplement_feedback_ids())).order_by(BetaFeedback.created_at.desc(), BetaFeedback.id.desc())
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
    if db.scalar(select(ReviewQueue.id).where(ReviewQueue.item_type == "user_supplement", ReviewQueue.item_id == row.id)):
        raise HTTPException(status_code=409, detail="请在信息补充入口审核此记录")
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
