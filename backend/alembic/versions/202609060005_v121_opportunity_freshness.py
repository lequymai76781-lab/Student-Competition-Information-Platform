"""Academic Conference V1.2.1 opportunity freshness & discovery entity types.

Additive V1.2.1 columns (no schema redesign):
- conference_opportunities.last_verified_at: when the row was last checked
  against an official source;
- conference_opportunities.status_hint: official wording ("open"/"upcoming")
  when the page states a live state but gives no deadline;
- conference_discovery_candidates.entity_type / metadata_json: mark a noisy
  find as a suspected series / edition / opportunity without creating a new
  table.

Revision ID: 202609060005
Revises: 202609060004
Create Date: 2026-09-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609060005"
down_revision: Union[str, None] = "202609060004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    opp_columns = _columns("conference_opportunities")
    if opp_columns:
        if "last_verified_at" not in opp_columns:
            op.add_column(
                "conference_opportunities",
                sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True, index=True),
            )
        if "status_hint" not in opp_columns:
            op.add_column(
                "conference_opportunities",
                sa.Column("status_hint", sa.String(20), nullable=True, index=True),
            )

    candidate_columns = _columns("conference_discovery_candidates")
    if candidate_columns:
        if "entity_type" not in candidate_columns:
            op.add_column(
                "conference_discovery_candidates",
                sa.Column(
                    "entity_type",
                    sa.String(60),
                    nullable=False,
                    server_default="conference_series",
                    index=True,
                ),
            )
        if "metadata_json" not in candidate_columns:
            op.add_column(
                "conference_discovery_candidates",
                sa.Column("metadata_json", sa.JSON(), nullable=True),
            )


def downgrade() -> None:
    candidate_columns = _columns("conference_discovery_candidates")
    if candidate_columns:
        if "metadata_json" in candidate_columns:
            op.drop_column("conference_discovery_candidates", "metadata_json")
        if "entity_type" in candidate_columns:
            op.drop_column("conference_discovery_candidates", "entity_type")
    opp_columns = _columns("conference_opportunities")
    if opp_columns:
        if "status_hint" in opp_columns:
            op.drop_column("conference_opportunities", "status_hint")
        if "last_verified_at" in opp_columns:
            op.drop_column("conference_opportunities", "last_verified_at")
