"""V0.9 shared data-architecture layer.

Additive tables that complete the four-layer model without touching the
existing competition/edition/source tables:

- organizations / competition_organizations : unified institutional registry
- conference_series / conference_editions / school_conferences : conference
  foundation for the future academic-conference module (schema only, no UI).

The existing school relation tables (competition_policy_recognitions and
university_competition_edition_relations) remain the source of truth for
competition school relations until the school_competitions canonical layer is
built in a later phase.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Organization(Base, TimestampMixin):
    """Unified institutional entity (ministry, committee, society, enterprise...)."""

    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    aliases: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    org_type: Mapped[str] = mapped_column(
        String(60),
        default="other",
        nullable=False,
        index=True,
    )
    country_or_region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    official_website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    official_domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False, index=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    competition_links: Mapped[list["CompetitionOrganization"]] = relationship(
        "CompetitionOrganization",
        back_populates="organization",
        cascade="all, delete-orphan",
    )


class CompetitionOrganization(Base, TimestampMixin):
    """Competition x organization relation with the original display string."""

    __tablename__ = "competition_organizations"
    __table_args__ = (
        UniqueConstraint(
            "competition_id",
            "organization_id",
            "role",
            name="uq_competition_organization_role",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    organization: Mapped[Organization] = relationship(back_populates="competition_links")


class ConferenceSeries(Base, TimestampMixin):
    """Long-lived conference brand (e.g. CVPR, 中国计算机大会)."""

    __tablename__ = "conference_series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    english_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    short_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    aliases: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    discipline: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    secondary_disciplines: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    discipline_evidence: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    subdiscipline: Mapped[str | None] = mapped_column(String(120), nullable=True)
    organizer_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    official_website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    first_held_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conference_frequency: Mapped[str | None] = mapped_column(String(60), nullable=True)
    conference_scope: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_international: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_classifications: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    student_value_tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    audience: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False, index=True)
    authority_status: Mapped[str] = mapped_column(
        String(50),
        default="unverified",
        nullable=False,
        index=True,
    )
    verification_status: Mapped[str] = mapped_column(
        String(50),
        default="unverified",
        nullable=False,
        index=True,
    )
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    risk_flags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    editions: Mapped[list["ConferenceEdition"]] = relationship(
        "ConferenceEdition",
        back_populates="series",
        cascade="all, delete-orphan",
        order_by=lambda: ConferenceEdition.year.desc(),
    )
    sources: Mapped[list["ConferenceSource"]] = relationship(
        "ConferenceSource",
        back_populates="series",
    )
    conference_organizations: Mapped[list["ConferenceOrganization"]] = relationship(
        "ConferenceOrganization",
        back_populates="series",
        cascade="all, delete-orphan",
    )
    school_relations: Mapped[list["SchoolConference"]] = relationship(
        "SchoolConference",
        back_populates="conference_series",
    )


class ConferenceEdition(Base, TimestampMixin):
    """A concrete conference edition (e.g. CVPR 2026)."""

    __tablename__ = "conference_editions"
    __table_args__ = (UniqueConstraint("conference_series_id", "year", name="uq_conference_series_year"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    conference_series_id: Mapped[int] = mapped_column(
        ForeignKey("conference_series.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    edition_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    edition_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country_or_region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    venue: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    online_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    abstract_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paper_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    notification_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    camera_ready_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    registration_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    poster_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    workshop_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    call_for_papers_url: Mapped[str | None] = mapped_column(String(700), nullable=True)
    edition_official_url: Mapped[str | None] = mapped_column(String(700), nullable=True)
    registration_url: Mapped[str | None] = mapped_column(String(700), nullable=True)
    publication_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    publication_status: Mapped[str] = mapped_column(
        String(30),
        default="unknown",
        nullable=False,
        index=True,
    )
    publication_details: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    indexing_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    indexing_claims: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    indexing_claim_status: Mapped[str] = mapped_column(
        String(50),
        default="unknown",
        nullable=False,
        index=True,
    )
    submission_language: Mapped[str | None] = mapped_column(String(80), nullable=True)
    participation_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    student_value_tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    audience: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    participation_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    paper_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    edition_status: Mapped[str] = mapped_column(String(40), default="unknown", nullable=False, index=True)
    authority_status: Mapped[str] = mapped_column(
        String(50),
        default="unverified",
        nullable=False,
        index=True,
    )
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    verification_status: Mapped[str] = mapped_column(
        String(50),
        default="unverified",
        nullable=False,
        index=True,
    )
    risk_flags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    series: Mapped[ConferenceSeries] = relationship(back_populates="editions")
    sources: Mapped[list["ConferenceSource"]] = relationship(
        "ConferenceSource",
        back_populates="edition",
    )
    school_relations: Mapped[list["SchoolConference"]] = relationship(
        "SchoolConference",
        back_populates="conference_edition",
        cascade="all, delete-orphan",
    )
    opportunities: Mapped[list["ConferenceOpportunity"]] = relationship(
        "ConferenceOpportunity",
        back_populates="edition",
        cascade="all, delete-orphan",
    )


class SchoolConference(Base, TimestampMixin):
    """School relation to a conference brand and/or concrete edition."""

    __tablename__ = "school_conferences"
    __table_args__ = (
        UniqueConstraint(
            "school_id",
            "conference_edition_id",
            "notice_url",
            name="uq_school_conference_edition_notice",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    school_id: Mapped[int] = mapped_column(
        ForeignKey("universities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conference_series_id: Mapped[int | None] = mapped_column(
        ForeignKey("conference_series.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    conference_edition_id: Mapped[int | None] = mapped_column(
        ForeignKey("conference_editions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    relation_type: Mapped[str] = mapped_column(String(60), default="other", nullable=False, index=True)
    responsible_department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    responsible_college: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notice_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    campus_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("conference_sources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verification_status: Mapped[str] = mapped_column(
        String(50),
        default="unverified",
        nullable=False,
        index=True,
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    conference_series: Mapped[ConferenceSeries | None] = relationship(back_populates="school_relations")
    conference_edition: Mapped[ConferenceEdition | None] = relationship(back_populates="school_relations")
    source: Mapped["ConferenceSource | None"] = relationship("ConferenceSource")


class SchoolCompetition(Base, TimestampMixin):
    """Canonical school x competition relation (V0.9 semantic refactor).

    One row per (school_id, competition_id). Directory recognition facts and
    edition-level campus notices from the legacy tables are merged here;
    the original rows in competition_policy_recognitions and
    university_competition_edition_relations remain untouched as evidence.
    """

    __tablename__ = "school_competitions"
    __table_args__ = (
        UniqueConstraint("school_id", "competition_id", name="uq_school_competition_pair"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    school_id: Mapped[int] = mapped_column(
        ForeignKey("universities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    competition_edition_id: Mapped[int | None] = mapped_column(
        ForeignKey("competition_editions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Directory-level recognition (school A/B, I/II classes stay here only).
    recognition_status: Mapped[str] = mapped_column(String(60), default="unknown", nullable=False, index=True)
    school_level: Mapped[str | None] = mapped_column(String(120), nullable=True)
    school_category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Participation / campus-notice facts.
    participation_status: Mapped[str] = mapped_column(String(60), default="unknown", nullable=False, index=True)
    responsible_department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    college_id: Mapped[int | None] = mapped_column(
        ForeignKey("colleges.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    responsible_college: Mapped[str | None] = mapped_column(String(255), nullable=True)
    campus_registration_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    campus_registration_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    campus_selection_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notice_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    credit_policy: Mapped[str | None] = mapped_column(Text, nullable=True)
    award_policy: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Proof state: school facts are confirmed by B/C sources; national facts
    # require S/A sources on the Competition/Edition layer.
    record_status: Mapped[str] = mapped_column(
        String(50),
        default="school_confirmed",
        nullable=False,
        index=True,
    )
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    conflict_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    school: Mapped["University"] = relationship("University")
    competition: Mapped["Competition"] = relationship("Competition")
    competition_edition: Mapped["CompetitionEdition | None"] = relationship("CompetitionEdition")
    college: Mapped["College | None"] = relationship("College")
