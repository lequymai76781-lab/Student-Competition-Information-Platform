from pydantic import BaseModel, Field


class RecommendationRequest(BaseModel):
    university_id: int | None = None
    college_id: int | None = None
    major_id: int | None = None
    major_name: str | None = None
    grade: str | None = None
    goal: str | None = None
    skills: list[str] = Field(default_factory=list)
    interest_tags: list[str] = Field(default_factory=list)
    weekly_available_hours: int | None = None
    preferred_team_type: str | None = None
    preferred_competition_level: str | None = None
    accept_cross_major: bool = True
    accept_cross_university: bool = True
    limit: int = Field(default=8, ge=1, le=30)


class RecommendationResult(BaseModel):
    competition_id: int
    competition_name: str
    score: float
    matched_factors: list[str]
    unmatched_factors: list[str]
    recommendation_reason: str

