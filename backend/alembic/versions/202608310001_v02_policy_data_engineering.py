"""v0.2 policy data engineering

Revision ID: 202608310001
Revises: 202608300001
Create Date: 2026-08-31 00:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202608310001"
down_revision: Union[str, None] = "202608300001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())
    university_columns = {column["name"] for column in inspector.get_columns("universities")}
    if "policy_documents" in existing_tables and "english_name" in university_columns:
        return

    with op.batch_alter_table("universities") as batch_op:
        batch_op.add_column(sa.Column("english_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("aliases", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("official_domain", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("is_demo", sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.create_index("ix_universities_official_domain", ["official_domain"])

    with op.batch_alter_table("colleges") as batch_op:
        batch_op.add_column(sa.Column("official_website", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("official_domain", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("aliases", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("source_url", sa.String(length=700), nullable=True))
        batch_op.add_column(sa.Column("source_hash", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("is_verified", sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.add_column(sa.Column("is_demo", sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.create_index("ix_colleges_official_domain", ["official_domain"])
        batch_op.create_index("ix_colleges_source_hash", ["source_hash"])

    with op.batch_alter_table("majors") as batch_op:
        batch_op.add_column(sa.Column("aliases", sa.JSON(), nullable=True))

    op.create_table(
        "crawler_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_type", sa.String(length=80), nullable=False),
        sa.Column("target_type", sa.String(length=80), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("target_name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=40), server_default="pending", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pages_discovered", sa.Integer(), server_default="0", nullable=False),
        sa.Column("pages_fetched", sa.Integer(), server_default="0", nullable=False),
        sa.Column("documents_found", sa.Integer(), server_default="0", nullable=False),
        sa.Column("documents_parsed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("competitions_found", sa.Integer(), server_default="0", nullable=False),
        sa.Column("errors_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_crawler_jobs_job_type", "crawler_jobs", ["job_type"])
    op.create_index("ix_crawler_jobs_status", "crawler_jobs", ["status"])
    op.create_index("ix_crawler_jobs_target_id", "crawler_jobs", ["target_id"])
    op.create_index("ix_crawler_jobs_target_type", "crawler_jobs", ["target_type"])

    op.create_table(
        "policy_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("university_id", sa.Integer(), nullable=False),
        sa.Column("college_id", sa.Integer(), nullable=True),
        sa.Column("major_id", sa.Integer(), nullable=True),
        sa.Column("scope_type", sa.String(length=30), server_default="university", nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("policy_type", sa.String(length=80), server_default="other", nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("latest_available_year", sa.Integer(), nullable=True),
        sa.Column("publisher", sa.String(length=255), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("attachment_url", sa.String(length=1000), nullable=True),
        sa.Column("original_filename", sa.String(length=500), nullable=True),
        sa.Column("official_domain", sa.String(length=255), nullable=True),
        sa.Column("authority_level", sa.String(length=10), server_default="A2", nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("content_markdown", sa.Text(), nullable=True),
        sa.Column("document_hash", sa.String(length=128), nullable=True),
        sa.Column("is_current", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_verified", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("verification_status", sa.String(length=80), server_default="pending", nullable=False),
        sa.Column("crawler_job_id", sa.Integer(), nullable=True),
        sa.Column("parser_type", sa.String(length=80), nullable=True),
        sa.Column("source_type", sa.String(length=80), server_default="university", nullable=False),
        sa.Column("is_demo", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["college_id"], ["colleges.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["crawler_job_id"], ["crawler_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["major_id"], ["majors.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["university_id"], ["universities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_hash", name="uq_policy_documents_document_hash"),
        sa.UniqueConstraint("source_url", "attachment_url", name="uq_policy_documents_source_attachment"),
    )
    op.create_index("ix_policy_documents_authority_level", "policy_documents", ["authority_level"])
    op.create_index("ix_policy_documents_college_id", "policy_documents", ["college_id"])
    op.create_index("ix_policy_documents_document_hash", "policy_documents", ["document_hash"])
    op.create_index("ix_policy_documents_is_current", "policy_documents", ["is_current"])
    op.create_index("ix_policy_documents_is_demo", "policy_documents", ["is_demo"])
    op.create_index("ix_policy_documents_latest_available_year", "policy_documents", ["latest_available_year"])
    op.create_index("ix_policy_documents_major_id", "policy_documents", ["major_id"])
    op.create_index("ix_policy_documents_official_domain", "policy_documents", ["official_domain"])
    op.create_index("ix_policy_documents_policy_type", "policy_documents", ["policy_type"])
    op.create_index("ix_policy_documents_scope_type", "policy_documents", ["scope_type"])
    op.create_index("ix_policy_documents_source_type", "policy_documents", ["source_type"])
    op.create_index("ix_policy_documents_title", "policy_documents", ["title"])
    op.create_index("ix_policy_documents_university_id", "policy_documents", ["university_id"])
    op.create_index("ix_policy_documents_verification_status", "policy_documents", ["verification_status"])
    op.create_index("ix_policy_documents_year", "policy_documents", ["year"])

    op.create_table(
        "policy_attachments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("policy_document_id", sa.Integer(), nullable=True),
        sa.Column("crawler_job_id", sa.Integer(), nullable=True),
        sa.Column("university_id", sa.Integer(), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("filename", sa.String(length=500), nullable=True),
        sa.Column("content_type", sa.String(length=120), nullable=True),
        sa.Column("file_extension", sa.String(length=30), nullable=True),
        sa.Column("file_hash", sa.String(length=128), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("parse_status", sa.String(length=60), server_default="pending", nullable=False),
        sa.Column("parsed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("is_demo", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["crawler_job_id"], ["crawler_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["policy_document_id"], ["policy_documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["university_id"], ["universities.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_hash", name="uq_policy_attachments_file_hash"),
        sa.UniqueConstraint("source_url", name="uq_policy_attachments_source_url"),
    )
    op.create_index("ix_policy_attachments_file_extension", "policy_attachments", ["file_extension"])
    op.create_index("ix_policy_attachments_file_hash", "policy_attachments", ["file_hash"])
    op.create_index("ix_policy_attachments_is_demo", "policy_attachments", ["is_demo"])
    op.create_index("ix_policy_attachments_parse_status", "policy_attachments", ["parse_status"])
    op.create_index("ix_policy_attachments_university_id", "policy_attachments", ["university_id"])

    op.create_table(
        "competition_aliases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("competition_id", sa.Integer(), nullable=False),
        sa.Column("alias", sa.String(length=255), nullable=False),
        sa.Column("normalized_alias", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=80), server_default="manual", nullable=False),
        sa.Column("confidence", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("is_verified", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("competition_id", "alias", name="uq_competition_alias_competition_alias"),
    )
    op.create_index("ix_competition_aliases_alias", "competition_aliases", ["alias"])
    op.create_index("ix_competition_aliases_competition_id", "competition_aliases", ["competition_id"])
    op.create_index("ix_competition_aliases_is_demo", "competition_aliases", ["is_demo"])
    op.create_index("ix_competition_aliases_normalized_alias", "competition_aliases", ["normalized_alias"])

    op.create_table(
        "competition_policy_recognitions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("competition_id", sa.Integer(), nullable=False),
        sa.Column("policy_document_id", sa.Integer(), nullable=False),
        sa.Column("university_id", sa.Integer(), nullable=False),
        sa.Column("college_id", sa.Integer(), nullable=True),
        sa.Column("major_id", sa.Integer(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("recognition_status", sa.String(length=50), server_default="insufficient_evidence", nullable=False),
        sa.Column("recognition_level", sa.String(length=120), nullable=True),
        sa.Column("award_requirement", sa.String(length=255), nullable=True),
        sa.Column("usage_type", sa.String(length=80), server_default="other", nullable=False),
        sa.Column("score_text", sa.Text(), nullable=True),
        sa.Column("score_numeric", sa.Float(), nullable=True),
        sa.Column("rank_requirement", sa.String(length=255), nullable=True),
        sa.Column("evidence_text", sa.Text(), nullable=False),
        sa.Column("evidence_hash", sa.String(length=128), nullable=False),
        sa.Column("evidence_page", sa.Integer(), nullable=True),
        sa.Column("evidence_section", sa.String(length=255), nullable=True),
        sa.Column("confidence", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("needs_manual_review", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["college_id"], ["colleges.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["major_id"], ["majors.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["policy_document_id"], ["policy_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["university_id"], ["universities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "policy_document_id",
            "competition_id",
            "usage_type",
            "evidence_hash",
            name="uq_competition_policy_recognition_evidence",
        ),
    )
    op.create_index("ix_competition_policy_recognitions_college_id", "competition_policy_recognitions", ["college_id"])
    op.create_index("ix_competition_policy_recognitions_competition_id", "competition_policy_recognitions", ["competition_id"])
    op.create_index("ix_competition_policy_recognitions_confidence", "competition_policy_recognitions", ["confidence"])
    op.create_index("ix_competition_policy_recognitions_evidence_hash", "competition_policy_recognitions", ["evidence_hash"])
    op.create_index("ix_competition_policy_recognitions_is_demo", "competition_policy_recognitions", ["is_demo"])
    op.create_index("ix_competition_policy_recognitions_major_id", "competition_policy_recognitions", ["major_id"])
    op.create_index("ix_competition_policy_recognitions_needs_manual_review", "competition_policy_recognitions", ["needs_manual_review"])
    op.create_index("ix_competition_policy_recognitions_policy_document_id", "competition_policy_recognitions", ["policy_document_id"])
    op.create_index("ix_competition_policy_recognitions_recognition_status", "competition_policy_recognitions", ["recognition_status"])
    op.create_index("ix_competition_policy_recognitions_university_id", "competition_policy_recognitions", ["university_id"])
    op.create_index("ix_competition_policy_recognitions_usage_type", "competition_policy_recognitions", ["usage_type"])
    op.create_index("ix_competition_policy_recognitions_year", "competition_policy_recognitions", ["year"])

    op.create_table(
        "competition_statistics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("competition_id", sa.Integer(), nullable=False),
        sa.Column("university_985_recognition_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("college_985_recognition_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("policy_reference_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("latest_policy_year", sa.Integer(), nullable=True),
        sa.Column("official_source_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("verification_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("priority_score", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("competition_id"),
    )

    op.create_table(
        "review_queue",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_type", sa.String(length=80), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=True),
        sa.Column("university_id", sa.Integer(), nullable=True),
        sa.Column("college_id", sa.Integer(), nullable=True),
        sa.Column("major_id", sa.Integer(), nullable=True),
        sa.Column("policy_document_id", sa.Integer(), nullable=True),
        sa.Column("competition_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=60), server_default="pending", nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("raw_value", sa.Text(), nullable=True),
        sa.Column("suggested_value", sa.Text(), nullable=True),
        sa.Column("evidence_text", sa.Text(), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("assigned_to", sa.String(length=120), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewer_notes", sa.Text(), nullable=True),
        sa.Column("is_demo", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["college_id"], ["colleges.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["major_id"], ["majors.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["policy_document_id"], ["policy_documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["university_id"], ["universities.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_queue_college_id", "review_queue", ["college_id"])
    op.create_index("ix_review_queue_competition_id", "review_queue", ["competition_id"])
    op.create_index("ix_review_queue_is_demo", "review_queue", ["is_demo"])
    op.create_index("ix_review_queue_item_id", "review_queue", ["item_id"])
    op.create_index("ix_review_queue_item_type", "review_queue", ["item_type"])
    op.create_index("ix_review_queue_major_id", "review_queue", ["major_id"])
    op.create_index("ix_review_queue_policy_document_id", "review_queue", ["policy_document_id"])
    op.create_index("ix_review_queue_status", "review_queue", ["status"])
    op.create_index("ix_review_queue_university_id", "review_queue", ["university_id"])


def downgrade() -> None:
    op.drop_index("ix_review_queue_university_id", table_name="review_queue")
    op.drop_index("ix_review_queue_status", table_name="review_queue")
    op.drop_index("ix_review_queue_policy_document_id", table_name="review_queue")
    op.drop_index("ix_review_queue_major_id", table_name="review_queue")
    op.drop_index("ix_review_queue_item_type", table_name="review_queue")
    op.drop_index("ix_review_queue_item_id", table_name="review_queue")
    op.drop_index("ix_review_queue_is_demo", table_name="review_queue")
    op.drop_index("ix_review_queue_competition_id", table_name="review_queue")
    op.drop_index("ix_review_queue_college_id", table_name="review_queue")
    op.drop_table("review_queue")
    op.drop_table("competition_statistics")
    op.drop_index("ix_competition_policy_recognitions_year", table_name="competition_policy_recognitions")
    op.drop_index("ix_competition_policy_recognitions_usage_type", table_name="competition_policy_recognitions")
    op.drop_index("ix_competition_policy_recognitions_university_id", table_name="competition_policy_recognitions")
    op.drop_index("ix_competition_policy_recognitions_recognition_status", table_name="competition_policy_recognitions")
    op.drop_index("ix_competition_policy_recognitions_policy_document_id", table_name="competition_policy_recognitions")
    op.drop_index("ix_competition_policy_recognitions_needs_manual_review", table_name="competition_policy_recognitions")
    op.drop_index("ix_competition_policy_recognitions_major_id", table_name="competition_policy_recognitions")
    op.drop_index("ix_competition_policy_recognitions_is_demo", table_name="competition_policy_recognitions")
    op.drop_index("ix_competition_policy_recognitions_evidence_hash", table_name="competition_policy_recognitions")
    op.drop_index("ix_competition_policy_recognitions_confidence", table_name="competition_policy_recognitions")
    op.drop_index("ix_competition_policy_recognitions_competition_id", table_name="competition_policy_recognitions")
    op.drop_index("ix_competition_policy_recognitions_college_id", table_name="competition_policy_recognitions")
    op.drop_table("competition_policy_recognitions")
    op.drop_index("ix_competition_aliases_normalized_alias", table_name="competition_aliases")
    op.drop_index("ix_competition_aliases_is_demo", table_name="competition_aliases")
    op.drop_index("ix_competition_aliases_competition_id", table_name="competition_aliases")
    op.drop_index("ix_competition_aliases_alias", table_name="competition_aliases")
    op.drop_table("competition_aliases")
    op.drop_index("ix_policy_attachments_university_id", table_name="policy_attachments")
    op.drop_index("ix_policy_attachments_parse_status", table_name="policy_attachments")
    op.drop_index("ix_policy_attachments_is_demo", table_name="policy_attachments")
    op.drop_index("ix_policy_attachments_file_hash", table_name="policy_attachments")
    op.drop_index("ix_policy_attachments_file_extension", table_name="policy_attachments")
    op.drop_table("policy_attachments")
    op.drop_index("ix_policy_documents_year", table_name="policy_documents")
    op.drop_index("ix_policy_documents_verification_status", table_name="policy_documents")
    op.drop_index("ix_policy_documents_university_id", table_name="policy_documents")
    op.drop_index("ix_policy_documents_title", table_name="policy_documents")
    op.drop_index("ix_policy_documents_source_type", table_name="policy_documents")
    op.drop_index("ix_policy_documents_scope_type", table_name="policy_documents")
    op.drop_index("ix_policy_documents_policy_type", table_name="policy_documents")
    op.drop_index("ix_policy_documents_official_domain", table_name="policy_documents")
    op.drop_index("ix_policy_documents_major_id", table_name="policy_documents")
    op.drop_index("ix_policy_documents_latest_available_year", table_name="policy_documents")
    op.drop_index("ix_policy_documents_is_demo", table_name="policy_documents")
    op.drop_index("ix_policy_documents_is_current", table_name="policy_documents")
    op.drop_index("ix_policy_documents_document_hash", table_name="policy_documents")
    op.drop_index("ix_policy_documents_college_id", table_name="policy_documents")
    op.drop_index("ix_policy_documents_authority_level", table_name="policy_documents")
    op.drop_table("policy_documents")
    op.drop_index("ix_crawler_jobs_target_type", table_name="crawler_jobs")
    op.drop_index("ix_crawler_jobs_target_id", table_name="crawler_jobs")
    op.drop_index("ix_crawler_jobs_status", table_name="crawler_jobs")
    op.drop_index("ix_crawler_jobs_job_type", table_name="crawler_jobs")
    op.drop_table("crawler_jobs")

    with op.batch_alter_table("majors") as batch_op:
        batch_op.drop_column("aliases")
    with op.batch_alter_table("colleges") as batch_op:
        batch_op.drop_index("ix_colleges_source_hash")
        batch_op.drop_index("ix_colleges_official_domain")
        batch_op.drop_column("is_demo")
        batch_op.drop_column("is_verified")
        batch_op.drop_column("source_hash")
        batch_op.drop_column("source_url")
        batch_op.drop_column("aliases")
        batch_op.drop_column("official_domain")
        batch_op.drop_column("official_website")
    with op.batch_alter_table("universities") as batch_op:
        batch_op.drop_index("ix_universities_official_domain")
        batch_op.drop_column("is_demo")
        batch_op.drop_column("official_domain")
        batch_op.drop_column("aliases")
        batch_op.drop_column("english_name")
