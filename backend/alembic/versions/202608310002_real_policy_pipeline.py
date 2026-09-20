"""real policy pipeline state and candidate evidence

Revision ID: 202608310002
Revises: 202608310001
Create Date: 2026-08-31 16:55:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202608310002"
down_revision: Union[str, None] = "202608310001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    university_columns = {column["name"] for column in inspector.get_columns("universities")}
    new_university_columns = {
        "policy_crawl_status": sa.Column(
            "policy_crawl_status",
            sa.String(length=40),
            server_default="not_started",
            nullable=False,
        ),
        "policy_crawl_started_at": sa.Column("policy_crawl_started_at", sa.DateTime(timezone=True), nullable=True),
        "last_policy_crawl_at": sa.Column("last_policy_crawl_at", sa.DateTime(timezone=True), nullable=True),
        "policy_crawl_error": sa.Column("policy_crawl_error", sa.Text(), nullable=True),
    }
    missing_columns = [column for name, column in new_university_columns.items() if name not in university_columns]
    if missing_columns:
        with op.batch_alter_table("universities") as batch_op:
            for column in missing_columns:
                batch_op.add_column(column)

    inspector = sa.inspect(bind)
    university_indexes = {index["name"] for index in inspector.get_indexes("universities")}
    if "ix_universities_policy_crawl_status" not in university_indexes:
        op.create_index("ix_universities_policy_crawl_status", "universities", ["policy_crawl_status"])

    if "candidate_competitions" in inspector.get_table_names():
        return

    op.create_table(
        "candidate_competitions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("policy_document_id", sa.Integer(), nullable=False),
        sa.Column("university_id", sa.Integer(), nullable=False),
        sa.Column("college_id", sa.Integer(), nullable=True),
        sa.Column("raw_name", sa.String(length=500), nullable=False),
        sa.Column("raw_category", sa.String(length=255), nullable=True),
        sa.Column("raw_level", sa.String(length=120), nullable=True),
        sa.Column("raw_award", sa.String(length=255), nullable=True),
        sa.Column("raw_score", sa.String(length=255), nullable=True),
        sa.Column("evidence_text", sa.Text(), nullable=False),
        sa.Column("table_row", sa.String(length=120), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("normalization_status", sa.String(length=60), server_default="pending", nullable=False),
        sa.Column("normalized_competition_id", sa.Integer(), nullable=True),
        sa.Column("needs_manual_review", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["college_id"], ["colleges.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["normalized_competition_id"], ["competitions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["policy_document_id"], ["policy_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["university_id"], ["universities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "policy_document_id",
            "table_row",
            "raw_name",
            name="uq_candidate_competition_document_row_name",
        ),
    )
    for column in (
        "college_id",
        "confidence",
        "is_demo",
        "needs_manual_review",
        "normalization_status",
        "normalized_competition_id",
        "policy_document_id",
        "raw_name",
        "university_id",
    ):
        op.create_index(f"ix_candidate_competitions_{column}", "candidate_competitions", [column])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "candidate_competitions" in inspector.get_table_names():
        op.drop_table("candidate_competitions")

    university_columns = {column["name"] for column in sa.inspect(bind).get_columns("universities")}
    removable = [
        column
        for column in (
            "policy_crawl_error",
            "last_policy_crawl_at",
            "policy_crawl_started_at",
            "policy_crawl_status",
        )
        if column in university_columns
    ]
    if removable:
        with op.batch_alter_table("universities") as batch_op:
            if "policy_crawl_status" in removable:
                batch_op.drop_index("ix_universities_policy_crawl_status")
            for column in removable:
                batch_op.drop_column(column)
