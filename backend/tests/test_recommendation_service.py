from sqlalchemy.orm import Session

from app.schemas.recommendation import RecommendationRequest
from app.services.recommendation_service import RuleBasedRecommendationService


def test_rule_based_recommendation_service_scores_relevant_competition(db_session: Session) -> None:
    service = RuleBasedRecommendationService()
    request = RecommendationRequest(
        university_id=1,
        major_name="计算机科学与技术",
        grade="大二",
        goal="保研",
        skills=["Python", "AIGC"],
        interest_tags=["计算机"],
        weekly_available_hours=8,
        preferred_team_type="团队赛",
        limit=3,
    )

    results = service.recommend(db_session, request)

    assert results
    assert results[0].competition_name == "测试计算机设计大赛"
    assert results[0].score >= 80
    assert "当前学校政策数据库存在相关认可记录" in results[0].matched_factors
