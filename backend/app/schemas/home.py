from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field


ReadinessStatus = Literal["READY", "PARTIAL", "BLOCKED"]
T = TypeVar("T")


class HomeReadiness(BaseModel):
    status: ReadinessStatus
    shippable: bool
    record_count: int
    verified_count: int
    threshold: int
    reason: str
    last_updated_at: datetime | None = None
    metrics: dict[str, int | str | bool] = Field(default_factory=dict)


class HomeSection(BaseModel, Generic[T]):
    readiness: HomeReadiness
    items: list[T]


class HomeRecognitionItem(BaseModel):
    recognition_id: int
    competition_id: int
    competition_name: str
    university_id: int
    university_name: str
    recognition_level: str | None = None
    usage_type: str
    year: int | None = None
    evidence_title: str
    evidence_url: str
    published_at: datetime | None = None


class HomeDeadlineItem(BaseModel):
    node_id: str
    competition_id: int
    competition_name: str
    edition_id: int
    edition_year: int
    deadline: datetime
    deadline_type: str
    deadline_label: str
    action: Literal["registration", "submission"]
    scope_type: Literal["official", "university", "college"]
    current_status: str
    university_id: int | None = None
    university_name: str | None = None
    college_id: int | None = None
    college_name: str | None = None
    source_url: str
    source_name: str | None = None
    verification_status: str
    last_verified_at: datetime | None = None


class HomeRecentUpdateItem(BaseModel):
    update_key: str
    update_type: str
    entity_type: Literal["competition", "competition_edition"]
    entity_id: int
    changed_fields: list[str]
    competition_id: int
    competition_name: str
    edition_id: int | None = None
    edition_year: int | None = None
    title: str
    field_name: str
    old_value: Any = None
    new_value: Any = None
    occurred_at: datetime
    source_url: str
    source_name: str | None = None
    verification_status: str


class HomeConferenceItem(BaseModel):
    series_id: int
    series_name: str
    short_name: str | None = None
    edition_id: int
    edition_name: str | None = None
    edition_year: int
    start_date: datetime
    end_date: datetime | None = None
    location: str | None = None
    discipline: str | None = None
    is_international: bool
    edition_status: str
    official_url: str
    verification_status: str
    last_verified_at: datetime | None = None


class HomeDataRead(BaseModel):
    as_of: datetime
    decision: Literal["FRONTEND_READY", "FRONTEND_NOT_READY"]
    frontend_ready: bool
    blockers: list[str]
    current_recognitions: HomeSection[HomeRecognitionItem]
    open_registrations: HomeSection[HomeDeadlineItem]
    upcoming_deadlines: HomeSection[HomeDeadlineItem]
    recent_updates: HomeSection[HomeRecentUpdateItem]
    conferences: HomeSection[HomeConferenceItem]
