from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.tag import TagRead


class CompetitionEditionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    year: int
    edition_name: str | None = None
    host_location: str | None = None
    edition_rules_url: str | None = None
    edition_status: str = "unknown"
    registration_start: datetime | None = None
    registration_deadline: datetime | None = None
    official_registration_deadline: datetime | None = None
    university_registration_deadline: datetime | None = None
    submission_deadline: datetime | None = None
    official_submission_deadline: datetime | None = None
    competition_start: datetime | None = None
    competition_end: datetime | None = None
    official_competition_date: datetime | None = None
    announcement_date: datetime | None = None
    edition_number: int | None = None
    registration_fee: float | None = None
    fee_notes: str | None = None
    official_url: str | None = None
    official_notice_url: str | None = None
    official_registration_url: str | None = None
    source_url: str | None = None
    is_verified: bool = False
    verification_status: str = "unverified"
    last_verified_at: datetime | None = None
    last_seen_at: datetime | None = None
    source_updated_at: datetime | None = None
    next_check_at: datetime | None = None
    freshness_status: str = "unknown"
    status: str
    current_status: str


class CompetitionSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_type: str
    source_name: str | None = None
    source_url: str
    source_repository: str | None = None
    source_file: str | None = None
    source_commit: str | None = None
    source_platform: str | None = None
    published_at: datetime | None = None
    crawled_at: datetime | None = None
    retrieved_at: datetime | None = None
    is_official: bool
    is_verified: bool
    reliability_tier: int = 3
    verification_status: str = "unverified"
    raw_title: str | None = None
    is_demo: bool


class CompetitionFactSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    competition_edition_id: int | None = None
    field_name: str
    fact_value: object | None = None
    source_type: str
    source_name: str | None = None
    source_url: str
    reliability_tier: int
    source_level: str | None = None
    is_official: bool
    verification_status: str
    published_at: datetime | None = None
    observed_at: datetime
    last_verified_at: datetime | None = None
    notes: str | None = None


class CompetitionFactRevisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    competition_edition_id: int | None = None
    field_name: str
    old_value: object | None = None
    new_value: object | None = None
    changed_at: datetime
    source_url: str
    source_name: str | None = None
    verification_status: str = "verified_official"


class UniversityCompetitionNoticeRead(BaseModel):
    id: int
    university_id: int
    university_name: str
    college_id: int | None = None
    college_name: str | None = None
    competition_edition_id: int
    edition_year: int
    edition_name: str | None = None
    source_type: str
    source_name: str | None = None
    source_platform: str | None = None
    notice_type: str = "other"
    notice_title: str | None = None
    internal_notice_url: str
    organizing_department: str | None = None
    internal_contact: str | None = None
    contact_person: str | None = None
    contact_method: str | None = None
    internal_registration_start: datetime | None = None
    internal_registration_deadline: datetime | None = None
    internal_submission_deadline: datetime | None = None
    college_registration_start: datetime | None = None
    college_registration_deadline: datetime | None = None
    college_submission_deadline: datetime | None = None
    official_registration_deadline: datetime | None = None
    published_at: datetime | None = None
    observed_at: datetime
    last_verified_at: datetime | None = None
    verification_status: str
    is_verified: bool


class CompetitionTrackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    track_type: str | None = None
    description: str | None = None
    source_url: str | None = None
    source_name: str | None = None
    reliability_tier: int
    is_official: bool
    verification_status: str


class DetailFactItemRead(BaseModel):
    label: str
    value: str
    source_url: str | None = None
    source_name: str | None = None
    verification_status: str = "verified_official"


class CompetitionHistoryEventRead(BaseModel):
    year: int
    title: str
    description: str | None = None
    source_url: str | None = None
    source_name: str | None = None
    verification_status: str = "verified_official"


class CompetitionProcessStepRead(BaseModel):
    title: str
    description: str | None = None
    source_url: str | None = None
    source_name: str | None = None
    verification_status: str = "verified_official"


class DeadlineResolutionRead(BaseModel):
    official_deadline: datetime | None = None
    official_submission_deadline: datetime | None = None
    university_deadline: datetime | None = None
    college_deadline: datetime | None = None
    effective_deadline: datetime | None = None
    effective_deadline_type: str = "unverified"
    university_id: int | None = None
    university_name: str | None = None
    college_id: int | None = None
    college_name: str | None = None
    notice_id: int | None = None
    notice_title: str | None = None
    notice_type: str | None = None
    source_url: str | None = None
    source_name: str | None = None
    source_level: str | None = None
    last_verified_at: datetime | None = None


class CompetitionBase(BaseModel):
    parent_competition_id: int | None = None
    name: str = Field(min_length=1, max_length=255)
    short_name: str | None = None
    english_name: str | None = None
    description: str | None = None
    organizer: str | None = None
    official_website: str | None = None
    category: str | None = None
    competition_level: str | None = None
    team_type: str | None = None
    min_team_size: int | None = None
    max_team_size: int | None = None
    difficulty_level: str | None = None
    target_students: str | None = None
    recommended_grade: str | None = None
    competition_type: str = "competition"
    typical_schedule: str | None = None
    is_official_verified: bool = False
    status: str = "active"
    is_cross_major_supported: bool = True
    is_cross_university_supported: bool = False
    is_demo: bool = False


