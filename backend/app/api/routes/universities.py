from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.responses import ApiResponse, success_response
from app.schemas.university import (
    UniversityCompetitionPolicyRead,
    UniversityDetail,
    UniversityPolicyRead,
    UniversityRead,
)
from app.services.university_service import UniversityService

router = APIRouter(tags=["universities"])
service = UniversityService()


@router.get("/universities", response_model=ApiResponse[list[UniversityRead]])
def list_universities(
    keyword: str | None = None,
    province: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    data = service.list_universities(db, keyword=keyword, province=province, limit=limit, offset=offset)
    return success_response(data, meta={"limit": limit, "offset": offset})


@router.get("/universities/{university_id}", response_model=ApiResponse[UniversityDetail])
def get_university(university_id: int, db: Session = Depends(get_db)) -> dict:
    return success_response(service.get_university(db, university_id))


@router.get("/universities/{university_id}/policies", response_model=ApiResponse[list[UniversityPolicyRead]])
def list_university_policies(
    university_id: int,
    year: int | None = None,
    policy_type: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    return success_response(service.list_policies(db, university_id, year=year, policy_type=policy_type))


@router.get(
    "/universities/{university_id}/competition-policies",
    response_model=ApiResponse[list[UniversityCompetitionPolicyRead]],
)
def list_university_competition_policies(
    university_id: int,
    year: int | None = None,
    usage_type: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    return success_response(service.list_competition_policies(db, university_id, year=year, usage_type=usage_type))

