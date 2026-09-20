"""V0.9 data-architecture foundation

Additive, non-destructive:

- competition_editions: host_location / edition_rules_url / edition_status
- competition_leads: review_status state machine (pending/matched/verified/...)
- organizations + competition_organizations: unified institutional registry
- conference_series / conference_editions / school_conferences: conference
  base schema (no fake data, no UI)

Revision ID: 202609040001
Revises: 202609020012
Create Date: 2026-09-04 10:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609040001"
down_revision: Union[str, None] = "202609020012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    edition_columns = {column["name"] for column in inspector.get_columns("competition_editions")}
    with op.batch_alter_table("competition_editions") as batch_op:
        if "host_location" not in edition_columns:
            batch_op.add_column(sa.Column("host_location", sa.String(length=255), nullable=True))
        if "edition_rules_url" not in edition_columns:
            batch_op.add_column(sa.Column("edition_rules_url", sa.String(length=1000), nullable=True))
        if "edition_status" not in edition_columns:
            batch_op.add_column(
                sa.Column("edition_status", sa.String(length=40), server_default="unknown", nullable=False)
            )
        indexes = {index["name"] for index in inspector.get_indexes("competition_editions")}
        if "ix_competition_editions_edition_status" not in indexes:
            batch_op.create_index("ix_competition_editions_edition_status", ["edition_status"])

    lead_columns = {column["name"] for column in inspector.get_columns("competition_leads")}
    with op.batch_alter_table("competition_leads") as batch_op:
        if "review_status" not in lead_columns:
            batch_op.add_column(
                sa.Column("review_status", sa.String(length=40), server_default="pending", nullable=False)
            )
        indexes = {index["name"] for index in inspector.get_indexes("competition_leads")}
        if "ix_competition_leads_review_status" not in indexes:
            batch_op.create_index("ix_competition_leads_review_status", ["review_status"])

    if "organizations" not in tables:
        op.create_table(
            "organizations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("aliases", sa.JSON(), nullable=True),
            sa.Column("org_type", sa.String(length=60), server_default="other", nullable=False),
            sa.Column("country_or_region", sa.String(length=120), nullable=True),
            sa.Column("official_website", sa.String(length=500), nullable=True),
            sa.Column("official_domain", sa.String(length=255), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=40), server_default="active", nullable=False),
            sa.Column("is_verified", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("is_demo", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("name", name="uq_organizations_name"),
        )
        for column in ("id", "name", "org_type", "official_domain", "status"):
            op.create_index(f"ix_organizations_{column}", "organizations", [column])

    if "competition_organizations" not in tables:
        op.create_table(
            "competition_organizations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("competition_id", sa.Integer(), nullable=False),
            sa.Column("organization_id", sa.Integer(), nullable=False),
            sa.Column("role", sa.String(length=40), nullable=False),
            sa.Column("display_name", sa.String(length=255), nullable=True),
            sa.Column("is_verified", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("source_url", sa.String(length=1000), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
            sa.UniqueConstraint(
                "competition_id",
                "organization_id",
                "role",
                name="uq_competition_organization_role",
            ),
        )
        for column in (
            "id",
            "competition_id",
            "organization_id",
            "role",
            "is_verified",
        ):
            op.create_index(f"ix_competition_organizations_{column}", "competition_organizations", [column])

    if "conference_series" not in tables:
        op.create_table(
            "conference_series",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("short_name", sa.String(length=120), nullable=True),
            sa.Column("aliases", sa.JSON(), nullable=True),
            sa.Column("discipline", sa.String(length=120), nullable=True),
            sa.Column("organizer_summary", sa.Text(), nullable=True),
            sa.Column("official_website", sa.String(length=500), nullable=True),
            sa.Column("first_held_year", sa.Integer(), nullable=True),
            sa.Column("conference_scope", sa.String(length=120), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=40), server_default="active", nullable=False),
            sa.Column("is_verified", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("is_demo", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("name", name="uq_conference_series_name"),
        )
        for column in ("id", "name", "discipline", "status"):
            op.create_index(f"ix_conference_series_{column}", "conference_series", [column])

    if "conference_editions" not in tables:
        op.create_table(
            "conference_editions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("conference_series_id", sa.Integer(), nullable=False),
            sa.Column("year", sa.Integer(), nullable=False),
            sa.Column("edition_name", sa.String(length=255), nullable=True),
            sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("location", sa.String(length=255), nullable=True),
            sa.Column("country_or_region", sa.String(length=120), nullable=True),
            sa.Column("city", sa.String(length=120), nullable=True),
            sa.Column("online_status", sa.String(length=40), nullable=True),
            sa.Column("abstract_deadline", sa.DateTime(timezone=True), nullable=True),
            sa.Column("paper_deadline", sa.DateTime(timezone=True), nullable=True),
            sa.Column("notification_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("camera_ready_deadline", sa.DateTime(timezone=True), nullable=True),
            sa.Column("registration_deadline", sa.DateTime(timezone=True), nullable=True),
            sa.Column("call_for_papers_url", sa.String(length=700), nullable=True),
            sa.Column("edition_official_url", sa.String(length=700), nullable=True),
            sa.Column("publication_info", sa.Text(), nullable=True),
            sa.Column("indexing_info", sa.String(length=255), nullable=True),
            sa.Column("submission_language", sa.String(length=80), nullable=True),
            sa.Column("participation_type", sa.String(length=120), nullable=True),
            sa.Column("edition_status", sa.String(length=40), server_default="unknown", nullable=False),
            sa.Column("source_url", sa.String(length=1000), nullable=True),
            sa.Column("is_verified", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("verification_status", sa.String(length=50), server_default="unverified", nullable=False),
            sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["conference_series_id"], ["conference_series.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("conference_series_id", "year", name="uq_conference_series_year"),
        )
        for column in (
            "id",
            "conference_series_id",
            "year",
            "paper_deadline",
            "registration_deadline",
            "edition_status",
            "is_verified",
            "verification_status",
        ):
            op.create_index(f"ix_conference_editions_{column}", "conference_editions", [column])

    if "school_conferences" not in tables:
        op.create_table(
            "school_conferences",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("school_id", sa.Integer(), nullable=False),
            sa.Column("conference_series_id", sa.Integer(), nullable=True),
            sa.Column("conference_edition_id", sa.Integer(), nullable=True),
            sa.Column("relation_type", sa.String(length=60), server_default="other", nullable=False),
            sa.Column("responsible_department", sa.String(length=255), nullable=True),
            sa.Column("notice_url", sa.String(length=1000), nullable=True),
            sa.Column("campus_deadline", sa.DateTime(timezone=True), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("is_verified", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("verification_status", sa.String(length=50), server_default="unverified", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["school_id"], ["universities.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["conference_series_id"],
                ["conference_series.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["conference_edition_id"],
                ["conference_editions.id"],
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint(
                "school_id",
                "conference_edition_id",
                "notice_url",
                name="uq_school_conference_edition_notice",
            ),
        )
        for column in (
            "id",
            "school_id",
            "conference_series_id",
            "conference_edition_id",
            "relation_type",
            "verification_status",
        ):
            op.create_index(f"ix_school_conferences_{column}", "school_conferences", [column])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table in ("school_conferences", "conference_editions", "conference_series"):
        if table in tables:
            op.drop_table(table)
    if "competition_organizations" in tables:
        op.drop_table("competition_organizations")
    if "organizations" in tables:
        op.drop_table("organizations")

    with op.batch_alter_table("competition_leads") as batch_op:
        indexes = {index["name"] for index in inspector.get_indexes("competition_leads")}
        if "ix_competition_leads_review_status" in indexes:
            batch_op.drop_index("ix_competition_leads_review_status")
        columns = {column["name"] for column in inspector.get_columns("competition_leads")}
        if "review_status" in columns:
            batch_op.drop_column("review_status")

    with op.batch_alter_table("competition_editions") as batch_op:
        indexes = {index["name"] for index in inspector.get_indexes("competition_editions")}
        if "ix_competition_editions_edition_status" in indexes:
            batch_op.drop_index("ix_competition_editions_edition_status")
        columns = {column["name"] for column in inspector.get_columns("competition_editions")}
        for column in ("edition_status", "edition_rules_url", "host_location"):
            if column in columns:
                batch_op.drop_column(column)
