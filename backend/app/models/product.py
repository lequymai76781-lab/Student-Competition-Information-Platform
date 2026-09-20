from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class CompetitionUpdateEvent(Base, TimestampMixin):
    """Traceable competition change event (deadline/date/url/notice/edition...)."""

    __tablename__ = "competition_update_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    competition_edition_id: Mapped[int | None] = mapped_column(
        ForeignKey("competition_editions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    field_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    old_value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON, nullable=True)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)


class UserCorrectionSubmission(Base, TimestampMixin):
    """User-submitted correction, never writes facts directly."""

    __tablename__ = "user_correction_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    competition_edition_id: Mapped[int | None] = mapped_column(
        ForeignKey("competition_editions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    correction_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    contact_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False, index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    admin_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    object_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    object_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class BetaMetric(Base):
    __tablename__ = "beta_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
