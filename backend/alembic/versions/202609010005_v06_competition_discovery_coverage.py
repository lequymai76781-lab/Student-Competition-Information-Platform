"""V0.6 985 competition discovery coverage

Revision ID: 202609010005
Revises: 202609010004
Create Date: 2026-09-01 02:10:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609010005"
down_revision: Union[str, None] = "202609010004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    university_columns = {column["name"] for column in inspector.get_columns("universities")}
    with op.batch_alter_table("universities") as batch_op:
        if "competition_discovery_status" not in university_columns:
            batch_op.add_column(
                sa.Column(
                    "competition_discovery_status",
                    sa.String(length=40),
                    server_default="not_started",
                    nullable=False,
                )
            )
            batch_op.create_index("ix_universities_competition_discovery_status", ["competition_discovery_status"])
        _add(batch_op, university_columns, "competition_discovery_started_at", sa.DateTime(timezone=True))
        _add(batch_op, university_columns, "last_competition_discovery_at", sa.DateTime(timezone=True))
        _add(batch_op, university_columns, "competition_discovery_error", sa.Text())

    edition_columns = {column["name"] for column in inspector.get_columns("competition_editions")}
    with op.batch_alter_table("competition_editions") as batch_op:
        if "official_registration_deadline" not in edition_columns:
            batch_op.add_column(sa.Column("official_registration_deadline", sa.DateTime(timezone=True), nullable=True))
            batch_op.create_index("ix_competition_editions_official_registration_deadline", ["official_registration_deadline"])
        if "university_registration_deadline" not in edition_columns:
            batch_op.add_column(sa.Column("university_registration_deadline", sa.DateTime(timezone=True), nullable=True))
            batch_op.create_index("ix_competition_editions_university_registration_deadline", ["university_registration_deadline"])

    stats_columns = {column["name"] for column in inspector.get_columns("competition_statistics")}
    with op.batch_alter_table("competition_statistics") as batch_op:
        _add_count(batch_op, stats_columns, "source_count")
        _add_count(batch_op, stats_columns, "university_source_count")
        _add_count(batch_op, stats_columns, "university_count")
        _add_count(batch_op, stats_columns, "college_count")
        _add(batch_op, stats_columns, "last_seen_at", sa.DateTime(timezone=True))

    tables = set(inspector.get_table_names())
    if "university_competition_discovery_reports" not in tables:
        op.create_table(
            "university_competition_discovery_reports",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("university_id", sa.Integer(), sa.ForeignKey("universities.id", ondelete="CASCADE"), nullable=False),
            sa.Column("batch_name", sa.String(length=120), nullable=False),
            sa.Column("status", sa.String(length=40), server_default="not_started", nullable=False),
            sa.Column("pages_searched", sa.Integer(), server_default="0", nullable=False),
            sa.Column("competition_leads", sa.Integer(), server_default="0", nullable=False),
            sa.Column("matched_competitions", sa.Integer(), server_default="0", nullable=False),
            sa.Column("new_competitions", sa.Integer(), server_default="0", nullable=False),
            sa.Column("new_editions", sa.Integer(), server_default="0", nullable=False),
            sa.Column("official_sources", sa.Integer(), server_default="0", nullable=False),
            sa.Column("university_notice_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("college_notice_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("current_registration_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("edition_2026_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("wechat_leads", sa.Integer(), server_default="0", nullable=False),
            sa.Column("duplicate_leads", sa.Integer(), server_default="0", nullable=False),
            sa.Column("errors_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("last_crawled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("channel_stats", sa.JSON(), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("university_id", "batch_name", name="uq_university_competition_discovery_report_batch"),
        )
        for column in ("id", "university_id", "batch_name", "status", "last_crawled_at"):
            op.create_index(
                f"ix_university_competition_discovery_reports_{column}",
                "university_competition_discovery_reports",
                [column],
            )

    if "university_competition_edition_relations" not in tables:
        op.create_table(
            "university_competition_edition_relations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("university_id", sa.Integer(), sa.ForeignKey("universities.id", ondelete="CASCADE"), nullable=False),
            sa.Column("college_id", sa.Integer(), sa.ForeignKey("colleges.id", ondelete="SET NULL"), nullable=True),
            sa.Column(
                "competition_edition_id",
                sa.Integer(),
                sa.ForeignKey("competition_editions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "source_type",
                sa.String(length=80),
                server_default="university_official_notice",
                nullable=False,
            ),
            sa.Column("source_platform", sa.String(length=80), nullable=True),
            sa.Column("source_name", sa.String(length=255), nullable=True),
            sa.Column("internal_notice_url", sa.String(length=1000), nullable=False),
            sa.Column("organizing_department", sa.String(length=255), nullable=True),
            sa.Column("internal_contact", sa.String(length=255), nullable=True),
            sa.Column("internal_registration_start", sa.DateTime(timezone=True), nullable=True),
            sa.Column("internal_registration_deadline", sa.DateTime(timezone=True), nullable=True),
            sa.Column("official_registration_deadline", sa.DateTime(timezone=True), nullable=True),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "verification_status",
                sa.String(length=50),
                server_default="verified_official",
                nullable=False,
            ),
            sa.Column("is_verified", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("is_demo", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "university_id",
                "competition_edition_id",
                "internal_notice_url",
                name="uq_university_competition_edition_notice",
            ),
        )
        for column in (
            "id",
            "university_id",
            "college_id",
            "competition_edition_id",
            "source_type",
            "source_platform",
            "internal_registration_deadline",
            "official_registration_deadline",
            "published_at",
            "observed_at",
            "verification_status",
            "is_verified",
            "is_demo",
        ):
            op.create_index(
                f"ix_university_competition_edition_relations_{column}",
                "university_competition_edition_relations",
                [column],
            )


def downgrade() -> None:
    op.drop_table("university_competition_edition_relations")
    op.drop_table("university_competition_discovery_reports")

    with op.batch_alter_table("competition_statistics") as batch_op:
        for column in ("last_seen_at", "college_count", "university_count", "university_source_count", "source_count"):
            batch_op.drop_column(column)

    with op.batch_alter_table("competition_editions") as batch_op:
        batch_op.drop_index("ix_competition_editions_university_registration_deadline")
        batch_op.drop_index("ix_competition_editions_official_registration_deadline")
        batch_op.drop_column("university_registration_deadline")
        batch_op.drop_column("official_registration_deadline")

    with op.batch_alter_table("universities") as batch_op:
        batch_op.drop_index("ix_universities_competition_discovery_status")
        batch_op.drop_column("competition_discovery_error")
        batch_op.drop_column("last_competition_discovery_at")
        batch_op.drop_column("competition_discovery_started_at")
        batch_op.drop_column("competition_discovery_status")


def _add(batch_op: object, columns: set[str], name: str, column_type: sa.types.TypeEngine) -> None:
    if name not in columns:
        batch_op.add_column(sa.Column(name, column_type, nullable=True))


def _add_count(batch_op: object, columns: set[str], name: str) -> None:
    if name not in columns:
        batch_op.add_column(sa.Column(name, sa.Integer(), server_default="0", nullable=False))
