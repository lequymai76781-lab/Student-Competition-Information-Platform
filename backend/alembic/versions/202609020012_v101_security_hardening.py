"""V1.0.1 security hardening: admin audit log + beta metrics

Revision ID: 202609020012
Revises: 202609020011
Create Date: 2026-09-03 09:30:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609020012"
down_revision: Union[str, None] = "202609020011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    tables = {name for name in sa.inspect(op.get_bind()).get_table_names()}
    if "admin_audit_logs" not in tables:
        op.create_table(
            "admin_audit_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("admin_id", sa.Integer(), nullable=True),
            sa.Column("action", sa.String(length=80), nullable=False),
            sa.Column("object_type", sa.String(length=80), nullable=False),
            sa.Column("object_id", sa.Integer(), nullable=True),
            sa.Column("before", sa.JSON(), nullable=True),
            sa.Column("after", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["admin_id"], ["users.id"], ondelete="SET NULL"),
        )
        for column in ("id", "admin_id", "action", "object_type", "created_at"):
            op.create_index(f"ix_admin_audit_logs_{column}", "admin_audit_logs", [column])
    if "beta_metrics" not in tables:
        op.create_table(
            "beta_metrics",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event", sa.String(length=60), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        )
        for column in ("id", "event", "user_id", "created_at"):
            op.create_index(f"ix_beta_metrics_{column}", "beta_metrics", [column])


def downgrade() -> None:
    tables = {name for name in sa.inspect(op.get_bind()).get_table_names()}
    if "beta_metrics" in tables:
        op.drop_table("beta_metrics")
    if "admin_audit_logs" in tables:
        op.drop_table("admin_audit_logs")
