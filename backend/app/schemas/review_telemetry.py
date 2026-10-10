"""Strict inputs for server-clock review measurements, separate from review facts."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

ReviewMode = Literal["human", "automation"]
CandidateId = Annotated[int, Field(strict=True, gt=0)]

class ReviewTelemetryStartIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    mode: ReviewMode
    candidate_ids: list[CandidateId] | None = Field(default=None, min_length=1, max_length=50)

    @model_validator(mode="after")
    def unique_members(self):
        if self.candidate_ids and len(self.candidate_ids) != len(set(self.candidate_ids)):
            raise ValueError("candidate_ids must be unique")
        return self

class ReviewTelemetryEventIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    session_id: str = Field(min_length=1, max_length=80)
    event: Literal["source_open", "decision", "submit"]
    proposal_id: str | None = Field(default=None, min_length=1, max_length=80)
    field_name: str | None = Field(default=None, min_length=1, max_length=120)
    decision: Literal["approve", "reject", "defer"] | None = None

    @model_validator(mode="after")
    def event_payload(self):
        if self.event == "decision" and self.decision is None:
            raise ValueError("decision events require a decision")
        if self.event != "decision" and self.decision is not None:
            raise ValueError("only decision events accept a decision")
        if self.event == "submit" and (self.proposal_id or self.field_name):
            raise ValueError("submit belongs to the whole session")
        return self
