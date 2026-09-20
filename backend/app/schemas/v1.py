from datetime import datetime

from pydantic import BaseModel, Field


class CorrectionIn(BaseModel):
    competition_id: int
    competition_edition_id: int | None = None
    correction_type: str = Field(max_length=60)
    description: str = Field(min_length=3, max_length=4000)
    source_url: str | None = Field(default=None, max_length=1000)
    contact_note: str | None = Field(default=None, max_length=2000)


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
