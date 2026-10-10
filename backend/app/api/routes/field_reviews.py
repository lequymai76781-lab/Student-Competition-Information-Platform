"""Administrator-only, candidate-based field review endpoints."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_db
from app.core.responses import ApiResponse, success_response
from app.models import User
from app.schemas.field_review import (
    FieldBulkReviewIn, FieldCandidateIn, FieldPrepareIn, FieldReviewIn, FieldSourceVerifyIn,
)
from app.services.field_review_service import FieldReviewService
from app.schemas.school_relation_review import SchoolRelationPrepareIn, SchoolRelationSourceVerifyIn, SchoolRelationReviewIn
from app.schemas.review_telemetry import ReviewTelemetryStartIn, ReviewTelemetryEventIn


router = APIRouter(prefix="/admin/field-reviews", tags=["字段审核"])


def _write(db, operation, *, learning_admin=None, learning_session_id=None, learning_candidate_id=None):
    try:
        binding = None
        if learning_session_id is not None:
            from app.services.review_learning_service import bind_learning_review
            binding = bind_learning_review(db, learning_admin, learning_candidate_id, learning_session_id)
        data = operation()
        if binding:
            from app.services.review_learning_service import attach_learning_audit
            attach_learning_audit(db, learning_admin, learning_candidate_id, binding)
        db.commit()
        if learning_admin is not None:
            from app.services.review_learning_service import finalize_learning_after_commit
            finalize_learning_after_commit(db, learning_admin, data, learning_session_id)
        return success_response(data)
    except Exception:
        db.rollback()
        raise


@router.get("/config", response_model=ApiResponse)
def config(admin: User = Depends(get_current_admin)):
    return success_response(FieldReviewService.config())


@router.get("", response_model=ApiResponse)
@router.get("/", response_model=ApiResponse, include_in_schema=False)
def list_candidates(
    status: Literal["pending", "approved", "rejected", "partially_approved", "deferred", "all"] | None = None,
    flag: Literal["CONFLICT", "NO_SOURCE", "UNVERIFIED", "DUPLICATE_SUSPECTED", "edition_uncertain", "LOW_RISK", "HIGH_RISK", "RELATION_CONFLICT"] | None = None,
    entity_type: Literal["competition", "edition"] | None = None,
    competition_id: int | None = Query(None, gt=0),
    university_id: int | None = Query(None, gt=0),
    source_type: str | None = None,
    submitter_id: int | None = Query(None, gt=0),
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    risk: Literal["LOW_RISK", "HIGH_RISK"] | None = None,
    search: str | None = Query(None, max_length=200),
    relation_type: str | None = Query(None, max_length=80),
    sort: Literal["newest", "oldest", "priority"] = "newest",
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return success_response(FieldReviewService.list_candidates(db, status=status, flag=flag, entity_type=entity_type,
        competition_id=competition_id, university_id=university_id, source_type=source_type, submitter_id=submitter_id,
        created_from=created_from, created_to=created_to, risk=risk, search=search,
        relation_type=relation_type, sort=sort, limit=limit, offset=offset))


@router.get("/statistics", response_model=ApiResponse)
def statistics(mode: Literal["human", "automation"] | None = None,
               admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    from app.services.review_queue_query import statistics as queue_statistics
    from app.services.review_telemetry_service import ReviewTelemetryService
    return success_response({"counts": queue_statistics(db), "telemetry": ReviewTelemetryService.statistics(db, admin, mode=mode)})


@router.post("/bulk-preview", response_model=ApiResponse)
def bulk_preview(payload: FieldBulkReviewIn, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return success_response(FieldReviewService.bulk_preview(db, payload, admin=admin))


@router.post("", response_model=ApiResponse)
@router.post("/", response_model=ApiResponse, include_in_schema=False)
def create_candidate(payload: FieldCandidateIn, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    def create():
        row = FieldReviewService.create_candidate(db, payload, submitter_id=admin.id)
        return FieldReviewService.detail(db, row)
    return _write(db, create)


@router.post("/bulk-review", response_model=ApiResponse)
def bulk_review(payload: FieldBulkReviewIn, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return _write(db, lambda: FieldReviewService.bulk_review(db, payload, admin=admin))


@router.get("/{identity}", response_model=ApiResponse)
def detail(identity: int, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return success_response(FieldReviewService.detail(db, identity))


@router.put("/{identity}/prepare", response_model=ApiResponse)
def prepare(identity: int, payload: FieldPrepareIn, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return _write(db, lambda: FieldReviewService.prepare(db, identity, payload, admin=admin))


@router.post("/{identity}/reject-unstructured", response_model=ApiResponse)
def reject_unstructured(identity: int, payload: FieldSourceVerifyIn,
                        admin: User = Depends(get_current_admin), db: Session = Depends(get_db),
                        learning_session_id: str | None = Header(None, alias='X-Review-Learning-Session')):
    return _write(db, lambda: FieldReviewService.reject_unstructured(db, identity, payload, admin=admin), learning_admin=admin,
        learning_session_id=learning_session_id, learning_candidate_id=identity)


@router.post("/{identity}/sources/{proposal_id}/verify", response_model=ApiResponse)
def verify_source(identity: int, proposal_id: str, payload: FieldSourceVerifyIn,
                  admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return _write(db, lambda: FieldReviewService.verify_source(db, identity, proposal_id, payload, admin=admin))


@router.post("/{identity}/review", response_model=ApiResponse)
def review(identity: int, payload: FieldReviewIn, admin: User = Depends(get_current_admin), db: Session = Depends(get_db),
           learning_session_id: str | None = Header(None, alias='X-Review-Learning-Session')):
    return _write(db, lambda: FieldReviewService.review(db, identity, payload, admin=admin), learning_admin=admin,
        learning_session_id=learning_session_id, learning_candidate_id=identity)


@router.post("/{identity}/timing/start", response_model=ApiResponse)
def start_timing(identity: int, payload: ReviewTelemetryStartIn, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    from app.services.review_telemetry_service import ReviewTelemetryService
    return _write(db, lambda: ReviewTelemetryService.start(db, identity, payload, admin=admin))


@router.post("/{identity}/timing/event", response_model=ApiResponse)
def timing_event(identity: int, payload: ReviewTelemetryEventIn, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    from app.services.review_telemetry_service import ReviewTelemetryService
    return _write(db, lambda: ReviewTelemetryService.event(db, identity, payload, admin=admin))


@router.put("/{identity}/relation/prepare", response_model=ApiResponse)
def prepare_relation(identity: int, payload: SchoolRelationPrepareIn, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    from app.services.school_relation_review_service import SchoolRelationReviewService
    return _write(db, lambda: SchoolRelationReviewService.prepare(db, identity, payload, admin=admin))


@router.post("/{identity}/relation/verify-source", response_model=ApiResponse)
def verify_relation_source(identity: int, payload: SchoolRelationSourceVerifyIn, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    from app.services.school_relation_review_service import SchoolRelationReviewService
    return _write(db, lambda: SchoolRelationReviewService.verify_source(db, identity, payload, admin=admin))


@router.post("/{identity}/relation/review", response_model=ApiResponse)
def review_relation(identity: int, payload: SchoolRelationReviewIn, admin: User = Depends(get_current_admin), db: Session = Depends(get_db),
                    learning_session_id: str | None = Header(None, alias='X-Review-Learning-Session')):
    from app.services.school_relation_review_service import SchoolRelationReviewService
    from app.services.review_telemetry_service import ReviewTelemetryService
    def operation():
        result = SchoolRelationReviewService.review(db, identity, payload, admin=admin)
        if payload.action in {"approve", "reject"}:
            ReviewTelemetryService.complete(db, identity, admin.id, payload.action)
        return result
    return _write(db, operation, learning_admin=admin, learning_session_id=learning_session_id, learning_candidate_id=identity)


@router.get("/{identity}/sources", response_model=ApiResponse)
def sources(identity: int, field_name: str | None = Query(None, max_length=120), limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
            admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    data = FieldReviewService.detail(db, identity, source_limit=None)
    items = [{"field_name": f["field_name"], **entry} for f in data["fields"] if field_name is None or f["field_name"] == field_name for entry in f["timeline"]]
    if data.get("relation") and field_name in {None, "school_relation"}:
        items.append({"field_name": "school_relation", "candidate_id": identity, "source": data["relation"]["source"]})
    return success_response({"items": items[offset:offset+limit], "total": len(items)})


@router.get("/{identity}/audit", response_model=ApiResponse)
def audit(identity: int, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
          admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    items = FieldReviewService.detail(db, identity)["history"]
    return success_response({"items": list(reversed(items))[offset:offset+limit], "total": len(items)})
