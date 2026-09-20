from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class CrawlerJob(Base, TimestampMixin):
    __tablename__ = "crawler_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    target_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pages_discovered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pages_fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    documents_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    documents_parsed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    competitions_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    policy_documents: Mapped[list["PolicyDocument"]] = relationship(back_populates="crawler_job")
    attachments: Mapped[list["PolicyAttachment"]] = relationship(back_populates="crawler_job")


class PolicyDocument(Base, TimestampMixin):
    __tablename__ = "policy_documents"
    __table_args__ = (
        UniqueConstraint("document_hash", name="uq_policy_documents_document_hash"),
        UniqueConstraint("source_url", "attachment_url", name="uq_policy_documents_source_attachment"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    university_id: Mapped[int] = mapped_column(ForeignKey("universities.id", ondelete="CASCADE"), nullable=False, index=True)
    college_id: Mapped[int | None] = mapped_column(ForeignKey("colleges.id", ondelete="SET NULL"), nullable=True, index=True)
    major_id: Mapped[int | None] = mapped_column(ForeignKey("majors.id", ondelete="SET NULL"), nullable=True, index=True)
    scope_type: Mapped[str] = mapped_column(String(30), default="university", nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    policy_type: Mapped[str] = mapped_column(String(80), default="other", nullable=False, index=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    latest_available_year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    attachment_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    official_domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    authority_level: Mapped[str] = mapped_column(String(10), default="A2", nullable=False, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verification_status: Mapped[str] = mapped_column(String(80), default="pending", nullable=False, index=True)
    crawler_job_id: Mapped[int | None] = mapped_column(ForeignKey("crawler_jobs.id", ondelete="SET NULL"), nullable=True)
    parser_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_type: Mapped[str] = mapped_column(String(80), default="university", nullable=False, index=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    university: Mapped["University"] = relationship("University", back_populates="policy_documents")
    college: Mapped["College | None"] = relationship("College", back_populates="policy_documents")
    major: Mapped["Major | None"] = relationship("Major", back_populates="policy_documents")
    crawler_job: Mapped[CrawlerJob | None] = relationship(back_populates="policy_documents")
    attachments: Mapped[list["PolicyAttachment"]] = relationship(back_populates="policy_document")
    recognitions: Mapped[list["CompetitionPolicyRecognition"]] = relationship(
        back_populates="policy_document",
        cascade="all, delete-orphan",
    )
    competition_candidates: Mapped[list["CandidateCompetition"]] = relationship(
        back_populates="policy_document",
        cascade="all, delete-orphan",
    )
    raw_items: Mapped[list["PolicyRawItem"]] = relationship(
        back_populates="policy_document",
        cascade="all, delete-orphan",
    )


class PolicyRawItem(Base, TimestampMixin):
    __tablename__ = "policy_raw_items"
    __table_args__ = (
        UniqueConstraint("policy_document_id", "raw_order", "raw_name", name="uq_policy_raw_item_order_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    policy_document_id: Mapped[int] = mapped_column(
        ForeignKey("policy_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    raw_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    raw_level: Mapped[str | None] = mapped_column(String(120), nullable=True)
    raw_order: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), default="unknown", nullable=False, index=True)
    normalized_competition_id: Mapped[int | None] = mapped_column(
        ForeignKey("competitions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    needs_manual_review: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    classification_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    policy_document: Mapped[PolicyDocument] = relationship(back_populates="raw_items")


class PolicyAttachment(Base, TimestampMixin):
    __tablename__ = "policy_attachments"
    __table_args__ = (
        UniqueConstraint("source_url", name="uq_policy_attachments_source_url"),
        UniqueConstraint("file_hash", name="uq_policy_attachments_file_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    policy_document_id: Mapped[int | None] = mapped_column(ForeignKey("policy_documents.id", ondelete="SET NULL"), nullable=True)
    crawler_job_id: Mapped[int | None] = mapped_column(ForeignKey("crawler_jobs.id", ondelete="SET NULL"), nullable=True)
    university_id: Mapped[int | None] = mapped_column(ForeignKey("universities.id", ondelete="SET NULL"), nullable=True, index=True)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    file_extension: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    file_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parse_status: Mapped[str] = mapped_column(String(60), default="pending", nullable=False, index=True)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    text_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    policy_document: Mapped[PolicyDocument | None] = relationship(back_populates="attachments")
    crawler_job: Mapped[CrawlerJob | None] = relationship(back_populates="attachments")


class CompetitionAlias(Base, TimestampMixin):
    __tablename__ = "competition_aliases"
    __table_args__ = (UniqueConstraint("competition_id", "alias", name="uq_competition_alias_competition_alias"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    alias: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    normalized_alias: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(80), default="manual", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    competition: Mapped["Competition"] = relationship("Competition", back_populates="aliases")


class CandidateCompetition(Base, TimestampMixin):
    __tablename__ = "candidate_competitions"
    __table_args__ = (
        UniqueConstraint(
            "policy_document_id",
            "table_row",
            "raw_name",
            name="uq_candidate_competition_document_row_name",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    policy_document_id: Mapped[int] = mapped_column(
        ForeignKey("policy_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    university_id: Mapped[int] = mapped_column(
        ForeignKey("universities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    college_id: Mapped[int | None] = mapped_column(
        ForeignKey("colleges.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    raw_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    raw_category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_level: Mapped[str | None] = mapped_column(String(120), nullable=True)
    raw_award: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_score: Mapped[str | None] = mapped_column(String(255), nullable=True)
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    table_row: Mapped[str | None] = mapped_column(String(120), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, index=True)
    normalization_status: Mapped[str] = mapped_column(
        String(60),
        default="pending",
        nullable=False,
        index=True,
    )
    normalized_competition_id: Mapped[int | None] = mapped_column(
        ForeignKey("competitions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    needs_manual_review: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    policy_document: Mapped[PolicyDocument] = relationship(back_populates="competition_candidates")
    university: Mapped["University"] = relationship("University", back_populates="competition_candidates")
    college: Mapped["College | None"] = relationship("College", back_populates="competition_candidates")
    normalized_competition: Mapped["Competition | None"] = relationship(
        "Competition",
        back_populates="policy_candidates",
    )


class CompetitionPolicyRecognition(Base, TimestampMixin):
    __tablename__ = "competition_policy_recognitions"
    __table_args__ = (
        UniqueConstraint(
            "policy_document_id",
            "competition_id",
            "usage_type",
            "evidence_hash",
            name="uq_competition_policy_recognition_evidence",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    policy_document_id: Mapped[int] = mapped_column(ForeignKey("policy_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    university_id: Mapped[int] = mapped_column(ForeignKey("universities.id", ondelete="CASCADE"), nullable=False, index=True)
    college_id: Mapped[int | None] = mapped_column(ForeignKey("colleges.id", ondelete="SET NULL"), nullable=True, index=True)
    major_id: Mapped[int | None] = mapped_column(ForeignKey("majors.id", ondelete="SET NULL"), nullable=True, index=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    recognition_status: Mapped[str] = mapped_column(String(50), default="insufficient_evidence", nullable=False, index=True)
    recognition_level: Mapped[str | None] = mapped_column(String(120), nullable=True)
    award_requirement: Mapped[str | None] = mapped_column(String(255), nullable=True)
    usage_type: Mapped[str] = mapped_column(String(80), default="other", nullable=False, index=True)
    score_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    score_numeric: Mapped[float | None] = mapped_column(Float, nullable=True)
    rank_requirement: Mapped[str | None] = mapped_column(String(255), nullable=True)
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    evidence_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_section: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, index=True)
    needs_manual_review: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    competition: Mapped["Competition"] = relationship("Competition", back_populates="policy_recognitions")
    policy_document: Mapped[PolicyDocument] = relationship(back_populates="recognitions")
    university: Mapped["University"] = relationship("University", back_populates="policy_recognitions")
    college: Mapped["College | None"] = relationship("College", back_populates="policy_recognitions")
    major: Mapped["Major | None"] = relationship("Major", back_populates="policy_recognitions")


class CompetitionStatistics(Base, TimestampMixin):
    __tablename__ = "competition_statistics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id", ondelete="CASCADE"), unique=True, nullable=False)
    university_985_recognition_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    college_985_recognition_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    policy_reference_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latest_policy_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    official_source_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    university_source_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    university_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    college_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    priority_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    score_breakdown: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    competition: Mapped["Competition"] = relationship("Competition", back_populates="statistics")


class ReviewQueue(Base, TimestampMixin):
    __tablename__ = "review_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    item_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    item_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    university_id: Mapped[int | None] = mapped_column(ForeignKey("universities.id", ondelete="SET NULL"), nullable=True, index=True)
    college_id: Mapped[int | None] = mapped_column(ForeignKey("colleges.id", ondelete="SET NULL"), nullable=True, index=True)
    major_id: Mapped[int | None] = mapped_column(ForeignKey("majors.id", ondelete="SET NULL"), nullable=True, index=True)
    policy_document_id: Mapped[int | None] = mapped_column(ForeignKey("policy_documents.id", ondelete="SET NULL"), nullable=True, index=True)
    competition_id: Mapped[int | None] = mapped_column(ForeignKey("competitions.id", ondelete="SET NULL"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(60), default="pending", nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
