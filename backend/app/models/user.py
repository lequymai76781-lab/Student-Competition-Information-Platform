from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    profile: Mapped[UserProfile | None] = relationship(back_populates="user", cascade="all, delete-orphan", uselist=False)
    favorites: Mapped[list["Favorite"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    competition_statuses: Mapped[list["UserCompetitionStatus"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserProfile(Base, TimestampMixin):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    university_id: Mapped[int | None] = mapped_column(ForeignKey("universities.id", ondelete="SET NULL"), nullable=True)
    college_id: Mapped[int | None] = mapped_column(ForeignKey("colleges.id", ondelete="SET NULL"), nullable=True)
    major_id: Mapped[int | None] = mapped_column(ForeignKey("majors.id", ondelete="SET NULL"), nullable=True)
    university_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    college_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    major_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(40), nullable=True)
    graduation_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    goal: Mapped[str | None] = mapped_column(String(120), nullable=True)
    skills: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    interest_tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    weekly_available_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preferred_team_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    preferred_competition_level: Mapped[str | None] = mapped_column(String(80), nullable=True)
    accept_cross_major: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    accept_cross_university: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped[User] = relationship(back_populates="profile")


class Favorite(Base, TimestampMixin):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "competition_id", name="uq_favorite_user_competition"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False)

    user: Mapped[User] = relationship(back_populates="favorites")


class UserCompetitionStatus(Base, TimestampMixin):
    """Lightweight per-user competition pipeline status (interested..abandoned)."""

    __tablename__ = "user_competition_statuses"
    __table_args__ = (
        UniqueConstraint("user_id", "competition_id", name="uq_user_competition_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(40),
        default="interested",
        nullable=False,
        index=True,
    )  # interested | planning | registered | participating | finished | abandoned
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    user: Mapped[User] = relationship(back_populates="competition_statuses")


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "dedup_key", name="uq_notification_user_dedup"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    competition_id: Mapped[int | None] = mapped_column(
        ForeignKey("competitions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    competition_edition_id: Mapped[int | None] = mapped_column(
        ForeignKey("competition_editions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dedup_key: Mapped[str] = mapped_column(String(160), nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    user: Mapped[User] = relationship(back_populates="notifications")


class BetaFeedback(Base, TimestampMixin):
    __tablename__ = "beta_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
