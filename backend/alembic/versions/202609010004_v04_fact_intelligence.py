"""V0.4 competition discovery and fact intelligence

Revision ID: 202609010004
Revises: 202608310003
Create Date: 2026-09-01 00:20:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609010004"
down_revision: Union[str, None] = "202608310003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    competition_columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("competitions")}
    with op.batch_alter_table("competitions") as batch_op:
        _add(batch_op, competition_columns, "former_names", sa.JSON())
        _add(batch_op, competition_columns, "co_organizers", sa.JSON())
        _add(batch_op, competition_columns, "guiding_organizations", sa.JSON())
        _add(batch_op, competition_columns, "official_account", sa.String(length=255))
        _add(batch_op, competition_columns, "founded_year", sa.Integer())
        _add(batch_op, competition_columns, "first_held_year", sa.Integer())
        _add(batch_op, competition_columns, "frequency", sa.String(length=80))
        _add(batch_op, competition_columns, "edition_count", sa.Integer())
        _add(batch_op, competition_columns, "competition_format", sa.String(length=120))
        _add(batch_op, competition_columns, "competition_scope", sa.String(length=120))
        _add(batch_op, competition_columns, "country_or_region", sa.String(length=120))
        if "crawl_priority" not in competition_columns:
            batch_op.add_column(sa.Column("crawl_priority", sa.Float(), server_default="0.0", nullable=False))
            batch_op.create_index("ix_competitions_crawl_priority", ["crawl_priority"])
        if "is_competition" not in competition_columns:
            batch_op.add_column(sa.Column("is_competition", sa.Boolean(), server_default=sa.true(), nullable=False))
            batch_op.create_index("ix_competitions_is_competition", ["is_competition"])
        if "entity_type" not in competition_columns:
            batch_op.add_column(
                sa.Column("entity_type", sa.String(length=50), server_default="competition", nullable=False)
            )
            batch_op.create_index("ix_competitions_entity_type", ["entity_type"])
        if "verification_status" not in competition_columns:
            batch_op.add_column(
                sa.Column("verification_status", sa.String(length=50), server_default="unverified", nullable=False)
            )
            batch_op.create_index("ix_competitions_verification_status", ["verification_status"])
        if "founded_year" not in competition_columns:
            batch_op.create_index("ix_competitions_founded_year", ["founded_year"])

    edition_columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("competition_editions")}
    with op.batch_alter_table("competition_editions") as batch_op:
        _add(batch_op, edition_columns, "edition_number", sa.Integer())
        _add(batch_op, edition_columns, "registration_fee", sa.Float())
        _add(batch_op, edition_columns, "fee_notes", sa.Text())
        if "verification_status" not in edition_columns:
            batch_op.add_column(
                sa.Column("verification_status", sa.String(length=50), server_default="unverified", nullable=False)
            )
            batch_op.create_index("ix_competition_editions_verification_status", ["verification_status"])

    source_columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("competition_sources")}
    with op.batch_alter_table("competition_sources") as batch_op:
        _add(batch_op, source_columns, "source_commit", sa.String(length=80))
        _add(batch_op, source_columns, "retrieved_at", sa.DateTime(timezone=True))
        if "reliability_tier" not in source_columns:
            batch_op.add_column(sa.Column("reliability_tier", sa.Integer(), server_default="3", nullable=False))
            batch_op.create_index("ix_competition_sources_reliability_tier", ["reliability_tier"])
        if "verification_status" not in source_columns:
            batch_op.add_column(
                sa.Column("verification_status", sa.String(length=50), server_default="unverified", nullable=False)
            )
            batch_op.create_index("ix_competition_sources_verification_status", ["verification_status"])

    op.create_table(
        "competition_leads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("raw_title", sa.String(length=700), nullable=False),
        sa.Column("raw_content", sa.Text(), nullable=True),
        sa.Column("detected_competition_name", sa.String(length=500), nullable=True),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("source_platform", sa.String(length=80), nullable=True),
        sa.Column("source_name", sa.String(length=255), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("author", sa.String(length=255), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("possible_year", sa.Integer(), nullable=True),
        sa.Column("possible_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("possible_organizer", sa.String(length=500), nullable=True),
        sa.Column("classification", sa.String(length=80), server_default="unknown", nullable=False),
        sa.Column("verification_status", sa.String(length=50), server_default="unverified", nullable=False),
        sa.Column("matched_competition_id", sa.Integer(), sa.ForeignKey("competitions.id", ondelete="SET NULL")),
        sa.Column("matched_edition_id", sa.Integer(), sa.ForeignKey("competition_editions.id", ondelete="SET NULL")),
        sa.Column("needs_review", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_url", "raw_title", name="uq_competition_lead_source_title"),
    )
    for column in (
        "id", "raw_title", "detected_competition_name", "source_type", "source_platform", "published_at",
        "discovered_at", "possible_year", "classification", "verification_status", "matched_competition_id",
        "matched_edition_id", "needs_review", "content_hash",
    ):
        op.create_index(f"ix_competition_leads_{column}", "competition_leads", [column])

    op.create_table(
        "policy_raw_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("policy_document_id", sa.Integer(), sa.ForeignKey("policy_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("raw_name", sa.String(length=500), nullable=False),
        sa.Column("raw_level", sa.String(length=120), nullable=True),
        sa.Column("raw_order", sa.Integer(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.String(length=50), server_default="unknown", nullable=False),
        sa.Column("normalized_competition_id", sa.Integer(), sa.ForeignKey("competitions.id", ondelete="SET NULL")),
        sa.Column("confidence", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("needs_manual_review", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("classification_reason", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("policy_document_id", "raw_order", "raw_name", name="uq_policy_raw_item_order_name"),
    )
    for column in ("id", "policy_document_id", "raw_name", "entity_type", "normalized_competition_id", "needs_manual_review"):
        op.create_index(f"ix_policy_raw_items_{column}", "policy_raw_items", [column])

    op.create_table(
        "competition_fact_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("competition_id", sa.Integer(), sa.ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("competition_edition_id", sa.Integer(), sa.ForeignKey("competition_editions.id", ondelete="CASCADE")),
        sa.Column("field_name", sa.String(length=120), nullable=False),
        sa.Column("fact_value", sa.JSON(), nullable=True),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("reliability_tier", sa.Integer(), nullable=False),
        sa.Column("is_official", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("verification_status", sa.String(length=50), server_default="unverified", nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "competition_id", "competition_edition_id", "field_name", "source_url",
            name="uq_competition_fact_source_field_url",
        ),
    )
    for column in ("id", "competition_id", "competition_edition_id", "field_name", "source_type", "reliability_tier", "is_official", "verification_status"):
        op.create_index(f"ix_competition_fact_sources_{column}", "competition_fact_sources", [column])

    op.create_table(
        "candidate_facts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("competition_leads.id", ondelete="CASCADE")),
        sa.Column("competition_id", sa.Integer(), sa.ForeignKey("competitions.id", ondelete="SET NULL")),
        sa.Column("competition_edition_id", sa.Integer(), sa.ForeignKey("competition_editions.id", ondelete="SET NULL")),
        sa.Column("field_name", sa.String(length=120), nullable=False),
        sa.Column("candidate_value", sa.JSON(), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("reliability_tier", sa.Integer(), nullable=False),
        sa.Column("verification_status", sa.String(length=50), server_default="unverified", nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("needs_review", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("conflict_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("lead_id", "field_name", "source_url", name="uq_candidate_fact_lead_field_url"),
    )
    for column in ("id", "lead_id", "competition_id", "competition_edition_id", "field_name", "source_type", "reliability_tier", "verification_status", "needs_review"):
        op.create_index(f"ix_candidate_facts_{column}", "candidate_facts", [column])


def _add(batch_op: object, columns: set[str], name: str, column_type: sa.types.TypeEngine) -> None:
    if name not in columns:
        batch_op.add_column(sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    op.drop_table("candidate_facts")
    op.drop_table("competition_fact_sources")
    op.drop_table("policy_raw_items")
    op.drop_table("competition_leads")

    with op.batch_alter_table("competition_sources") as batch_op:
        batch_op.drop_index("ix_competition_sources_verification_status")
        batch_op.drop_index("ix_competition_sources_reliability_tier")
        for column in ("verification_status", "reliability_tier", "retrieved_at", "source_commit"):
            batch_op.drop_column(column)
    with op.batch_alter_table("competition_editions") as batch_op:
        batch_op.drop_index("ix_competition_editions_verification_status")
        for column in ("verification_status", "fee_notes", "registration_fee", "edition_number"):
            batch_op.drop_column(column)
    with op.batch_alter_table("competitions") as batch_op:
        batch_op.drop_index("ix_competitions_verification_status")
        batch_op.drop_index("ix_competitions_entity_type")
        batch_op.drop_index("ix_competitions_is_competition")
        batch_op.drop_index("ix_competitions_crawl_priority")
        batch_op.drop_index("ix_competitions_founded_year")
        for column in (
            "verification_status", "entity_type", "is_competition", "crawl_priority", "country_or_region",
            "competition_scope", "competition_format", "edition_count", "frequency", "first_held_year",
            "founded_year", "official_account", "guiding_organizations", "co_organizers", "former_names",
        ):
            batch_op.drop_column(column)

