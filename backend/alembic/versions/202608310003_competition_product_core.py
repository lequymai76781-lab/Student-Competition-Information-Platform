"""competition product core and edition verification fields

Revision ID: 202608310003
Revises: 202608310002
Create Date: 2026-08-31 19:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202608310003"
down_revision: Union[str, None] = "202608310002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    competition_columns = {column["name"] for column in inspector.get_columns("competitions")}
    with op.batch_alter_table("competitions") as batch_op:
        if "parent_competition_id" not in competition_columns:
            batch_op.add_column(sa.Column("parent_competition_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                "fk_competitions_parent_competition_id",
                "competitions",
                ["parent_competition_id"],
                ["id"],
                ondelete="SET NULL",
            )
            batch_op.create_index("ix_competitions_parent_competition_id", ["parent_competition_id"])
        if "competition_type" not in competition_columns:
            batch_op.add_column(
                sa.Column("competition_type", sa.String(length=30), server_default="competition", nullable=False)
            )
            batch_op.create_index("ix_competitions_competition_type", ["competition_type"])
        if "typical_schedule" not in competition_columns:
            batch_op.add_column(sa.Column("typical_schedule", sa.Text(), nullable=True))
        if "data_completeness_score" not in competition_columns:
            batch_op.add_column(
                sa.Column("data_completeness_score", sa.Float(), server_default="0.0", nullable=False)
            )
            batch_op.create_index("ix_competitions_data_completeness_score", ["data_completeness_score"])
        if "is_official_verified" not in competition_columns:
            batch_op.add_column(
                sa.Column("is_official_verified", sa.Boolean(), server_default=sa.false(), nullable=False)
            )
            batch_op.create_index("ix_competitions_is_official_verified", ["is_official_verified"])

    inspector = sa.inspect(bind)
    edition_columns = {column["name"] for column in inspector.get_columns("competition_editions")}
    with op.batch_alter_table("competition_editions") as batch_op:
        if "submission_deadline" not in edition_columns:
            batch_op.add_column(sa.Column("submission_deadline", sa.DateTime(timezone=True), nullable=True))
            batch_op.create_index("ix_competition_editions_submission_deadline", ["submission_deadline"])
        if "official_notice_url" not in edition_columns:
            batch_op.add_column(sa.Column("official_notice_url", sa.String(length=700), nullable=True))
        if "official_registration_url" not in edition_columns:
            batch_op.add_column(sa.Column("official_registration_url", sa.String(length=700), nullable=True))
        if "source_url" not in edition_columns:
            batch_op.add_column(sa.Column("source_url", sa.String(length=700), nullable=True))
        if "is_verified" not in edition_columns:
            batch_op.add_column(sa.Column("is_verified", sa.Boolean(), server_default=sa.false(), nullable=False))
            batch_op.create_index("ix_competition_editions_is_verified", ["is_verified"])
        if "last_verified_at" not in edition_columns:
            batch_op.add_column(sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True))

    inspector = sa.inspect(bind)
    source_columns = {column["name"] for column in inspector.get_columns("competition_sources")}
    with op.batch_alter_table("competition_sources") as batch_op:
        if "source_repository" not in source_columns:
            batch_op.add_column(sa.Column("source_repository", sa.String(length=255), nullable=True))
            batch_op.create_index("ix_competition_sources_source_repository", ["source_repository"])
        if "source_file" not in source_columns:
            batch_op.add_column(sa.Column("source_file", sa.String(length=500), nullable=True))

    statistics_columns = {column["name"] for column in sa.inspect(bind).get_columns("competition_statistics")}
    if "score_breakdown" not in statistics_columns:
        with op.batch_alter_table("competition_statistics") as batch_op:
            batch_op.add_column(sa.Column("score_breakdown", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("competition_statistics") as batch_op:
        batch_op.drop_column("score_breakdown")
    with op.batch_alter_table("competition_sources") as batch_op:
        batch_op.drop_index("ix_competition_sources_source_repository")
        batch_op.drop_column("source_file")
        batch_op.drop_column("source_repository")
    with op.batch_alter_table("competition_editions") as batch_op:
        batch_op.drop_index("ix_competition_editions_is_verified")
        batch_op.drop_index("ix_competition_editions_submission_deadline")
        for column in (
            "last_verified_at",
            "is_verified",
            "source_url",
            "official_registration_url",
            "official_notice_url",
            "submission_deadline",
        ):
            batch_op.drop_column(column)
    with op.batch_alter_table("competitions") as batch_op:
        batch_op.drop_index("ix_competitions_is_official_verified")
        batch_op.drop_index("ix_competitions_data_completeness_score")
        batch_op.drop_index("ix_competitions_competition_type")
        batch_op.drop_index("ix_competitions_parent_competition_id")
        batch_op.drop_constraint("fk_competitions_parent_competition_id", type_="foreignkey")
        for column in (
            "is_official_verified",
            "data_completeness_score",
            "typical_schedule",
            "competition_type",
            "parent_competition_id",
        ):
            batch_op.drop_column(column)
