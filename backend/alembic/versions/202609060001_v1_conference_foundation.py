"""Academic Conference V1 foundation (additive, non-destructive).

Extends the V0.9 conference schema (empty tables until now) with:

- identity fields: english_name / subdiscipline / frequency / scope marker
- independent Series & Edition authority_status (+ verification fields)
- risk markers (JSON vocabulary, no auto-scoring)
- external classifications (CCF etc. with system + level + version_year)
- full conference lifecycle deadlines (poster/workshop/registration URLs)
- structured indexing claims + publication states (claims != indexed)
- conference_sources / conference_organizations / discovery candidates
- SchoolConference: responsible_college / source_id / verified_at

Uses plain ADD COLUMN / CREATE TABLE operations (no batch table rebuilds) so
the migration is deterministic on SQLite and PostgreSQL.

Revision ID: 202609060001
Revises: 202609040002
Create Date: 2026-09-06 10:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609060001"
down_revision: Union[str, None] = "202609040002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _dialect() -> str:
    return op.get_bind().dialect.name


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)}


def _add_column(table: str, column: sa.Column) -> None:
    if column.name not in _columns(table):
        op.add_column(table, column)


def _add_index(table: str, column_name: str) -> None:
    index_name = f"ix_{table}_{column_name}"
    if index_name not in _indexes(table):
        op.create_index(index_name, table, [column_name])


def upgrade() -> None:
    bind = op.get_bind()
    if _dialect() == "sqlite":
        bind.exec_driver_sql("PRAGMA foreign_keys=OFF")
    tables = _table_names()

    # ---- conference_series identity & authority fields ---------------------
    series_columns = [
        sa.Column("english_name", sa.String(length=255), nullable=True),
        sa.Column("subdiscipline", sa.String(length=120), nullable=True),
        sa.Column("conference_frequency", sa.String(length=60), nullable=True),
        sa.Column("is_international", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("external_classifications", sa.JSON(), nullable=True),
        sa.Column("authority_status", sa.String(length=50), server_default="unverified", nullable=False),
        sa.Column("verification_status", sa.String(length=50), server_default="unverified", nullable=False),
        sa.Column("risk_flags", sa.JSON(), nullable=True),
        sa.Column("needs_review", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
    ]
    for column in series_columns:
        _add_column("conference_series", column)
    for column_name in ("is_international", "authority_status", "verification_status", "needs_review"):
        _add_index("conference_series", column_name)

    # ---- conference_sources (evidence) --------------------------------------
    if "conference_sources" not in tables:
        op.create_table(
            "conference_sources",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("conference_series_id", sa.Integer(), nullable=True),
            sa.Column("conference_edition_id", sa.Integer(), nullable=True),
            sa.Column("source_type", sa.String(length=80), nullable=False),
            sa.Column("authority_level", sa.String(length=4), nullable=True),
            sa.Column("source_name", sa.String(length=255), nullable=True),
            sa.Column("source_url", sa.String(length=1000), nullable=False),
            sa.Column("source_platform", sa.String(length=120), nullable=True),
            sa.Column("official_domain", sa.String(length=255), nullable=True),
            sa.Column("document_name", sa.String(length=500), nullable=True),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("is_official", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("is_verified", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("verification_status", sa.String(length=50), server_default="unverified", nullable=False),
            sa.Column("raw_title", sa.String(length=500), nullable=True),
            sa.Column("raw_content", sa.Text(), nullable=True),
            sa.Column("content_hash", sa.String(length=128), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["conference_series_id"], ["conference_series.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["conference_edition_id"], ["conference_editions.id"], ondelete="CASCADE"),
        )
    for column_name in (
        "conference_series_id",
        "conference_edition_id",
        "source_type",
        "authority_level",
        "source_platform",
        "official_domain",
        "is_verified",
        "verification_status",
        "content_hash",
    ):
        _add_index("conference_sources", column_name)

    # ---- conference_editions lifecycle/evidence fields -----------------------
    edition_columns = [
        sa.Column("edition_number", sa.Integer(), nullable=True),
        sa.Column("venue", sa.String(length=255), nullable=True),
        sa.Column("poster_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("workshop_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registration_url", sa.String(length=700), nullable=True),
        sa.Column("publication_status", sa.String(length=30), server_default="unknown", nullable=False),
        sa.Column("publication_details", sa.JSON(), nullable=True),
        sa.Column("indexing_claims", sa.JSON(), nullable=True),
        sa.Column("indexing_claim_status", sa.String(length=50), server_default="unknown", nullable=False),
        sa.Column("authority_status", sa.String(length=50), server_default="unverified", nullable=False),
        sa.Column("risk_flags", sa.JSON(), nullable=True),
        sa.Column("needs_review", sa.Boolean(), server_default=sa.false(), nullable=False),
    ]
    for column in edition_columns:
        _add_column("conference_editions", column)
    for column_name in ("publication_status", "indexing_claim_status", "authority_status", "needs_review"):
        _add_index("conference_editions", column_name)

    # Widen the original display column for full claim text (PostgreSQL only;
    # SQLite does not enforce VARCHAR lengths).
    if _dialect() != "sqlite" and "indexing_info" in _columns("conference_editions"):
        op.alter_column(
            "conference_editions",
            "indexing_info",
            existing_type=sa.String(length=255),
            type_=sa.Text(),
            existing_nullable=True,
        )

    # ---- school_conferences supplementary fields ----------------------------
    _add_column(
        "school_conferences",
        sa.Column("responsible_college", sa.String(length=255), nullable=True),
    )
    if "source_id" not in _columns("school_conferences"):
        if _dialect() == "sqlite":
            # SQLite dialect refuses ALTER ADD COLUMN with a FK through Alembic;
            # raw DDL is fine here because PRAGMA foreign_keys is disabled above
            # and the conference tables are empty.
            op.execute(
                "ALTER TABLE school_conferences ADD COLUMN source_id INTEGER "
                "REFERENCES conference_sources(id) ON DELETE SET NULL"
            )
        else:
            _add_column(
                "school_conferences",
                sa.Column(
                    "source_id",
                    sa.Integer(),
                    sa.ForeignKey("conference_sources.id", ondelete="SET NULL"),
                    nullable=True,
                ),
            )
    _add_column("school_conferences", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
    _add_index("school_conferences", "source_id")

    # ---- conference_organizations --------------------------------------------
    if "conference_organizations" not in tables:
        op.create_table(
            "conference_organizations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("conference_series_id", sa.Integer(), nullable=False),
            sa.Column("organization_id", sa.Integer(), nullable=False),
            sa.Column("role", sa.String(length=60), nullable=False),
            sa.Column("display_name", sa.String(length=255), nullable=True),
            sa.Column("is_verified", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("source_url", sa.String(length=1000), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["conference_series_id"],
                ["conference_series.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
            sa.UniqueConstraint(
                "conference_series_id",
                "organization_id",
                "role",
                name="uq_conference_organization_role",
            ),
        )
    for column_name in ("conference_series_id", "organization_id", "role"):
        _add_index("conference_organizations", column_name)

    # ---- conference_discovery_candidates --------------------------------------
    if "conference_discovery_candidates" not in tables:
        op.create_table(
            "conference_discovery_candidates",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("raw_name", sa.String(length=500), nullable=False),
            sa.Column("year", sa.Integer(), nullable=True),
            sa.Column("acronym", sa.String(length=120), nullable=True),
            sa.Column("english_name", sa.String(length=255), nullable=True),
            sa.Column("organizer_hint", sa.String(length=255), nullable=True),
            sa.Column("discipline_hint", sa.String(length=120), nullable=True),
            sa.Column("source_type", sa.String(length=80), nullable=False),
            sa.Column("source_name", sa.String(length=255), nullable=True),
            sa.Column("source_url", sa.String(length=1000), nullable=False),
            sa.Column("source_domain", sa.String(length=255), nullable=True),
            sa.Column("status", sa.String(length=40), server_default="pending", nullable=False),
            sa.Column("matched_series_id", sa.Integer(), nullable=True),
            sa.Column("matched_edition_id", sa.Integer(), nullable=True),
            sa.Column("duplicate_of_id", sa.Integer(), nullable=True),
            sa.Column("needs_review", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("risk_flags", sa.JSON(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("review_notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["matched_series_id"], ["conference_series.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["matched_edition_id"], ["conference_editions.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(
                ["duplicate_of_id"],
                ["conference_discovery_candidates.id"],
                ondelete="SET NULL",
            ),
        )
    for column_name in (
        "raw_name",
        "year",
        "source_type",
        "status",
        "matched_series_id",
        "matched_edition_id",
        "duplicate_of_id",
        "needs_review",
        "discovered_at",
    ):
        _add_index("conference_discovery_candidates", column_name)


def downgrade() -> None:
    bind = op.get_bind()
    if _dialect() == "sqlite":
        bind.exec_driver_sql("PRAGMA foreign_keys=OFF")
    tables = _table_names()
    for table in ("conference_discovery_candidates", "conference_organizations", "conference_sources"):
        if table in tables:
            op.drop_table(table)

    school_columns = _columns("school_conferences")
    for column_name in ("verified_at", "source_id", "responsible_college"):
        if column_name in school_columns:
            op.drop_column("school_conferences", column_name)

    if _dialect() != "sqlite":
        op.alter_column(
            "conference_editions",
            "indexing_info",
            existing_type=sa.Text(),
            type_=sa.String(length=255),
            existing_nullable=True,
        )
    edition_columns = _columns("conference_editions")
    for column_name in (
        "needs_review",
        "risk_flags",
        "authority_status",
        "indexing_claim_status",
        "indexing_claims",
        "publication_details",
        "publication_status",
        "registration_url",
        "workshop_deadline",
        "poster_deadline",
        "venue",
        "edition_number",
    ):
        if column_name in edition_columns:
            op.drop_column("conference_editions", column_name)

    series_columns = _columns("conference_series")
    for column_name in (
        "last_verified_at",
        "needs_review",
        "risk_flags",
        "verification_status",
        "authority_status",
        "external_classifications",
        "is_international",
        "conference_frequency",
        "subdiscipline",
        "english_name",
    ):
        if column_name in series_columns:
            op.drop_column("conference_series", column_name)