class CompetitionCreate(CompetitionBase):
    tag_ids: list[int] = Field(default_factory=list)


class CompetitionUpdate(BaseModel):
    parent_competition_id: int | None = None
    name: str | None = None
    short_name: str | None = None
    english_name: str | None = None
    description: str | None = None
    organizer: str | None = None
    official_website: str | None = None
    category: str | None = None
    competition_level: str | None = None
    team_type: str | None = None
    min_team_size: int | None = None
    max_team_size: int | None = None
    difficulty_level: str | None = None
    target_students: str | None = None
    recommended_grade: str | None = None
    competition_type: str | None = None
    typical_schedule: str | None = None
    is_official_verified: bool | None = None
    status: str | None = None
    is_cross_major_supported: bool | None = None
    is_cross_university_supported: bool | None = None
    is_demo: bool | None = None
    tag_ids: list[int] | None = None


class FeaturedRecognition(BaseModel):
    university_name: str
    college_name: str | None = None
    recognition_level: str | None = None
    year: int | None = None


class CompetitionHierarchyItem(BaseModel):
    id: int
    name: str
    competition_type: str


class CompetitionListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    short_name: str | None = None
    description: str | None = None
    organizer: str | None = None
    category: str | None = None
    competition_level: str | None = None
    team_type: str | None = None
    difficulty_level: str | None = None
    recommended_grade: str | None = None
    parent_competition_id: int | None = None
    competition_type: str = "competition"
    status: str
    registration_deadline: datetime | None = None
    official_registration_deadline: datetime | None = None
    university_registration_deadline: datetime | None = None
    college_registration_deadline: datetime | None = None
    submission_deadline: datetime | None = None
    official_submission_deadline: datetime | None = None
    action_deadline: datetime | None = None
    action_deadline_label: str | None = None
    effective_deadline: datetime | None = None
    effective_deadline_type: str | None = None
    current_edition_name: str | None = None
    current_edition_id: int | None = None
    registration_closing_soon: bool = False
    current_status: str | None = None
    policy_reference_count: int = 0
    university_inclusion_count: int = 0
    college_inclusion_count: int = 0
    has_college_recognition: bool = False
    official_source_count: int = 0
    source_count: int = 0
    university_source_count: int = 0
    university_notice_count: int = 0
    is_official_verified: bool = False
    verification_status: str = "unverified"
    edition_last_verified_at: datetime | None = None
    edition_source_updated_at: datetime | None = None
    freshness_status: str = "unknown"
    featured_recognition: FeaturedRecognition | None = None
    tags: list[TagRead] = Field(default_factory=list)
    is_demo: bool


class CompetitionDetail(CompetitionListItem):
    english_name: str | None = None
    former_names: list[str] = Field(default_factory=list)
    official_website: str | None = None
    official_account: str | None = None
    founded_year: int | None = None
    first_held_year: int | None = None
    frequency: str | None = None
    edition_count: int | None = None
    co_organizers: list[str] = Field(default_factory=list)
    guiding_organizations: list[str] = Field(default_factory=list)
    undertakers: list[str] = Field(default_factory=list)
    description_source_url: str | None = None
    development_history: str | None = None
    history_timeline: list[CompetitionHistoryEventRead] = Field(default_factory=list)
    participation_requirements: list[DetailFactItemRead] = Field(default_factory=list)
    competition_process: list[CompetitionProcessStepRead] = Field(default_factory=list)
    submission_requirements: list[DetailFactItemRead] = Field(default_factory=list)
    award_settings: list[DetailFactItemRead] = Field(default_factory=list)
    detail_ready: bool = False
    founded_year_candidate: int | None = None
    competition_format: str | None = None
    competition_scope: str | None = None
    country_or_region: str | None = None
    target_students: str | None = None
    min_team_size: int | None = None
    max_team_size: int | None = None
    is_cross_major_supported: bool
    is_cross_university_supported: bool
    typical_schedule: str | None = None
    aliases: list[str] = Field(default_factory=list)
    parent: CompetitionHierarchyItem | None = None
    children: list[CompetitionHierarchyItem] = Field(default_factory=list)
    tracks: list[CompetitionTrackRead] = Field(default_factory=list)
    editions: list[CompetitionEditionRead] = Field(default_factory=list)
    sources: list[CompetitionSourceRead] = Field(default_factory=list)
    fact_sources: list[CompetitionFactSourceRead] = Field(default_factory=list)
    fact_revisions: list[CompetitionFactRevisionRead] = Field(default_factory=list)
    university_notices: list[UniversityCompetitionNoticeRead] = Field(default_factory=list)
    deadline_resolution: DeadlineResolutionRead = Field(default_factory=DeadlineResolutionRead)
    official_verification_status: str = "暂未核实"
    last_verified_at: datetime | None = None
    last_seen_at: datetime | None = None
    updated_at: datetime


class CompetitionRecognitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    university_id: int
    university_name: str
    college_id: int | None = None
    college_name: str | None = None
    policy_document_id: int
    policy_title: str
    source_url: str
    attachment_url: str | None = None
    year: int | None = None
    recognition_status: str
    recognition_level: str | None = None
    award_requirement: str | None = None
    score_text: str | None = None
    score_numeric: float | None = None
    usage_type: str
    evidence_text: str
    evidence_page: int | None = None
    confidence: float
    needs_manual_review: bool
    is_demo: bool
