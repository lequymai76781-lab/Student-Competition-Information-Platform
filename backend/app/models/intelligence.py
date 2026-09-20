from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class CompetitionLead(Base, TimestampMixin):
    __tablename__ = "competition_leads"
    __table_args__ = (
        UniqueConstraint("source_url", "raw_title", name="uq_competition_lead_source_title"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    raw_title: Mapped[str] = mapped_column(String(700), nullable=False, index=True)
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_competition_name: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_platform: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    possible_year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    possible_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    possible_organizer: Mapped[str | None] = mapped_column(String(500), nullable=True)
    classification: Mapped[str] = mapped_column(String(80), default="unknown", nullable=False, index=True)
    review_status: Mapped[str] = mapped_column(
        String(40),
        default="pending",
        nullable=False,
        index=True,
    )
    verification_status: Mapped[str] = mapped_column(String(50), default="unverified", nullable=False, index=True)
    matched_competition_id: Mapped[int | None] = mapped_column(
        ForeignKey("competitions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    matched_edition_id: Mapped[int | None] = mapped_column(
        ForeignKey("competition_editions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    duplicate_of_id: Mapped[int | None] = mapped_column(
        ForeignKey("competition_leads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    needs_review: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)


class UniversityCompetitionDiscoveryReport(Base, TimestampMixin):
    __tablename__ = "university_competition_discovery_reports"
    __table_args__ = (
        UniqueConstraint("university_id", "batch_name", name="uq_university_competition_discovery_report_batch"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    university_id: Mapped[int] = mapped_column(ForeignKey("universities.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), default="not_started", nullable=False, index=True)
    methods_attempted: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    methods_successful: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    pages_examined: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    candidate_articles: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pages_searched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    competition_leads: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matched_competitions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_competitions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_editions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    internal_deadlines: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    official_sources: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    university_notice_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    college_notice_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_registration_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    edition_2026_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    wechat_leads: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_leads: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel_stats: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    university: Mapped["University"] = relationship("University", back_populates="competition_discovery_reports")


class UniversityCompetitionEditionRelation(Base, TimestampMixin):
    __tablename__ = "university_competition_edition_relations"
    __table_args__ = (
        UniqueConstraint(
            "university_id",
            "competition_edition_id",
            "internal_notice_url",
            name="uq_university_competition_edition_notice",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    university_id: Mapped[int] = mapped_column(ForeignKey("universities.id", ondelete="CASCADE"), nullable=False, index=True)
    college_id: Mapped[int | None] = mapped_column(ForeignKey("colleges.id", ondelete="SET NULL"), nullable=True, index=True)
    competition_edition_id: Mapped[int] = mapped_column(
        ForeignKey("competition_editions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_type: Mapped[str] = mapped_column(String(80), default="university_official_notice", nullable=False, index=True)
    source_platform: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notice_type: Mapped[str] = mapped_column(String(80), default="other", nullable=False, index=True)
    notice_title: Mapped[str | None] = mapped_column(String(700), nullable=True)
    internal_notice_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    organizing_department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    internal_contact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    internal_registration_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    internal_registration_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    internal_submission_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    college_registration_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    college_registration_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    college_submission_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    official_registration_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    contact_person: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contact_method: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    verification_status: Mapped[str] = mapped_column(
        String(50),
        default="school_confirmed",
        nullable=False,
        index=True,
    )
    is_verified: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    university: Mapped["University"] = relationship("University", back_populates="competition_edition_relations")
    college: Mapped["College | None"] = relationship("College", back_populates="competition_edition_relations")
    competition_edition: Mapped["CompetitionEdition"] = relationship(
        "CompetitionEdition",
        back_populates="university_relations",
    )


class CompetitionFactSource(Base, TimestampMixin):
    __tablename__ = "competition_fact_sources"
    __table_args__ = (
        UniqueConstraint(
            "competition_id",
            "competition_edition_id",
            "field_name",
            "source_url",
            name="uq_competition_fact_source_field_url",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    competition_edition_id: Mapped[int | None] = mapped_column(
        ForeignKey("competition_editions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    field_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    fact_value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON, nullable=True)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    reliability_tier: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    source_level: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    is_official: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    verification_status: Mapped[str] = mapped_column(String(50), default="unverified", nullable=False, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class CompetitionFactRevision(Base, TimestampMixin):
    __tablename__ = "competition_fact_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    competition_edition_id: Mapped[int | None] = mapped_column(
        ForeignKey("competition_editions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    field_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    old_value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verification_status: Mapped[str] = mapped_column(
        String(50), default="verified_official", nullable=False, index=True
    )


class CandidateFact(Base, TimestampMixin):
    __tablename__ = "candidate_facts"
    __table_args__ = (
        UniqueConstraint("lead_id", "field_name", "source_url", name="uq_candidate_fact_lead_field_url"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    lead_id: Mapped[int | None] = mapped_column(
        ForeignKey("competition_leads.id", ondelete="CASCADE"), nullable=True, index=True
    )
    competition_id: Mapped[int | None] = mapped_column(
        ForeignKey("competitions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    competition_edition_id: Mapped[int | None] = mapped_column(
        ForeignKey("competition_editions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    field_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    candidate_value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON, nullable=True)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    reliability_tier: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    verification_status: Mapped[str] = mapped_column(String(50), default="unverified", nullable=False, index=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    conflict_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
