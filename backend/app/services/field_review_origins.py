"""Adapt private user evidence to candidates without writing official facts."""
import json

from fastapi import HTTPException
from sqlalchemy import select, update

from app.models import BetaFeedback, ReviewQueue
from app.services.field_review_service import FieldReviewService


CORRECTION_FIELDS = {
    "报名截止错误": ("edition", "official_registration_deadline"),
    "官网失效": ("competition", "official_website"),
    "赛事名称错误": ("competition", "name"),
    "主办方错误": ("competition", "organizer"),
}


def linked_field_review(db, kind: str, origin_id: int):
    rows = db.scalars(select(ReviewQueue).where(
        ReviewQueue.item_type == "field_candidate", ReviewQueue.item_id == origin_id,
    ).order_by(ReviewQueue.id))
    for row in rows:
        try:
            document = json.loads(row.raw_value or "{}")
        except (ValueError, TypeError):
            continue
        if document.get("origin_kind") == kind and document.get("origin_id") == origin_id:
            return row
    return None


def require_field_review(db, kind: str, origin_id: int):
    if linked_field_review(db, kind, origin_id) is not None:
        raise HTTPException(409, "该提交已进入字段审核，请到 /admin/field-review 核验来源并逐字段处理")


def _source(url):
    return {"source_type": "user_submission", "source_title": "用户提交的来源", "source_url": url}


def _lock_origin(db, row):
    # A no-op UPDATE acquires a write lock on SQLite as well as row locks on
    # PostgreSQL. Recheck the candidate only AFTER this lock; SELECT FOR UPDATE
    # alone is ignored by SQLite and permits two candidates for one submission.
    model = type(row)
    changed = db.execute(update(model).where(model.id == row.id).values(updated_at=model.updated_at)
                         .execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        raise HTTPException(409, "原始提交已变化，请刷新后重试")
    db.refresh(row)


def stage_correction(db, row, *, proposed_value=None):
    _lock_origin(db, row)
    existing = linked_field_review(db, "user_correction", row.id)
    if existing is not None:
        existing.source_url = existing.source_url or row.source_url
        return existing
    if row.status not in {"pending", "needs_more_evidence"}:
        raise HTTPException(409, "该纠错已处理，不能重复转入")
    entity_type, field = CORRECTION_FIELDS.get(row.correction_type, ("competition", None))
    if proposed_value is not None and field is None:
        raise HTTPException(422, "此纠错类型请用具体说明提交，等待管理员结构化")
    if entity_type == "edition" and row.competition_edition_id is None:
        if proposed_value is not None:
            raise HTTPException(422, "截止建议必须明确目标届次")
        entity_type = "competition"  # Free text retains evidence; prepare must choose an edition.
    candidate = FieldReviewService.create_candidate(db, {
        "entity_type": entity_type, "competition_id": row.competition_id,
        "edition_id": row.competition_edition_id if entity_type == "edition" else None,
        "title": row.correction_type, "description": row.description,
        "origin": "user_submission", "origin_kind": "user_correction", "origin_id": row.id,
        "fields": [] if proposed_value is None else [{
            "field_name": field, "candidate_value": proposed_value, "source": _source(row.source_url),
        }],
    }, submitter_id=row.user_id)
    candidate.source_url = row.source_url
    return candidate


def stage_supplement(db, row):
    _lock_origin(db, row)
    if row.item_type != "user_supplement" or row.suggested_value != "competition":
        raise HTTPException(422, "本阶段只支持赛事补充进入字段审核")
    existing = linked_field_review(db, "user_supplement", row.item_id)
    if existing is not None:
        existing.source_url = existing.source_url or row.source_url
        return existing
    if row.status not in {"pending", "needs_more_evidence", "verified_pending_import"}:
        raise HTTPException(409, "该补充已处理，不能重复转入")
    submission = db.get(BetaFeedback, row.item_id)
    if submission is None:
        raise HTTPException(409, "缺少原始提交记录")
    candidate = FieldReviewService.create_candidate(db, {
        "entity_type": "competition", "title": row.reason, "description": row.evidence_text,
        "origin": "user_submission", "origin_kind": "user_supplement", "origin_id": submission.id,
        "fields": [{"field_name": "name", "candidate_value": row.reason, "source": _source(row.source_url)}],
    }, submitter_id=submission.user_id)
    candidate.source_url = row.source_url
    return candidate
