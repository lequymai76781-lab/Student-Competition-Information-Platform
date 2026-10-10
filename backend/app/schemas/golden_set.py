"""Strict human annotation inputs; provenance and prediction are server-owned."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.source_document_classifier import DOCUMENT_TYPES


class SaveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["annotated", "draft", "skipped"]
    expected_revision: int = Field(ge=0, strict=True)
    note: str = Field(default="", max_length=6000)


class AnnotationIn(SaveIn):
    human_primary_type: str | None = None
    human_secondary_types: list[str] = Field(default_factory=list, max_length=19)
    prediction_exposed: bool = False
    informational_safe: Literal["yes", "no", "unsure"] | None = None

    @model_validator(mode="after")
    def validate_labels(self):
        if self.human_primary_type is not None and self.human_primary_type not in DOCUMENT_TYPES:
            raise ValueError("未知文档类型")
        if self.status == "annotated" and self.human_primary_type is None:
            raise ValueError("完成标注必须选择主类型")
        secondary = self.human_secondary_types
        if (len(secondary) != len(set(secondary)) or self.human_primary_type in secondary
                or any(value not in DOCUMENT_TYPES for value in secondary)):
            raise ValueError("第二类型必须有效、唯一且不包含主类型")
        return self


class AuditIn(SaveIn):
    answers: dict[str, Literal["yes", "no", "unsure"]] = Field(default_factory=dict)


class ExposureIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
