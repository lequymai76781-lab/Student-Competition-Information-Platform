"""Inputs for the candidate-only, administrator-reviewed fact workflow."""
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


SourceType = Literal[
    "official_website", "organizer_notice", "government_document", "university_notice",
    "university_policy", "industry_organization", "user_submission", "third_party",
    "ai_assisted", "crawler", "manual_entry",
]


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FieldSourceIn(StrictInput):
    source_type: SourceType
    source_title: str | None = Field(default=None, max_length=255)
    source_url: str | None = Field(default=None, max_length=1000)
    publisher: str | None = Field(default=None, max_length=255)
    published_at: datetime | None = None

    @field_validator("source_url")
    @classmethod
    def source_url_is_http(cls, value):
        if value is None or not value.strip():
            return None
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("来源链接必须为无凭据的 HTTP(S) 地址")
        return value


class FieldProposalIn(StrictInput):
    field_name: str = Field(min_length=1, max_length=120)
    candidate_value: Any
    source: FieldSourceIn | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class StructuredFactIn(StrictInput):
    """Only content and optional reference links; provenance is server-owned."""
    source_url: str | None = Field(default=None, max_length=1000)
    source_name: str | None = Field(default=None, max_length=255)

    @field_validator("source_url")
    @classmethod
    def validate_reference(cls, value):
        return FieldSourceIn.source_url_is_http(value)


class FieldHistoryItemIn(StructuredFactIn):
    year: int = Field(strict=True, ge=1000, le=2200)
    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=10000)


class FieldProcessItemIn(StructuredFactIn):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=10000)


class FieldDetailItemIn(StructuredFactIn):
    label: str = Field(min_length=1, max_length=500)
    value: str = Field(min_length=1, max_length=10000)


class FieldCandidateIn(StrictInput):
    entity_type: Literal["competition", "edition"]
    competition_id: int | None = Field(default=None, gt=0)
    edition_id: int | None = Field(default=None, gt=0)
    year: int | None = Field(default=None, ge=1900, le=2200)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=30000)
    university_id: int | None = Field(default=None, gt=0)
    origin: Literal["manual_entry", "crawler", "ai_assisted", "user_submission"] = "manual_entry"
    origin_id: int | None = Field(default=None, gt=0)
    origin_kind: Literal["user_correction", "user_supplement"] | None = None
    fields: list[FieldProposalIn] = Field(default_factory=list, max_length=100)


class FieldPrepareIn(FieldCandidateIn):
    preview_token: str = Field(min_length=1, max_length=128)


class FieldSourceVerifyIn(StrictInput):
    preview_token: str = Field(min_length=1, max_length=128)
    note: str = Field(min_length=1, max_length=5000)


class FieldDecisionIn(StrictInput):
    field_name: str = Field(min_length=1, max_length=120)
    action: Literal["approve", "reject", "defer"]
    proposal_id: str | None = Field(default=None, max_length=80)
    confirm_delete: bool = False


class FieldReviewIn(FieldSourceVerifyIn):
    decisions: list[FieldDecisionIn] = Field(min_length=1, max_length=100)


class FieldBulkItemIn(StrictInput):
    id: int = Field(gt=0)
    preview_token: str = Field(min_length=1, max_length=128)
    field_names: list[str] = Field(min_length=1, max_length=100)


class FieldBulkReviewIn(StrictInput):
    items: list[FieldBulkItemIn] = Field(min_length=1, max_length=50)
    note: str = Field(min_length=1, max_length=5000)
