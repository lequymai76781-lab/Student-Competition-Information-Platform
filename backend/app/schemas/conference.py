"""Academic Conference V1 read schemas (basic internal APIs, no frontend)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.common import TimestampedSchema


class DisciplineRead(BaseModel):
    code: str
    name_en: str
    name_zh: str


class ConferenceOrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    display_name: str | None = None
    is_verified: bool
    source_url: str | None = None
    organization_name: str | None = None
    official_domain: str | None = None


class ConferenceSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conference_series_id: int | None = None
    conference_edition_id: int | None = None
    source_type: str
    authority_level: str | None = None
    source_name: str | None = None
    source_url: str
    source_platform: str | None = None
    official_domain: str | None = None
    document_name: str | None = None
    published_at: datetime | None = None
    retrieved_at: datetime | None = None
    is_official: bool
    is_verified: bool
    verification_status: str = "unverified"
    raw_title: str | None = None
    metadata_json: dict | None = None
    notes: str | None = None


class ConferenceEditionRead(TimestampedSchema):
    id: int
    conference_series_id: int
    series_name: str | None = None
    year: int
    edition_name: str | None = None
    edition_number: int | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    location: str | None = None
    country_or_region: str | None = None
    city: str | None = None
    venue: str | None = None
    notes: str | None = None
    online_status: str | None = None
    abstract_deadline: datetime | None = None
    paper_deadline: datetime | None = None
    notification_date: datetime | None = None
    camera_ready_deadline: datetime | None = None
    registration_deadline: datetime | None = None
    poster_deadline: datetime | None = None
    workshop_deadline: datetime | None = None
    call_for_papers_url: str | None = None
    edition_official_url: str | None = None
    registration_url: str | None = None
    publication_info: str | None = None
    publication_status: str = "unknown"
    publication_details: list[dict] | None = None
    indexing_info: str | None = None
    indexing_claims: list[dict] | None = None
    indexing_claim_status: str = "unknown"
    submission_language: str | None = None
    participation_type: str | None = None
    student_value_tags: list[str] | None = None
    audience: list[str] | None = None
    participation_details: dict | None = None
    paper_details: dict | None = None
    edition_status: str = "unknown"
    authority_status: str = "unverified"
    verification_status: str = "unverified"
    is_verified: bool = False
    risk_flags: list[str] | None = None
    needs_review: bool = False
    last_verified_at: datetime | None = None
    source_url: str | None = None


class ConferenceSeriesRead(TimestampedSchema):
    id: int
    name: str
    english_name: str | None = None
    short_name: str | None = None
    aliases: list[str] | None = None
    discipline: str | None = None
    subdiscipline: str | None = None
    organizer_summary: str | None = None
    official_website: str | None = None
    first_held_year: int | None = None
    conference_frequency: str | None = None
    conference_scope: str | None = None
    is_international: bool = False
    description: str | None = None
    external_classifications: list[dict] | None = None
    recognition: list[dict] | None = None
    student_value_tags: list[str] | None = None
    audience: list[str] | None = None
    status: str = "active"
    authority_status: str = "unverified"
    verification_status: str = "unverified"
    is_verified: bool = False
    risk_flags: list[str] | None = None
    needs_review: bool = False
    last_verified_at: datetime | None = None


class ConferenceSeriesListItem(ConferenceSeriesRead):
    edition_count: int = 0
    official_source_count: int = 0
    latest_edition_year: int | None = None


class ConferenceSeriesDetail(ConferenceSeriesRead):
    editions: list[ConferenceEditionRead] = []
    organizations: list[ConferenceOrganizationRead] = []
    sources: list[ConferenceSourceRead] = []
    school_relation_count: int = 0


class SchoolConferenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    school_id: int
    school_name: str | None = None
    conference_series_id: int | None = None
    series_name: str | None = None
    conference_edition_id: int | None = None
    edition_name: str | None = None
    edition_year: int | None = None
    relation_type: str = "other"
    responsible_department: str | None = None
    responsible_college: str | None = None
    notice_url: str | None = None
    campus_deadline: datetime | None = None
    notes: str | None = None
    source_id: int | None = None
    is_verified: bool = False
    verification_status: str = "unverified"
    verified_at: datetime | None = None
    created_at: datetime | None = None


class ConferenceDiscoveryCandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    raw_name: str
    year: int | None = None
    acronym: str | None = None
    english_name: str | None = None
    organizer_hint: str | None = None
    discipline_hint: str | None = None
    source_type: str
    source_name: str | None = None
    source_url: str
    source_domain: str | None = None
    status: str = "pending"
    matched_series_id: int | None = None
    matched_edition_id: int | None = None
    duplicate_of_id: int | None = None
    needs_review: bool = False
    risk_flags: list[str] | None = None
    rejection_reason: str | None = None
    notes: str | None = None
    discovered_at: datetime
    reviewed_at: datetime | None = None
    review_notes: str | None = None
    entity_type: str = "conference_series"
    metadata_json: dict | None = None


class ConferenceOpportunityRead(TimestampedSchema):
    id: int
    conference_edition_id: int
    series_id: int | None = None
    series_name: str | None = None
    year: int | None = None
    opportunity_type: str
    title: str | None = None
    official_label: str | None = None
    description: str | None = None
    audience: list[str] | None = None
    open_date: datetime | None = None
    deadline: datetime | None = None
    participation_mode: str | None = None
    official_url: str | None = None
    source_id: int | None = None
    evidence: str | None = None
    evidence_status: str = "pending_evidence"
    verification_status: str = "unverified"
    is_verified: bool = False
    risk_flags: list[str] | None = None
    needs_review: bool = False
    notes: str | None = None
    status: str = "unknown"
    last_verified_at: datetime | None = None
    status_hint: str | None = None


class ConferenceDisciplineMappingRead(TimestampedSchema):
    id: int
    major_alias: str
    discipline: str
    relationship_type: str = "direct"
    mapping_basis: str | None = None
    evidence: str | None = None
    source_url: str | None = None
    status: str = "active"


class ConferenceCatalogStats(BaseModel):
    series_total: int
    editions_total: int
    sources_total: int
    candidates_total: int
    school_relations_total: int
    disciplines: list[DisciplineRead]
