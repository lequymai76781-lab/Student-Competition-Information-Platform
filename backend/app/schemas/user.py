from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RegisterIn(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=6, max_length=128)
    invite_code: str | None = None


class LoginIn(BaseModel):
    email: str
    password: str


class ProfileUpdateIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    university_id: int | None = None
    university_name: str | None = None
    college_id: int | None = None
    college_name: str | None = None
    major_id: int | None = None
    major_name: str | None = None
    grade: str | None = None
    graduation_year: int | None = None
    interest_tags: list[str] | None = None
    skills: list[str] | None = None
    preferred_team_type: str | None = None
    preferred_competition_categories: list[str] | None = None
    weekly_available_hours: int | None = None
    accept_cross_major: bool | None = None
    accept_cross_university: bool | None = None


class StatusUpdateIn(BaseModel):
    status: str = Field(pattern="^(interested|planning|registered|participating|finished|abandoned)$")
    notes: str | None = None


class FavoriteIn(BaseModel):
    competition_id: int
