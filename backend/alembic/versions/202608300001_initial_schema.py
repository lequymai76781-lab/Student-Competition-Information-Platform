"""initial schema

Revision ID: 202608300001
Revises:
Create Date: 2026-08-30 00:00:00
"""
from typing import Sequence, Union

from alembic import op

from app.database.base import Base

revision: str = "202608300001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    initial_tables = {
        "colleges",
        "competition_editions",
        "competition_sources",
        "competition_tags",
        "competitions",
        "favorites",
        "majors",
        "recommendations",
        "tags",
        "universities",
        "university_competition_policies",
        "university_policies",
        "user_profiles",
        "users",
    }
    tables = [table for table in Base.metadata.sorted_tables if table.name in initial_tables]
    Base.metadata.create_all(bind=op.get_bind(), tables=tables)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
