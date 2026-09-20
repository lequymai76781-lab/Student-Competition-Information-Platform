"""V0.8 edition freshness and fact revisions

Revision ID: 202609020008
Revises: 202609010007
Create Date: 2026-09-02 00:20:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609020008"
down_revision: Union[str, None] = "202609010007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("competition_editions")}
    with op.batch_alter_table("competition_editions") as batch_op:
        if "source_updated_at" not in columns:
            batch_op.add_column(sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True))
        if "next_check_at" not in columns:
            batch_op.add_column(sa.Column("next_check_at", sa.DateTime(timezone=True), nullable=True))
            batch_op.create_index("ix_competition_editions_next_check_at", ["next_check_at"])
        if "freshness_status" not in columns:
            batch_op.add_column(
                sa.Column("freshness_status", sa.String(length=30), server_default="unknown", nullable=False)
            )
            batch_op.create_index("ix_competition_editions_freshness_status", ["freshness_status"])

    if not sa.inspect(op.get_bind()).has_table("competition_fact_revisions"):
        op.create_table(
            "competition_fact_revisions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("competition_id", sa.Integer(), nullable=False),
            sa.Column("competition_edition_id", sa.Integer(), nullable=True),
            sa.Column("field_name", sa.String(length=120), nullable=False),
            sa.Column("old_value", sa.JSON(), nullable=True),
            sa.Column("new_value", sa.JSON(), nullable=True),
            sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("source_url", sa.String(length=1000), nullable=False),
            sa.Column("source_name", sa.String(length=255), nullable=True),
            sa.Column("verification_status", sa.String(length=50), server_default="verified_official", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["competition_edition_id"], ["competition_editions.id"], ondelete="CASCADE"),
        )
        for column in ("id", "competition_id", "competition_edition_id", "field_name", "changed_at", "verification_status"):
            op.create_index(f"ix_competition_fact_revisions_{column}", "competition_fact_revisions", [column])


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("competition_fact_revisions"):
        op.drop_table("competition_fact_revisions")
    with op.batch_alter_table("competition_editions") as batch_op:
        for index_name in (
            "ix_competition_editions_freshness_status",
            "ix_competition_editions_next_check_at",
        ):
            try:
                batch_op.drop_index(index_name)
            except Exception:
                pass
        for column in ("freshness_status", "next_check_at", "source_updated_at"):
            try:
                batch_op.drop_column(column)
            except Exception:
                pass
