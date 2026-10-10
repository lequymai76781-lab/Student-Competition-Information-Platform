from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_db
from app.core.responses import ApiResponse, success_response
from app.models import User
from app.schemas.policy import (
    CrawlerJobRead,
    PolicyCoverageSummary,
    PolicyDocumentRead,
    PolicyRecognitionRead,
    PolicyResolutionRead,
    ReviewQueueRead,
)
from app.services.policy_data_service import PolicyDataService

router = APIRouter(tags=["v0.2-policy-data"])
service = PolicyDataService()


@router.get("/v0.2/policies/documents", response_model=ApiResponse[list[PolicyDocumentRead]])
def list_policy_documents(
    university_id: int | None = None,
    scope_type: str | None = Query(default=None, pattern="^(university|college|major)$"),
    policy_type: str | None = None,
    year: int | None = None,
    include_demo: bool = False,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    data = service.list_documents(
        db,
        university_id=university_id,
        scope_type=scope_type,
        policy_type=policy_type,
        year=year,
        include_demo=include_demo,
        limit=limit,
        offset=offset,
    )
    return success_response(data, meta={"limit": limit, "offset": offset})


@router.get("/v0.2/policies/recognitions", response_model=ApiResponse[list[PolicyRecognitionRead]])
def list_policy_recognitions(
    competition_id: int | None = None,
    university_id: int | None = None,
    recognition_status: str | None = Query(
        default=None,
        pattern="^(recognized|explicitly_not_recognized|not_mentioned|insufficient_evidence|conflicting|expired|uncertain)$",
    ),
    include_demo: bool = False,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    data = service.list_recognitions(
        db,
        competition_id=competition_id,
        university_id=university_id,
        recognition_status=recognition_status,
        include_demo=include_demo,
        limit=limit,
        offset=offset,
    )
    return success_response(data, meta={"limit": limit, "offset": offset})


@router.get("/v0.2/policies/resolve", response_model=ApiResponse[PolicyResolutionRead])
def resolve_policy(
    competition_id: int,
    university_id: int,
    college_id: int | None = None,
    major_id: int | None = None,
    year: int | None = None,
    db: Session = Depends(get_db),
) -> dict:
    return success_response(
        service.resolve(
            db,
            competition_id=competition_id,
            university_id=university_id,
            college_id=college_id,
            major_id=major_id,
            year=year,
        )
    )


@router.get("/v0.2/policies/jobs", response_model=ApiResponse[list[CrawlerJobRead]])
def list_crawler_jobs(
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    data = service.list_jobs(db, status=status, limit=limit, offset=offset)
    return success_response(data, meta={"limit": limit, "offset": offset})


@router.get("/v0.2/policies/review-queue", response_model=ApiResponse[list[ReviewQueueRead]])
def list_review_queue(
    status: str = "pending",
    university_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    data = service.list_review_queue(db, status=status, university_id=university_id, limit=limit, offset=offset)
    return success_response(data, meta={"limit": limit, "offset": offset})


@router.get("/v0.2/universities/985-progress", response_model=ApiResponse[PolicyCoverageSummary])
def get_985_progress(db: Session = Depends(get_db)) -> dict:
    return success_response(service.coverage_summary(db))
