"""Academic Conference V1.1 edition notes column.

V1/V1.1 curated Edition payloads carry `notes` (official date/wording
discrepancies, sub-event splits and evidence nuances). Add a nullable Text
column so the importer can persist them instead of silently dropping them.
Conference-only change; no competition tables are touched.

Revision ID: 202609060003
Revises: 202609060002
Create Date: 2026-09-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609060003"
down_revision: Union[str, None] = "202609060002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("conference_editions")}
    if "notes" not in columns:
        op.add_column("conference_editions", sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("conference_editions")}
    if "notes" in columns:
        op.drop_column("conference_editions", "notes")
