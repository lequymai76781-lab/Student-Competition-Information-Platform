from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, utc_now


class CompetitionTag(Base):
    __tablename__ = "competition_tags"

    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Tag(Base, TimestampMixin):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)

    competitions: Mapped[list["Competition"]] = relationship(
        "Competition",
        secondary="competition_tags",
        back_populates="tags",
    )


class Competition(Base, TimestampMixin):
    __tablename__ = "competitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    parent_competition_id: Mapped[int | None] = mapped_column(
        ForeignKey("competitions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    short_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    english_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    former_names: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    organizer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    co_organizers: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    guiding_organizations: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    undertakers: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    official_website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    official_account: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description_source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    founded_year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    founded_year_candidate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_held_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frequency: Mapped[str | None] = mapped_column(String(80), nullable=True)
    edition_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    development_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    history_timeline: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    participation_requirements: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    competition_process: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    submission_requirements: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    award_settings: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    competition_format: Mapped[str | None] = mapped_column(String(120), nullable=True)
    competition_scope: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country_or_region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    category: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    competition_level: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    team_type: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    min_team_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_team_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    difficulty_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_students: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_grade: Mapped[str | None] = mapped_column(String(120), nullable=True)
    competition_type: Mapped[str] = mapped_column(String(30), default="competition", nullable=False, index=True)
    typical_schedule: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_completeness_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, index=True)
    crawl_priority: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, index=True)
    detail_ready: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_official_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_competition: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), default="competition", nullable=False, index=True)
    verification_status: Mapped[str] = mapped_column(String(50), default="unverified", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False, index=True)
    is_cross_major_supported: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_cross_university_supported: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    parent: Mapped["Competition | None"] = relationship(
        "Competition",
        remote_side="Competition.id",
        back_populates="children",
    )
    children: Mapped[list["Competition"]] = relationship(
        "Competition",
        back_populates="parent",
    )

    editions: Mapped[list["CompetitionEdition"]] = relationship(
        back_populates="competition",
        cascade="all, delete-orphan",
        order_by=lambda: CompetitionEdition.year.desc(),
    )
    sources: Mapped[list["CompetitionSource"]] = relationship(
        back_populates="competition",
        cascade="all, delete-orphan",
    )
    tags: Mapped[list[Tag]] = relationship(
        "Tag",
        secondary="competition_tags",
        back_populates="competitions",
    )
    university_policies: Mapped[list["UniversityCompetitionPolicy"]] = relationship(
        "UniversityCompetitionPolicy",
        back_populates="competition",
        cascade="all, delete-orphan",
    )
    aliases: Mapped[list["CompetitionAlias"]] = relationship(
        "CompetitionAlias",
        back_populates="competition",
        cascade="all, delete-orphan",
    )
    policy_recognitions: Mapped[list["CompetitionPolicyRecognition"]] = relationship(
        "CompetitionPolicyRecognition",
        back_populates="competition",
        cascade="all, delete-orphan",
    )
    policy_candidates: Mapped[list["CandidateCompetition"]] = relationship(
        "CandidateCompetition",
        back_populates="normalized_competition",
    )
    statistics: Mapped["CompetitionStatistics | None"] = relationship(
        "CompetitionStatistics",
        back_populates="competition",
        uselist=False,
        cascade="all, delete-orphan",
    )
    tracks: Mapped[list["CompetitionTrack"]] = relationship(
        "CompetitionTrack",
        back_populates="competition",
        cascade="all, delete-orphan",
        order_by=lambda: (CompetitionTrack.order_index, CompetitionTrack.id),
    )


class CompetitionEdition(Base, TimestampMixin):
    __tablename__ = "competition_editions"
    __table_args__ = (UniqueConstraint("competition_id", "year", name="uq_competition_edition_year"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    edition_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    host_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    edition_rules_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    edition_status: Mapped[str] = mapped_column(String(40), default="unknown", nullable=False, index=True)
    registration_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    registration_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    official_registration_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    university_registration_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    submission_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    official_submission_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    competition_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    competition_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    official_competition_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    announcement_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    edition_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    registration_fee: Mapped[float | None] = mapped_column(Float, nullable=True)
    fee_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    official_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    official_notice_url: Mapped[str | None] = mapped_column(String(700), nullable=True)
    official_registration_url: Mapped[str | None] = mapped_column(String(700), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(700), nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    verification_status: Mapped[str] = mapped_column(String(50), default="unverified", nullable=False, index=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    freshness_status: Mapped[str] = mapped_column(String(30), default="unknown", nullable=False, index=True)
    source_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    current_status: Mapped[str] = mapped_column(String(50), default="unknown", nullable=False, index=True)

    competition: Mapped[Competition] = relationship(back_populates="editions")
    sources: Mapped[list["CompetitionSource"]] = relationship(back_populates="competition_edition")
    university_relations: Mapped[list["UniversityCompetitionEditionRelation"]] = relationship(
        "UniversityCompetitionEditionRelation",
        back_populates="competition_edition",
        cascade="all, delete-orphan",
    )


class CompetitionSource(Base, TimestampMixin):
    __tablename__ = "competition_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    competition_id: Mapped[int | None] = mapped_column(ForeignKey("competitions.id", ondelete="CASCADE"), nullable=True)
    competition_edition_id: Mapped[int | None] = mapped_column(
        ForeignKey("competition_editions.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    authority_level: Mapped[str | None] = mapped_column(String(4), nullable=True, index=True)
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str] = mapped_column(String(700), nullable=False)
    source_repository: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source_file: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_commit: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_platform: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_official: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    credibility_score: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    reliability_tier: Mapped[int] = mapped_column(Integer, default=3, nullable=False, index=True)
    verification_status: Mapped[str] = mapped_column(String(50), default="unverified", nullable=False, index=True)
    raw_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    competition: Mapped[Competition | None] = relationship(back_populates="sources")
    competition_edition: Mapped[CompetitionEdition | None] = relationship(back_populates="sources")


class CompetitionTrack(Base, TimestampMixin):
    __tablename__ = "competition_tracks"
    __table_args__ = (UniqueConstraint("competition_id", "name", name="uq_competition_track_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    track_type: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reliability_tier: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    is_official: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verification_status: Mapped[str] = mapped_column(String(50), default="secondary_source_only", nullable=False, index=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    competition: Mapped[Competition] = relationship("Competition", back_populates="tracks")
