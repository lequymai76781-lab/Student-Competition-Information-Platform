from pydantic import BaseModel, Field


class PlatformStats(BaseModel):
    competitions: int
    universities: int
    policies: int
    recognitions: int
    tags: int
    universities_985_total: int = 39
    universities_985_seeded: int = 0
    real_policy_documents: int = 0
    verified_policy_documents: int = 0
    college_policy_documents: int = 0
    review_queue_pending: int = 0
    universities_with_real_policy: int = 0
    candidate_competitions: int = 0
    editions: int = 0
    verified_editions: int = 0
    registration_open: int = 0
    submission_open: int = 0
    tagged_competitions: int = 0
    github_seed_sources: int = 0
    competition_leads: int = 0
    github_discovery_leads: int = 0
    university_official_leads: int = 0
    third_party_platform_leads: int = 0
    wechat_leads: int = 0
    social_leads: int = 0
    universities_crawled: int = 0
    competition_discovery_scanned_985: int = 0
    competition_discovery_completed_985: int = 0
    competition_discovery_partial_985: int = 0
    competition_discovery_failed_985: int = 0
    competition_discovery_blocked_985: int = 0
    universities_with_competition_leads: int = 0
    universities_with_competitions: int = 0
    universities_with_2026_editions: int = 0
    university_competition_notices: int = 0
    college_competition_notices: int = 0
    internal_deadline_count: int = 0
    official_registration_deadline_count: int = 0
    registration_notice_count: int = 0
    internal_selection_count: int = 0
    submission_notice_count: int = 0
    non_action_notice_count: int = 0
    competitions_with_description: int = 0
    competitions_with_organizer: int = 0
    competitions_with_official_website: int = 0
    competitions_with_founded_year: int = 0
    field_fact_sources: int = 0
    detail_ready_competitions: int = 0
    competitions_with_history_timeline: int = 0
    competitions_with_participation_requirements: int = 0
    competitions_with_competition_process: int = 0
    competitions_with_submission_requirements: int = 0
    competitions_with_award_settings: int = 0
    editions_with_fee_information: int = 0
    policy_raw_items: int = 0
    verified_official_competitions: int = 0
    verified_multi_source_competitions: int = 0
    secondary_source_only_competitions: int = 0
    source_distribution: dict[str, int] = Field(default_factory=dict)
    demo_data: bool
