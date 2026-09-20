"""V0.9 user competition status

Revision ID: 202609020010
Revises: 202609020009
Create Date: 2026-09-02 18:20:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609020010"
down_revision: Union[str, None] = "202609020009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    profile_columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("user_profiles")
    }
    with op.batch_alter_table("user_profiles") as batch_op:
        if "university_name" not in profile_columns:
            batch_op.add_column(sa.Column("university_name", sa.String(length=255), nullable=True))
        if "college_name" not in profile_columns:
            batch_op.add_column(sa.Column("college_name", sa.String(length=255), nullable=True))
        if "major_name" not in profile_columns:
            batch_op.add_column(sa.Column("major_name", sa.String(length=255), nullable=True))
    if not sa.inspect(op.get_bind()).has_table("user_competition_statuses"):
        op.create_table(
            "user_competition_statuses",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("competition_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=40), server_default="interested", nullable=False),
            sa.Column("notes", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("user_id", "competition_id", name="uq_user_competition_status"),
        )
        for column in ("id", "user_id", "competition_id", "status"):
            op.create_index(f"ix_user_competition_statuses_{column}", "user_competition_statuses", [column])


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("user_competition_statuses"):
        op.drop_table("user_competition_statuses")
    with op.batch_alter_table("user_profiles") as batch_op:
        for column in ("major_name", "college_name", "university_name"):
            try:
                batch_op.drop_column(column)
            except Exception:
                pass
