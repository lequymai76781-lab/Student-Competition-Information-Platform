"""Strict inputs for independent school relation review; no entity-type conversion."""
from datetime import datetime
from typing import Literal
from pydantic import Field, field_validator, model_validator
from app.schemas.field_review import StrictInput


class SchoolRelationSourceVerifyIn(StrictInput):
    preview_token: str = Field(min_length=1, max_length=128)
    note: str = Field(min_length=1, max_length=3000)


class SchoolRelationPrepareIn(SchoolRelationSourceVerifyIn):
    university_id: int | None = Field(default=None, gt=0)
    competition_id: int | None = Field(default=None, gt=0)
    identity_evidence: str | None = Field(default=None, min_length=1, max_length=3000)
    year: int | None = Field(default=None, ge=1900, le=2200)
    edition_id: int | None = Field(default=None, gt=0)
    scope_type: Literal["university", "college", "major"] | None = None
    college_id: int | None = Field(default=None, gt=0)
    major_id: int | None = Field(default=None, gt=0)
    student_scope: Literal["undergraduate", "graduate", "all", "other"] | None = None
    applicability_text: str | None = Field(default=None, min_length=1, max_length=3000)
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    validity_note: str | None = Field(default=None, min_length=1, max_length=3000)
    current_validity_confirmed: bool = False
    recognition_evidence: str | None = Field(default=None, min_length=1, max_length=5000)
    revoked: bool = False

    @field_validator("effective_from", "effective_until")
    @classmethod
    def aware_dates(cls, value):
        if value is not None and value.utcoffset() is None:
            raise ValueError("Effective dates require an explicit timezone")
        return value

    @model_validator(mode="after")
    def ordered_dates(self):
        if self.effective_from and self.effective_until and self.effective_until <= self.effective_from:
            raise ValueError("effective_until must be after effective_from")
        return self


class SchoolRelationReviewIn(SchoolRelationSourceVerifyIn):
    action: Literal["approve", "reject", "defer"]

