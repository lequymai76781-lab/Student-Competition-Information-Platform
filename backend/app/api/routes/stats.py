from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.responses import ApiResponse, success_response
from app.repositories.stats_repository import StatsRepository
from app.schemas.stats import PlatformStats

router = APIRouter(tags=["stats"])
repository = StatsRepository()


@router.get("/stats", response_model=ApiResponse[PlatformStats])
def get_stats(db: Session = Depends(get_db)) -> dict:
    return success_response(repository.get_platform_stats(db))

