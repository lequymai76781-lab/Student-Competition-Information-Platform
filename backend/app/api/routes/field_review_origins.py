"""Explicit, idempotent administrator transfer of legacy user evidence."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_db
from app.core.responses import success_response
from app.models import ReviewQueue, User, UserCorrectionSubmission
from app.services.field_review_origins import stage_correction, stage_supplement


router = APIRouter(prefix="/admin/field-review-origins", tags=["字段审核"])


@router.post("/{kind}/{item_id}")
def stage_origin(kind: Literal["correction", "supplement"], item_id: int,
                 admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    try:
        model = UserCorrectionSubmission if kind == "correction" else ReviewQueue
        row = db.get(model, item_id)
        if row is None:
            raise HTTPException(404, "原始提交不存在")
        candidate = stage_correction(db, row) if kind == "correction" else stage_supplement(db, row)
        result = {"field_review_id": candidate.id}
        db.commit()
        return success_response(result)
    except Exception:
        db.rollback()
        raise
