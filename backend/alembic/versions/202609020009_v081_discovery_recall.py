"""V0.8.1 discovery recall - report metrics for multi-channel discovery

Revision ID: 202609020009
Revises: 202609020008
Create Date: 2026-09-02 09:30:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609020009"
down_revision: Union[str, None] = "202609020008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("university_competition_discovery_reports")}
    with op.batch_alter_table("university_competition_discovery_reports") as batch_op:
        if "methods_attempted" not in columns:
            batch_op.add_column(sa.Column("methods_attempted", sa.JSON(), nullable=True))
        if "methods_successful" not in columns:
            batch_op.add_column(sa.Column("methods_successful", sa.JSON(), nullable=True))
        if "pages_examined" not in columns:
            batch_op.add_column(sa.Column("pages_examined", sa.Integer(), server_default="0", nullable=False))
        if "candidate_articles" not in columns:
            batch_op.add_column(sa.Column("candidate_articles", sa.Integer(), server_default="0", nullable=False))
        if "internal_deadlines" not in columns:
            batch_op.add_column(sa.Column("internal_deadlines", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("university_competition_discovery_reports") as batch_op:
        for column in ("internal_deadlines", "candidate_articles", "pages_examined", "methods_successful", "methods_attempted"):
            try:
                batch_op.drop_column(column)
            except Exception:
                pass
