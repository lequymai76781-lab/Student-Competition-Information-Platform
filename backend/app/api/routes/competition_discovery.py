from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.responses import ApiResponse, success_response
from app.schemas.competition_discovery import CompetitionDiscoveryCoverageSummary
from app.services.competition_discovery_service import CompetitionDiscoveryService

router = APIRouter(tags=["v0.6-competition-discovery"])
service = CompetitionDiscoveryService()


@router.get(
    "/v0.6/competitions/discovery/985-progress",
    response_model=ApiResponse[CompetitionDiscoveryCoverageSummary],
)
def get_985_competition_discovery_progress(db: Session = Depends(get_db)) -> dict:
    return success_response(service.coverage_summary(db))


@router.get(
    "/v0.8/competitions/discovery/coverage",
    response_model=ApiResponse[CompetitionDiscoveryCoverageSummary],
)
def get_v08_competition_discovery_coverage(db: Session = Depends(get_db)) -> dict:
    return success_response(service.v08_coverage_summary(db))
