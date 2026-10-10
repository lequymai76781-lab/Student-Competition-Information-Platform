from pydantic import BaseModel, ConfigDict, Field

class ClassificationCorrectionIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    document_type: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=1, max_length=2000)

class DocumentPolicyActionIn(BaseModel):
    model_config = ConfigDict(extra='forbid')

class PolicyMatchConfirmationIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    raw_competition_name: str = Field(min_length=1, max_length=500)
    competition_id: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=2000)
