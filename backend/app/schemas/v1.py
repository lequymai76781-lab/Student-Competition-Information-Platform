from datetime import datetime

from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


def validated_source_url(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("来源须为有效的 HTTP(S) 网页地址")
    return value


class CorrectionIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    competition_id: int
    competition_edition_id: int | None = None
    correction_type: str = Field(max_length=60)
    description: str = Field(min_length=3, max_length=4000)
    source_url: str | None = Field(default=None, max_length=1000)
    contact_note: str | None = Field(default=None, max_length=2000)
    proposed_value: str | None = Field(default=None, min_length=1, max_length=4000)
    _validate_source = field_validator("source_url")(validated_source_url)


class SupplementIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    kind: Literal["competition", "school", "school_notice", "recognition", "history", "other"]
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(min_length=3, max_length=4000)
    source_url: str | None = Field(default=None, max_length=500)
    _validate_source = field_validator("source_url")(validated_source_url)


class SupplementReviewIn(BaseModel):
    status: Literal["verified_pending_import", "rejected", "duplicate", "needs_more_evidence"]
    note: str = Field(min_length=3, max_length=2000)


class FeedbackIn(BaseModel):
    category: str = Field(
        pattern="^(数据错误|找不到比赛|学校信息错误|Deadline问题|使用困难|功能建议|页面问题|其他)$"
    )
    content: str = Field(min_length=3, max_length=4000)
    url: str | None = Field(default=None, max_length=500)


class ReviewActionIn(BaseModel):
    status: str = Field(pattern="^(approved|rejected|duplicate|needs_more_evidence)$")
    note: str | None = None
    new_deadline: datetime | None = None
    competition_edition_id: int | None = None
