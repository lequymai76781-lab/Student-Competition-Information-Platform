"""V0.7 deadline resolution and fact enrichment

Revision ID: 202609010006
Revises: 202609010005
Create Date: 2026-09-01 09:20:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609010006"
down_revision: Union[str, None] = "202609010005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())

    competition_columns = {column["name"] for column in inspector.get_columns("competitions")}
    with op.batch_alter_table("competitions") as batch_op:
        _add(batch_op, competition_columns, "undertakers", sa.JSON())
        _add(batch_op, competition_columns, "description_source_url", sa.String(length=1000))
        _add(batch_op, competition_columns, "development_history", sa.Text())
        _add(batch_op, competition_columns, "founded_year_candidate", sa.Integer())
        _add(batch_op, competition_columns, "last_verified_at", sa.DateTime(timezone=True))
        _add(batch_op, competition_columns, "last_seen_at", sa.DateTime(timezone=True))
        _add(batch_op, competition_columns, "source_hash", sa.String(length=128))
        if "source_hash" not in competition_columns:
            batch_op.create_index("ix_competitions_source_hash", ["source_hash"])
        if "last_verified_at" not in competition_columns:
            batch_op.create_index("ix_competitions_last_verified_at", ["last_verified_at"])

    edition_columns = {column["name"] for column in inspector.get_columns("competition_editions")}
    with op.batch_alter_table("competition_editions") as batch_op:
        _add(batch_op, edition_columns, "official_submission_deadline", sa.DateTime(timezone=True))
        _add(batch_op, edition_columns, "official_competition_date", sa.DateTime(timezone=True))
        _add(batch_op, edition_columns, "last_seen_at", sa.DateTime(timezone=True))
        _add(batch_op, edition_columns, "source_hash", sa.String(length=128))
        if "official_submission_deadline" not in edition_columns:
            batch_op.create_index(
                "ix_competition_editions_official_submission_deadline",
                ["official_submission_deadline"],
            )
        if "official_competition_date" not in edition_columns:
            batch_op.create_index("ix_competition_editions_official_competition_date", ["official_competition_date"])
        if "last_seen_at" not in edition_columns:
            batch_op.create_index("ix_competition_editions_last_seen_at", ["last_seen_at"])
        if "source_hash" not in edition_columns:
            batch_op.create_index("ix_competition_editions_source_hash", ["source_hash"])

    relation_columns = {
        column["name"] for column in inspector.get_columns("university_competition_edition_relations")
    }
    with op.batch_alter_table("university_competition_edition_relations") as batch_op:
        if "notice_type" not in relation_columns:
            batch_op.add_column(
                sa.Column("notice_type", sa.String(length=80), server_default="other", nullable=False)
            )
            batch_op.create_index("ix_university_competition_edition_relations_notice_type", ["notice_type"])
        _add(batch_op, relation_columns, "notice_title", sa.String(length=700))
        _add(batch_op, relation_columns, "internal_submission_deadline", sa.DateTime(timezone=True))
        _add(batch_op, relation_columns, "college_registration_start", sa.DateTime(timezone=True))
        _add(batch_op, relation_columns, "college_registration_deadline", sa.DateTime(timezone=True))
        _add(batch_op, relation_columns, "college_submission_deadline", sa.DateTime(timezone=True))
        _add(batch_op, relation_columns, "contact_person", sa.String(length=120))
        _add(batch_op, relation_columns, "contact_method", sa.String(length=255))
        _add(batch_op, relation_columns, "last_verified_at", sa.DateTime(timezone=True))
        _add(batch_op, relation_columns, "last_seen_at", sa.DateTime(timezone=True))
        _add(batch_op, relation_columns, "source_hash", sa.String(length=128))
        if "internal_submission_deadline" not in relation_columns:
            batch_op.create_index(
                "ix_university_competition_edition_relations_internal_submission_deadline",
                ["internal_submission_deadline"],
            )
        if "college_registration_deadline" not in relation_columns:
            batch_op.create_index(
                "ix_university_competition_edition_relations_college_registration_deadline",
                ["college_registration_deadline"],
            )
        if "college_submission_deadline" not in relation_columns:
            batch_op.create_index(
                "ix_university_competition_edition_relations_college_submission_deadline",
                ["college_submission_deadline"],
            )
        if "last_verified_at" not in relation_columns:
            batch_op.create_index(
                "ix_university_competition_edition_relations_last_verified_at",
                ["last_verified_at"],
            )
        if "source_hash" not in relation_columns:
            batch_op.create_index("ix_university_competition_edition_relations_source_hash", ["source_hash"])

    fact_columns = {column["name"] for column in inspector.get_columns("competition_fact_sources")}
    with op.batch_alter_table("competition_fact_sources") as batch_op:
        _add(batch_op, fact_columns, "source_level", sa.String(length=30))
        _add(batch_op, fact_columns, "source_hash", sa.String(length=128))
        _add(batch_op, fact_columns, "last_verified_at", sa.DateTime(timezone=True))
        if "source_level" not in fact_columns:
            batch_op.create_index("ix_competition_fact_sources_source_level", ["source_level"])
        if "source_hash" not in fact_columns:
            batch_op.create_index("ix_competition_fact_sources_source_hash", ["source_hash"])

    if "competition_tracks" not in tables:
        op.create_table(
            "competition_tracks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("competition_id", sa.Integer(), sa.ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("track_type", sa.String(length=80), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("source_url", sa.String(length=1000), nullable=True),
            sa.Column("source_name", sa.String(length=255), nullable=True),
            sa.Column("reliability_tier", sa.Integer(), server_default="5", nullable=False),
            sa.Column("is_official", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("verification_status", sa.String(length=50), server_default="secondary_source_only", nullable=False),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("order_index", sa.Integer(), server_default="0", nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("competition_id", "name", name="uq_competition_track_name"),
        )
        for column in ("id", "competition_id", "name", "track_type", "verification_status"):
            op.create_index(f"ix_competition_tracks_{column}", "competition_tracks", [column])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "competition_tracks" in set(inspector.get_table_names()):
        op.drop_table("competition_tracks")

    with op.batch_alter_table("competition_fact_sources") as batch_op:
        for index in ("ix_competition_fact_sources_source_hash", "ix_competition_fact_sources_source_level"):
            _drop_index(batch_op, index)
        for column in ("last_verified_at", "source_hash", "source_level"):
            _drop_column(batch_op, column)

    with op.batch_alter_table("university_competition_edition_relations") as batch_op:
        for index in (
            "ix_university_competition_edition_relations_source_hash",
            "ix_university_competition_edition_relations_last_verified_at",
            "ix_university_competition_edition_relations_college_submission_deadline",
            "ix_university_competition_edition_relations_college_registration_deadline",
            "ix_university_competition_edition_relations_internal_submission_deadline",
            "ix_university_competition_edition_relations_notice_type",
        ):
            _drop_index(batch_op, index)
        for column in (
            "source_hash",
            "last_seen_at",
            "last_verified_at",
            "contact_method",
            "contact_person",
            "college_submission_deadline",
            "college_registration_deadline",
            "college_registration_start",
            "internal_submission_deadline",
            "notice_title",
            "notice_type",
        ):
            _drop_column(batch_op, column)

    with op.batch_alter_table("competition_editions") as batch_op:
        for index in (
            "ix_competition_editions_source_hash",
            "ix_competition_editions_last_seen_at",
            "ix_competition_editions_official_competition_date",
            "ix_competition_editions_official_submission_deadline",
        ):
            _drop_index(batch_op, index)
        for column in ("source_hash", "last_seen_at", "official_competition_date", "official_submission_deadline"):
            _drop_column(batch_op, column)

    with op.batch_alter_table("competitions") as batch_op:
        for index in ("ix_competitions_last_verified_at", "ix_competitions_source_hash"):
            _drop_index(batch_op, index)
        for column in (
            "source_hash",
            "last_seen_at",
            "last_verified_at",
            "founded_year_candidate",
            "development_history",
            "description_source_url",
            "undertakers",
        ):
            _drop_column(batch_op, column)


def _add(batch_op: object, columns: set[str], name: str, column_type: sa.types.TypeEngine) -> None:
    if name not in columns:
        batch_op.add_column(sa.Column(name, column_type, nullable=True))


def _drop_index(batch_op: object, name: str) -> None:
    try:
        batch_op.drop_index(name)
    except Exception:
        pass


def _drop_column(batch_op: object, name: str) -> None:
    try:
        batch_op.drop_column(name)
    except Exception:
        pass
