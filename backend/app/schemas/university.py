from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CollegeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    official_website: str | None = None
    official_domain: str | None = None
    aliases: list[str] | None = None
    source_url: str | None = None
    source_hash: str | None = None
    is_verified: bool = False
    is_demo: bool = False


class UniversityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    short_name: str | None = None
    english_name: str | None = None
    aliases: list[str] | None = None
    province: str | None = None
    city: str | None = None
    university_type: str | None = None
    is_985: bool
    is_211: bool
    is_double_first_class: bool
    official_website: str | None = None
    official_domain: str | None = None
    is_demo: bool = False


class UniversityDetail(UniversityRead):
    colleges: list[CollegeRead] = Field(default_factory=list)


class UniversityPolicyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    university_id: int
    policy_name: str
    policy_type: str
    year: int | None = None
    source_url: str | None = None
    official_file_url: str | None = None
    published_at: datetime | None = None
    effective_date: datetime | None = None
    content: str | None = None
    is_verified: bool
    is_demo: bool


class UniversityCompetitionPolicyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    competition_id: int
    competition_name: str
    policy_id: int | None = None
    policy_name: str | None = None
    year: int | None = None
    recognition_status: str
    recognized_level: str | None = None
    recognized_award: str | None = None
    score: float | None = None
    usage_type: str
    notes: str | None = None
    evidence_text: str | None = None
    is_demo: bool
