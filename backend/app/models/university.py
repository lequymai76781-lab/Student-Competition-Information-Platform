from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class University(Base, TimestampMixin):
    __tablename__ = "universities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    short_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    english_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    aliases: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    province: Mapped[str | None] = mapped_column(String(80), nullable=True)
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    university_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_985: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_211: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_double_first_class: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    official_website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    official_domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    policy_crawl_status: Mapped[str] = mapped_column(
        String(40),
        default="not_started",
        nullable=False,
        index=True,
    )
    policy_crawl_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_policy_crawl_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    policy_crawl_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    competition_discovery_status: Mapped[str] = mapped_column(
        String(40),
        default="not_started",
        nullable=False,
        index=True,
    )
    competition_discovery_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_competition_discovery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    competition_discovery_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    colleges: Mapped[list["College"]] = relationship(back_populates="university", cascade="all, delete-orphan")
    policies: Mapped[list["UniversityPolicy"]] = relationship(back_populates="university", cascade="all, delete-orphan")
    policy_documents: Mapped[list["PolicyDocument"]] = relationship(
        "PolicyDocument",
        back_populates="university",
        cascade="all, delete-orphan",
    )
    policy_recognitions: Mapped[list["CompetitionPolicyRecognition"]] = relationship(
        "CompetitionPolicyRecognition",
        back_populates="university",
    )
    competition_candidates: Mapped[list["CandidateCompetition"]] = relationship(
        "CandidateCompetition",
        back_populates="university",
        cascade="all, delete-orphan",
    )
    competition_policies: Mapped[list["UniversityCompetitionPolicy"]] = relationship(
        back_populates="university",
        cascade="all, delete-orphan",
    )
    competition_discovery_reports: Mapped[list["UniversityCompetitionDiscoveryReport"]] = relationship(
        "UniversityCompetitionDiscoveryReport",
        back_populates="university",
        cascade="all, delete-orphan",
    )
    competition_edition_relations: Mapped[list["UniversityCompetitionEditionRelation"]] = relationship(
        "UniversityCompetitionEditionRelation",
        back_populates="university",
        cascade="all, delete-orphan",
    )


class College(Base, TimestampMixin):
    __tablename__ = "colleges"
    __table_args__ = (UniqueConstraint("university_id", "name", name="uq_college_university_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    university_id: Mapped[int] = mapped_column(ForeignKey("universities.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    official_website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    official_domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    aliases: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(700), nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    university: Mapped[University] = relationship(back_populates="colleges")
    policy_documents: Mapped[list["PolicyDocument"]] = relationship("PolicyDocument", back_populates="college")
    policy_recognitions: Mapped[list["CompetitionPolicyRecognition"]] = relationship(
        "CompetitionPolicyRecognition",
        back_populates="college",
    )
    competition_candidates: Mapped[list["CandidateCompetition"]] = relationship(
        "CandidateCompetition",
        back_populates="college",
    )
    competition_edition_relations: Mapped[list["UniversityCompetitionEditionRelation"]] = relationship(
        "UniversityCompetitionEditionRelation",
        back_populates="college",
    )


class Major(Base, TimestampMixin):
    __tablename__ = "majors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    discipline_category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    major_category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    aliases: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    policy_documents: Mapped[list["PolicyDocument"]] = relationship("PolicyDocument", back_populates="major")
    policy_recognitions: Mapped[list["CompetitionPolicyRecognition"]] = relationship(
        "CompetitionPolicyRecognition",
        back_populates="major",
    )


class UniversityPolicy(Base, TimestampMixin):
    __tablename__ = "university_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    university_id: Mapped[int] = mapped_column(ForeignKey("universities.id", ondelete="CASCADE"), nullable=False)
    policy_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    policy_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    source_url: Mapped[str | None] = mapped_column(String(700), nullable=True)
    official_file_url: Mapped[str | None] = mapped_column(String(700), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    university: Mapped[University] = relationship(back_populates="policies")
    competition_policies: Mapped[list["UniversityCompetitionPolicy"]] = relationship(back_populates="policy")


class UniversityCompetitionPolicy(Base, TimestampMixin):
    __tablename__ = "university_competition_policies"
    __table_args__ = (
        UniqueConstraint(
            "university_id",
            "competition_id",
            "policy_id",
            "year",
            "usage_type",
            name="uq_university_competition_policy_scope",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    university_id: Mapped[int] = mapped_column(ForeignKey("universities.id", ondelete="CASCADE"), nullable=False)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False)
    policy_id: Mapped[int | None] = mapped_column(ForeignKey("university_policies.id", ondelete="SET NULL"), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    recognition_status: Mapped[str] = mapped_column(String(50), default="unknown", nullable=False, index=True)
    recognized_level: Mapped[str | None] = mapped_column(String(120), nullable=True)
    recognized_award: Mapped[str | None] = mapped_column(String(120), nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    usage_type: Mapped[str] = mapped_column(String(80), default="other", nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    university: Mapped[University] = relationship(back_populates="competition_policies")
    competition: Mapped["Competition"] = relationship("Competition", back_populates="university_policies")
    policy: Mapped[UniversityPolicy | None] = relationship(back_populates="competition_policies")
