"""V1.0 notifications & productization tables

Revision ID: 202609020011
Revises: 202609020010
Create Date: 2026-09-02 20:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609020011"
down_revision: Union[str, None] = "202609020010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names() -> set[str]:
    return {name for name in sa.inspect(op.get_bind()).get_table_names()}


def upgrade() -> None:
    tables = _table_names()
    if "notifications" not in tables:
        op.create_table(
            "notifications",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("type", sa.String(length=50), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("content", sa.Text(), nullable=True),
            sa.Column("competition_id", sa.Integer(), nullable=True),
            sa.Column("competition_edition_id", sa.Integer(), nullable=True),
            sa.Column("source_event_id", sa.Integer(), nullable=True),
            sa.Column("dedup_key", sa.String(length=160), nullable=False),
            sa.Column("is_read", sa.Boolean(), server_default="0", nullable=False),
            sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["competition_edition_id"], ["competition_editions.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("user_id", "dedup_key", name="uq_notification_user_dedup"),
        )
        for column in ("id", "user_id", "type", "competition_id", "competition_edition_id", "is_read"):
            op.create_index(f"ix_notifications_{column}", "notifications", [column])

    if "competition_update_events" not in tables:
        op.create_table(
            "competition_update_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("competition_id", sa.Integer(), nullable=False),
            sa.Column("competition_edition_id", sa.Integer(), nullable=True),
            sa.Column("event_type", sa.String(length=60), nullable=False),
            sa.Column("field_name", sa.String(length=120), nullable=True),
            sa.Column("old_value", sa.JSON(), nullable=True),
            sa.Column("new_value", sa.JSON(), nullable=True),
            sa.Column("source_url", sa.String(length=1000), nullable=False),
            sa.Column("source_name", sa.String(length=255), nullable=True),
            sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["competition_edition_id"], ["competition_editions.id"], ondelete="SET NULL"),
        )
        for column in ("id", "competition_id", "competition_edition_id", "event_type", "changed_at", "observed_at"):
            op.create_index(f"ix_competition_update_events_{column}", "competition_update_events", [column])

    if "user_correction_submissions" not in tables:
        op.create_table(
            "user_correction_submissions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("competition_id", sa.Integer(), nullable=False),
            sa.Column("competition_edition_id", sa.Integer(), nullable=True),
            sa.Column("correction_type", sa.String(length=60), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("source_url", sa.String(length=1000), nullable=True),
            sa.Column("contact_note", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=40), server_default="pending", nullable=False),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reviewed_by", sa.Integer(), nullable=True),
            sa.Column("review_note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["competition_edition_id"], ["competition_editions.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
        )
        for column in ("id", "user_id", "competition_id", "correction_type", "status"):
            op.create_index(f"ix_user_correction_submissions_{column}", "user_correction_submissions", [column])

    if "beta_feedback" not in tables:
        op.create_table(
            "beta_feedback",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("category", sa.String(length=40), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("url", sa.String(length=500), nullable=True),
            sa.Column("status", sa.String(length=30), server_default="pending", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        )
        for column in ("id", "user_id", "category", "status"):
            op.create_index(f"ix_beta_feedback_{column}", "beta_feedback", [column])

    user_columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}
    if "is_admin" not in user_columns:
        with op.batch_alter_table("users") as batch_op:
            batch_op.add_column(
                sa.Column("is_admin", sa.Boolean(), server_default="0", nullable=False)
            )
            batch_op.create_index("ix_users_is_admin", ["is_admin"])


def downgrade() -> None:
    tables = _table_names()
    for name in ("notifications", "competition_update_events", "user_correction_submissions", "beta_feedback"):
        if name in tables:
            op.drop_table(name)
    with op.batch_alter_table("users") as batch_op:
        try:
            batch_op.drop_index("ix_users_is_admin")
        except Exception:
            pass
        try:
            batch_op.drop_column("is_admin")
        except Exception:
            pass
