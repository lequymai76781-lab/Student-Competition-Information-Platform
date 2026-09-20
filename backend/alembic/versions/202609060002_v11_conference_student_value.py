"""Academic Conference V1.1 additive schema (student value & recognition).

Adds controlled student-value/audience vocabularies as JSON columns on
ConferenceSeries and ConferenceEdition, structured participation/paper detail
JSON on ConferenceEdition, and a rejection_reason on Discovery candidates.
Recognition keeps the existing external_classifications JSON (records with
system/level/version_year/source_url/evidence) so no duplicate rating table is
created.

Revision ID: 202609060002
Revises: 202609060001
Create Date: 2026-09-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609060002"
down_revision: Union[str, None] = "202609060001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _add_column(table: str, column: sa.Column) -> None:
    if column.name not in _columns(table):
        op.add_column(table, column)


def _add_index(table: str, column_name: str) -> None:
    index_name = f"ix_{table}_{column_name}"
    existing = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)}
    if index_name not in existing:
        op.create_index(index_name, table, [column_name])


def upgrade() -> None:
    for column in (
        sa.Column("student_value_tags", sa.JSON(), nullable=True),
        sa.Column("audience", sa.JSON(), nullable=True),
    ):
        _add_column("conference_series", column)

    for column in (
        sa.Column("student_value_tags", sa.JSON(), nullable=True),
        sa.Column("audience", sa.JSON(), nullable=True),
        sa.Column("participation_details", sa.JSON(), nullable=True),
        sa.Column("paper_details", sa.JSON(), nullable=True),
    ):
        _add_column("conference_editions", column)

    _add_column(
        "conference_discovery_candidates",
        sa.Column("rejection_reason", sa.String(length=80), nullable=True),
    )
    _add_index("conference_discovery_candidates", "rejection_reason")


def downgrade() -> None:
    series_columns = _columns("conference_series")
    for column_name in ("student_value_tags", "audience"):
        if column_name in series_columns:
            op.drop_column("conference_series", column_name)

    edition_columns = _columns("conference_editions")
    for column_name in (
        "student_value_tags",
        "audience",
        "participation_details",
        "paper_details",
    ):
        if column_name in edition_columns:
            op.drop_column("conference_editions", column_name)

    if "rejection_reason" in _columns("conference_discovery_candidates"):
        op.drop_column("conference_discovery_candidates", "rejection_reason")
