"""Academic Conference V1 evidence/discovery models (additive).

Kept separate from the competition module. These tables share only the
organizations registry and universities for relations; identity proof follows
conference-specific S/A/B/C rules (see conference_authority_service).
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, utc_now


class ConferenceSource(Base, TimestampMixin):
    """Evidence source attached to a conference series and/or an edition."""

    __tablename__ = "conference_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
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
    source_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    authority_level: Mapped[str | None] = mapped_column(String(4), nullable=True, index=True)
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_platform: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    official_domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    document_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_official: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    verification_status: Mapped[str] = mapped_column(
        String(50),
        default="unverified",
        nullable=False,
        index=True,
    )
    raw_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    series: Mapped["ConferenceSeries | None"] = relationship(
        "ConferenceSeries",
        back_populates="sources",
    )
    edition: Mapped["ConferenceEdition | None"] = relationship(
        "ConferenceEdition",
        back_populates="sources",
    )


class ConferenceOrganization(Base, TimestampMixin):
    """Official institutional relation of a conference series (organizations shared)."""

    __tablename__ = "conference_organizations"
    __table_args__ = (
        UniqueConstraint(
            "conference_series_id",
            "organization_id",
            "role",
            name="uq_conference_organization_role",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    conference_series_id: Mapped[int] = mapped_column(
        ForeignKey("conference_series.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    series: Mapped["ConferenceSeries"] = relationship(
        "ConferenceSeries",
        back_populates="conference_organizations",
    )
    organization: Mapped["Organization"] = relationship("Organization")


class ConferenceDiscoveryCandidate(Base, TimestampMixin):
    """Discovery pool: noisy finds that are not yet formal conference series."""

    __tablename__ = "conference_discovery_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    raw_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    acronym: Mapped[str | None] = mapped_column(String(120), nullable=True)
    english_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    organizer_hint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    discipline_hint: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(40),
        default="pending",
        nullable=False,
        index=True,
    )
    matched_series_id: Mapped[int | None] = mapped_column(
        ForeignKey("conference_series.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    matched_edition_id: Mapped[int | None] = mapped_column(
        ForeignKey("conference_editions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    duplicate_of_id: Mapped[int | None] = mapped_column(
        ForeignKey("conference_discovery_candidates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    risk_flags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_type: Mapped[str] = mapped_column(
        String(60),
        default="conference_series",
        nullable=False,
        index=True,
    )
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class ConferenceOpportunity(Base, TimestampMixin):
    """A concrete student opportunity of one ConferenceEdition.

    One Edition may have several opportunities (paper submission, poster,
    doctoral consortium, student forum, travel grant...), each with its own
    audience, deadline(s), official URL and evidence. The Edition keeps only
    conference-level dates; opportunity states are derived from real dates and
    are never copied across Editions or Series.
    """

    __tablename__ = "conference_opportunities"
    __table_args__ = (
        UniqueConstraint(
            "conference_edition_id",
            "opportunity_type",
            "official_url",
            name="uq_conference_opportunity_edition_type_url",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    conference_edition_id: Mapped[int] = mapped_column(
        ForeignKey("conference_editions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    opportunity_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    official_label: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    audience: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    open_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    participation_mode: Mapped[str | None] = mapped_column(String(60), nullable=True)
    official_url: Mapped[str | None] = mapped_column(String(700), nullable=True, index=True)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("conference_sources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_status: Mapped[str] = mapped_column(
        String(50),
        default="pending_evidence",
        nullable=False,
        index=True,
    )
    verification_status: Mapped[str] = mapped_column(
        String(50),
        default="unverified",
        nullable=False,
        index=True,
    )
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    risk_flags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    status_hint: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        index=True,
    )

    edition: Mapped["ConferenceEdition"] = relationship(
        "ConferenceEdition",
        back_populates="opportunities",
    )
    source: Mapped["ConferenceSource | None"] = relationship("ConferenceSource")


class ConferenceDisciplineMapping(Base, TimestampMixin):
    """Lightweight major/alias -> conference-discipline vocabulary mapping.

    This maps *professional vocabulary*, not conferences: e.g. 新闻学 is a
    direct alias of Journalism & Communication; 数据新闻 is additionally an
    interdisciplinary alias of Data Science. It is never used as a
    personalised recommendation or a conference-suitability score.
    """

    __tablename__ = "conference_discipline_mappings"
    __table_args__ = (
        UniqueConstraint("major_alias", "discipline", name="uq_discipline_mapping_alias"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    major_alias: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    discipline: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    relationship_type: Mapped[str] = mapped_column(
        String(40),
        default="direct",
        nullable=False,
        index=True,
    )
    mapping_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(700), nullable=True)
    status: Mapped[str] = mapped_column(
        String(40),
        default="active",
        nullable=False,
        index=True,
    )
