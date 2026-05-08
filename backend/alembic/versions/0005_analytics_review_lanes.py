"""analytics review lanes

Revision ID: 0005_analytics_review_lanes
Revises: 0004_analytics_filter_indexes
Create Date: 2026-05-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_analytics_review_lanes"
down_revision: str | None = "0004_analytics_filter_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "analytics_candidates",
        sa.Column("review_lane", sa.Text(), nullable=False, server_default="other_candidate"),
    )
    op.create_index(
        "ix_analytics_candidates_run_review_lane",
        "analytics_candidates",
        ["run_id", "review_lane"],
    )


def downgrade() -> None:
    op.drop_index("ix_analytics_candidates_run_review_lane", table_name="analytics_candidates")
    op.drop_column("analytics_candidates", "review_lane")
