from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PolicyDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    university_id: int
    university_name: str | None = None
    college_id: int | None = None
    college_name: str | None = None
    major_id: int | None = None
    major_name: str | None = None
    scope_type: str
    title: str
    policy_type: str
    year: int | None = None
    latest_available_year: int | None = None
    publisher: str | None = None
    source_url: str
    attachment_url: str | None = None
    original_filename: str | None = None
    official_domain: str | None = None
    authority_level: str
    published_at: datetime | None = None
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    content_excerpt: str | None = None
    document_hash: str | None = None
    is_current: bool
    is_verified: bool
    verification_status: str
    crawler_job_id: int | None = None
    parser_type: str | None = None
    source_type: str
    is_demo: bool
    created_at: datetime
    updated_at: datetime


class PolicyRecognitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    competition_id: int
    competition_name: str | None = None
    policy_document_id: int
    policy_title: str | None = None
    university_id: int
    university_name: str | None = None
    college_id: int | None = None
    college_name: str | None = None
    major_id: int | None = None
    major_name: str | None = None
    year: int | None = None
    recognition_status: str
    recognition_level: str | None = None
    award_requirement: str | None = None
    usage_type: str
    score_text: str | None = None
    score_numeric: float | None = None
    rank_requirement: str | None = None
    evidence_text: str
    evidence_page: int | None = None
    evidence_section: str | None = None
    confidence: float
    needs_manual_review: bool
    is_demo: bool
    created_at: datetime
    updated_at: datetime


class CrawlerJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_type: str
    target_type: str
    target_id: int | None = None
    target_name: str | None = None
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    pages_discovered: int
    pages_fetched: int
    documents_found: int
    documents_parsed: int
    competitions_found: int
    errors_count: int
    error_summary: str | None = None
    created_at: datetime
    updated_at: datetime


class ReviewQueueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_type: str
    item_id: int | None = None
    university_id: int | None = None
    university_name: str | None = None
    college_id: int | None = None
    major_id: int | None = None
    policy_document_id: int | None = None
    competition_id: int | None = None
    status: str
    reason: str
    raw_value: str | None = None
    suggested_value: str | None = None
    evidence_text: str | None = None
    source_url: str | None = None
    confidence: float | None = None
    assigned_to: str | None = None
    reviewed_at: datetime | None = None
    reviewer_notes: str | None = None
    is_demo: bool
    created_at: datetime
    updated_at: datetime


class PolicyResolutionRead(BaseModel):
    competition_id: int
    university_id: int
    college_id: int | None = None
    major_id: int | None = None
    year: int | None = None
    effective_status: str
    effective_scope: str
    effective_policy_document_id: int | None = None
    effective_recognition_id: int | None = None
    secondary_policy_document_id: int | None = None
    conflict: bool
    reason: str
    evidence_text: str | None = None
    needs_manual_review: bool


class University985ProgressRead(BaseModel):
    university_id: int
    university_name: str
    short_name: str | None = None
    province: str | None = None
    city: str | None = None
    official_domain: str | None = None
    seeded: bool = True
    college_count: int = 0
    policy_documents_count: int = 0
    verified_policy_documents_count: int = 0
    parsed_policy_documents_count: int = 0
    competition_count: int = 0
    recognition_count: int = 0
    review_pending_count: int = 0
    latest_policy_year: int | None = None
    last_policy_crawl_at: datetime | None = None
    crawl_status: str = "not_started"
    crawl_error: str | None = None


class PolicyCoverageSummary(BaseModel):
    universities_985_total: int = 39
    universities_985_seeded: int = 0
    universities_with_real_policy: int = 0
    real_policy_documents: int = 0
    verified_policy_documents: int = 0
    college_policy_documents: int = 0
    parsed_college_policy_documents: int = 0
    candidate_competitions: int = 0
    competitions: int = 0
    recognitions: int = 0
    review_queue_pending: int = 0
    progress: list[University985ProgressRead] = Field(default_factory=list)
