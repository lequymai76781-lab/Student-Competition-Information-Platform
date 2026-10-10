"""Unlisted schools/events enter the existing review queue, never the fact tables."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_user, get_db
from app.core.ratelimit import rate_limit
from app.core.responses import success_response
from app.models import BetaFeedback, ReviewQueue, User
from app.schemas.v1 import SupplementIn, SupplementReviewIn
from app.services.audit_service import record_admin_action
from app.services.field_review_origins import linked_field_review, require_field_review, stage_supplement

router = APIRouter(tags=["contributions"])


def _read(row: ReviewQueue) -> dict:
    return {"id": row.id, "kind": row.suggested_value, "title": row.reason,
            "description": row.evidence_text, "source_url": row.source_url,
            "status": row.status, "review_note": row.reviewer_notes,
            "created_at": row.created_at, "reviewed_at": row.reviewed_at}


@router.post("/users/me/supplements")
def submit_supplement(payload: SupplementIn, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db),
                      _: None = Depends(rate_limit("supplements_submit", limit=5, window_seconds=60))) -> dict:
    submission = BetaFeedback(user_id=user.id, category="数据补充", content=payload.description,
                              url=payload.source_url, status="pending")
    try:
        db.add(submission)
        db.flush()
        row = ReviewQueue(item_type="user_supplement", item_id=submission.id, reason=payload.title,
                          suggested_value=payload.kind, evidence_text=payload.description,
                          source_url=payload.source_url, status="pending", is_demo=False)
        db.add(row)
        db.flush()
        candidate = stage_supplement(db, row) if payload.kind == "competition" else None
        result = {**_read(row), "field_review_id": candidate.id if candidate else None}
        db.commit()
    except Exception:
        db.rollback()
        raise
    return success_response(result, message="submitted_for_review")


@router.get("/users/me/supplements")
def my_supplements(user: User = Depends(get_current_user), db: Session = Depends(get_db),
                   limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)) -> dict:
    rows = db.scalars(select(ReviewQueue).join(BetaFeedback, BetaFeedback.id == ReviewQueue.item_id)
        .where(ReviewQueue.item_type == "user_supplement", BetaFeedback.user_id == user.id)
        .order_by(ReviewQueue.created_at.desc(), ReviewQueue.id.desc()).limit(limit).offset(offset)).all()
    return success_response([_read(row) for row in rows])


@router.get("/admin/review/supplements")
def list_supplements(admin: User = Depends(get_current_admin), db: Session = Depends(get_db),
                     limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                     status: str = Query("unfinished", pattern="^(unfinished|all|pending|needs_more_evidence|partially_approved|approved|verified_pending_import|rejected|duplicate)$")) -> dict:
    query = select(ReviewQueue).where(ReviewQueue.item_type == "user_supplement")
    if status == "unfinished":
        query = query.where(ReviewQueue.status.in_(["pending", "needs_more_evidence", "partially_approved"]))
    elif status != "all":
        query = query.where(ReviewQueue.status == status)
    rows = db.scalars(query.order_by(ReviewQueue.created_at.desc(), ReviewQueue.id.desc())
                      .offset(offset).limit(limit)).all()
    return success_response([{**_read(row), "field_review_id": linked.id if
        (linked := linked_field_review(db, "user_supplement", row.item_id)) else None} for row in rows])


@router.put("/admin/review/supplements/{item_id}")
def review_supplement(item_id: int, payload: SupplementReviewIn,
                      admin: User = Depends(get_current_admin), db: Session = Depends(get_db)) -> dict:
    try:
        row = db.get(ReviewQueue, item_id)
        if row is None or row.item_type != "user_supplement":
            raise HTTPException(404, "补充记录不存在")
        require_field_review(db, "user_supplement", row.item_id)
        if row.suggested_value == "competition":
            raise HTTPException(409, "赛事补充请先转入 /admin/field-review 核验来源并逐字段处理")
        if row.status in {"verified_pending_import", "rejected", "duplicate"}:
            raise HTTPException(409, "该记录已处理")
        submission = db.get(BetaFeedback, row.item_id)
        if submission is None:
            raise HTTPException(409, "缺少原始提交记录")
        before = row.status
        changed = db.execute(update(ReviewQueue).where(
            ReviewQueue.id == row.id, ReviewQueue.status == before,
            ReviewQueue.reviewed_at == row.reviewed_at,
        ).values(status=payload.status, reviewed_at=datetime.now(timezone.utc),
                 assigned_to=str(admin.id), reviewer_notes=payload.note)
          .execution_options(synchronize_session=False))
        if changed.rowcount != 1:
            raise HTTPException(409, "该记录已被其他管理员处理，请刷新")
        db.refresh(row)
        submission.status = payload.status
        record_admin_action(db, admin_id=admin.id, action="supplement_review", object_type="review_queue",
                            object_id=row.id, before={"status": before}, after={"status": row.status, "note": payload.note})
        result = _read(row)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return success_response(result)
