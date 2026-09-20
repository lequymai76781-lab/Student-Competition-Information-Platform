from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class UniversityCompetitionDiscoveryProgress(BaseModel):
    university_id: int
    university_name: str
    short_name: str | None = None
    province: str | None = None
    city: str | None = None
    official_domain: str | None = None
    scope: str = "985"
    is_985: bool = False
    is_211: bool = False
    seeded: bool = True
    batch_name: str | None = None
    discovery_status: str = "not_started"
    methods_attempted: list[str] | None = None
    methods_successful: list[str] | None = None
    pages_examined: int = 0
    candidate_articles: int = 0
    pages_searched: int = 0
    competition_leads: int = 0
    matched_competitions: int = 0
    new_competitions: int = 0
    new_editions: int = 0
    official_sources: int = 0
    university_notice_count: int = 0
    college_notice_count: int = 0
    current_registration_count: int = 0
    edition_2026_count: int = 0
    wechat_leads: int = 0
    internal_deadlines: int = 0
    last_crawled_at: datetime | None = None
    reason: str | None = None
    channel_stats: dict[str, Any] = Field(default_factory=dict)


class CompetitionDiscoveryCoverageSummary(BaseModel):
    universities_985_total: int = 39
    universities_985_seeded: int = 0
    scanned_985_count: int = 0
    completed_985_count: int = 0
    completed_with_gaps_985_count: int = 0
    partial_985_count: int = 0
    failed_985_count: int = 0
    blocked_985_count: int = 0
    universities_211_non_985_total: int = 73
    universities_211_non_985_seeded: int = 0
    scanned_211_non_985_count: int = 0
    completed_211_non_985_count: int = 0
    completed_with_gaps_211_non_985_count: int = 0
    partial_211_non_985_count: int = 0
    failed_211_non_985_count: int = 0
    blocked_211_non_985_count: int = 0
    universities_with_leads: int = 0
    universities_with_matched_competitions: int = 0
    universities_with_2026_editions: int = 0
    competition_leads: int = 0
    matched_competitions: int = 0
    new_competitions: int = 0
    new_editions: int = 0
    official_sources: int = 0
    university_notice_count: int = 0
    college_notice_count: int = 0
    current_registration_count: int = 0
    edition_2026_count: int = 0
    wechat_leads: int = 0
    university_relations: int = 0
    internal_deadlines: int = 0
    discovery_methods: dict = Field(default_factory=dict)
    source_distribution: dict[str, int] = Field(default_factory=dict)
    progress_985: list[UniversityCompetitionDiscoveryProgress] = Field(default_factory=list)
    progress_211_non_985: list[UniversityCompetitionDiscoveryProgress] = Field(default_factory=list)
    progress: list[UniversityCompetitionDiscoveryProgress] = Field(default_factory=list)
