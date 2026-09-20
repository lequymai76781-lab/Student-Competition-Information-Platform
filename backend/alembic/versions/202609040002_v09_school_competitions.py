"""V0.9 school_competitions semantic layer

Additive, non-destructive:

- school_competitions: canonical school x competition relation table
- competition_sources.authority_level: S/A/B/C/D proof power
- competition_leads.duplicate_of_id: duplicate lead linking

Revision ID: 202609040002
Revises: 202609040001
Create Date: 2026-09-04 11:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609040002"
down_revision: Union[str, None] = "202609040001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "school_competitions" not in tables:
        op.create_table(
            "school_competitions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("school_id", sa.Integer(), nullable=False),
            sa.Column("competition_id", sa.Integer(), nullable=False),
            sa.Column("competition_edition_id", sa.Integer(), nullable=True),
            sa.Column("recognition_status", sa.String(length=60), server_default="unknown", nullable=False),
            sa.Column("school_level", sa.String(length=120), nullable=True),
            sa.Column("school_category", sa.String(length=120), nullable=True),
            sa.Column("participation_status", sa.String(length=60), server_default="unknown", nullable=False),
            sa.Column("responsible_department", sa.String(length=255), nullable=True),
            sa.Column("college_id", sa.Integer(), nullable=True),
            sa.Column("responsible_college", sa.String(length=255), nullable=True),
            sa.Column("campus_registration_start", sa.DateTime(timezone=True), nullable=True),
            sa.Column("campus_registration_deadline", sa.DateTime(timezone=True), nullable=True),
            sa.Column("campus_selection_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("notice_url", sa.String(length=1000), nullable=True),
            sa.Column("credit_policy", sa.Text(), nullable=True),
            sa.Column("award_policy", sa.Text(), nullable=True),
            sa.Column("record_status", sa.String(length=50), server_default="school_confirmed", nullable=False),
            sa.Column("needs_review", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("conflict_notes", sa.Text(), nullable=True),
            sa.Column("provenance", sa.JSON(), nullable=True),
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["school_id"], ["universities.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["competition_edition_id"],
                ["competition_editions.id"],
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(["college_id"], ["colleges.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("school_id", "competition_id", name="uq_school_competition_pair"),
        )
        for column in (
            "id",
            "school_id",
            "competition_id",
            "competition_edition_id",
            "recognition_status",
            "participation_status",
            "college_id",
            "campus_registration_deadline",
            "record_status",
            "needs_review",
        ):
            op.create_index(f"ix_school_competitions_{column}", "school_competitions", [column])

    source_columns = {column["name"] for column in inspector.get_columns("competition_sources")}
    with op.batch_alter_table("competition_sources") as batch_op:
        if "authority_level" not in source_columns:
            batch_op.add_column(sa.Column("authority_level", sa.String(length=4), nullable=True))
        indexes = {index["name"] for index in inspector.get_indexes("competition_sources")}
        if "ix_competition_sources_authority_level" not in indexes:
            batch_op.create_index("ix_competition_sources_authority_level", ["authority_level"])

    lead_columns = {column["name"] for column in inspector.get_columns("competition_leads")}
    with op.batch_alter_table("competition_leads") as batch_op:
        if "duplicate_of_id" not in lead_columns:
            batch_op.add_column(sa.Column("duplicate_of_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                "fk_competition_leads_duplicate_of_id",
                "competition_leads",
                ["duplicate_of_id"],
                ["id"],
                ondelete="SET NULL",
            )
        indexes = {index["name"] for index in inspector.get_indexes("competition_leads")}
        if "ix_competition_leads_duplicate_of_id" not in indexes:
            batch_op.create_index("ix_competition_leads_duplicate_of_id", ["duplicate_of_id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "school_competitions" in tables:
        op.drop_table("school_competitions")

    with op.batch_alter_table("competition_leads") as batch_op:
        indexes = {index["name"] for index in inspector.get_indexes("competition_leads")}
        if "ix_competition_leads_duplicate_of_id" in indexes:
            batch_op.drop_index("ix_competition_leads_duplicate_of_id")
        columns = {column["name"] for column in inspector.get_columns("competition_leads")}
        if "duplicate_of_id" in columns:
            batch_op.drop_constraint("fk_competition_leads_duplicate_of_id", type_="foreignkey")
            batch_op.drop_column("duplicate_of_id")

    with op.batch_alter_table("competition_sources") as batch_op:
        indexes = {index["name"] for index in inspector.get_indexes("competition_sources")}
        if "ix_competition_sources_authority_level" in indexes:
            batch_op.drop_index("ix_competition_sources_authority_level")
        columns = {column["name"] for column in inspector.get_columns("competition_sources")}
        if "authority_level" in columns:
            batch_op.drop_column("authority_level")
