"""Academic Conference V1.2 opportunity & discipline mapping layer.

Adds lightweight V1.2 entities without touching the competition module:
- conference_series.secondary_disciplines / discipline_evidence (JSON);
- conference_opportunities (per-Edition student opportunities);
- conference_discipline_mappings (major alias -> controlled discipline).

Revision ID: 202609060004
Revises: 202609060003
Create Date: 2026-09-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609060004"
down_revision: Union[str, None] = "202609060003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    series_columns = _columns("conference_series")
    if "secondary_disciplines" not in series_columns:
        op.add_column(
            "conference_series",
            sa.Column("secondary_disciplines", sa.JSON(), nullable=True),
        )
    if "discipline_evidence" not in series_columns:
        op.add_column(
            "conference_series",
            sa.Column("discipline_evidence", sa.JSON(), nullable=True),
        )

    if not op.get_bind().dialect.has_table(op.get_bind(), "conference_opportunities"):
        op.create_table(
            "conference_opportunities",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column(
                "conference_edition_id",
                sa.Integer(),
                sa.ForeignKey("conference_editions.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("opportunity_type", sa.String(60), nullable=False, index=True),
            sa.Column("title", sa.String(255), nullable=True),
            sa.Column("official_label", sa.String(500), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("audience", sa.JSON(), nullable=True),
            sa.Column("open_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deadline", sa.DateTime(timezone=True), nullable=True, index=True),
            sa.Column("participation_mode", sa.String(60), nullable=True),
            sa.Column("official_url", sa.String(700), nullable=True, index=True),
            sa.Column(
                "source_id",
                sa.Integer(),
                sa.ForeignKey("conference_sources.id", ondelete="SET NULL"),
                nullable=True,
                index=True,
            ),
            sa.Column("evidence", sa.Text(), nullable=True),
            sa.Column(
                "evidence_status",
                sa.String(50),
                nullable=False,
                server_default="pending_evidence",
                index=True,
            ),
            sa.Column(
                "verification_status",
                sa.String(50),
                nullable=False,
                server_default="unverified",
                index=True,
            ),
            sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false(), index=True),
            sa.Column("risk_flags", sa.JSON(), nullable=True),
            sa.Column("needs_review", sa.Boolean(), nullable=False, server_default=sa.false(), index=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "conference_edition_id",
                "opportunity_type",
                "official_url",
                name="uq_conference_opportunity_edition_type_url",
            ),
        )

    if not op.get_bind().dialect.has_table(op.get_bind(), "conference_discipline_mappings"):
        op.create_table(
            "conference_discipline_mappings",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("major_alias", sa.String(255), nullable=False, index=True),
            sa.Column("discipline", sa.String(120), nullable=False, index=True),
            sa.Column("relationship_type", sa.String(40), nullable=False, index=True),
            sa.Column("mapping_basis", sa.Text(), nullable=True),
            sa.Column("evidence", sa.Text(), nullable=True),
            sa.Column("source_url", sa.String(700), nullable=True),
            sa.Column("status", sa.String(40), nullable=False, server_default="active", index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "major_alias",
                "discipline",
                name="uq_discipline_mapping_alias",
            ),
        )


def downgrade() -> None:
    if op.get_bind().dialect.has_table(op.get_bind(), "conference_discipline_mappings"):
        op.drop_table("conference_discipline_mappings")
    if op.get_bind().dialect.has_table(op.get_bind(), "conference_opportunities"):
        op.drop_table("conference_opportunities")
    series_columns = _columns("conference_series")
    if "secondary_disciplines" in series_columns:
        op.drop_column("conference_series", "secondary_disciplines")
    if "discipline_evidence" in series_columns:
        op.drop_column("conference_series", "discipline_evidence")
