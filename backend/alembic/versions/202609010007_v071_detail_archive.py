"""V0.7.1 competition detail archive fields

Revision ID: 202609010007
Revises: 202609010006
Create Date: 2026-09-01 23:20:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609010007"
down_revision: Union[str, None] = "202609010006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("competitions")}
    with op.batch_alter_table("competitions") as batch_op:
        for name in (
            "history_timeline",
            "participation_requirements",
            "competition_process",
            "submission_requirements",
            "award_settings",
        ):
            if name not in columns:
                batch_op.add_column(sa.Column(name, sa.JSON(), nullable=True))
        if "detail_ready" not in columns:
            batch_op.add_column(sa.Column("detail_ready", sa.Boolean(), server_default=sa.false(), nullable=False))
            batch_op.create_index("ix_competitions_detail_ready", ["detail_ready"])


def downgrade() -> None:
    with op.batch_alter_table("competitions") as batch_op:
        try:
            batch_op.drop_index("ix_competitions_detail_ready")
        except Exception:
            pass
        for name in (
            "detail_ready",
            "award_settings",
            "submission_requirements",
            "competition_process",
            "participation_requirements",
            "history_timeline",
        ):
            try:
                batch_op.drop_column(name)
            except Exception:
                pass
