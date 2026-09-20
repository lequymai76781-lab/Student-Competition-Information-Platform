from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.responses import ApiResponse, success_response
from app.schemas.recommendation import RecommendationRequest, RecommendationResult
from app.services.recommendation_service import RuleBasedRecommendationService

router = APIRouter(tags=["recommendations"])
service = RuleBasedRecommendationService()


@router.post("/recommendations", response_model=ApiResponse[list[RecommendationResult]])
def create_recommendations(payload: RecommendationRequest, db: Session = Depends(get_db)) -> dict:
    return success_response(service.recommend(db, payload))

