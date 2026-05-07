"""analytics candidate filter indexes

Revision ID: 0004_analytics_filter_indexes
Revises: 0003_analytics
Create Date: 2026-05-07
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_analytics_filter_indexes"
down_revision: str | None = "0003_analytics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_analytics_candidates_reason_keys",
        "analytics_candidates",
        ["reason_keys"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_analytics_candidates_solution_area_types",
        "analytics_candidates",
        ["solution_area_types"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_analytics_candidates_customer_segment_types",
        "analytics_candidates",
        ["customer_segment_types"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_analytics_candidates_customer_segment_types", table_name="analytics_candidates")
    op.drop_index("ix_analytics_candidates_solution_area_types", table_name="analytics_candidates")
    op.drop_index("ix_analytics_candidates_reason_keys", table_name="analytics_candidates")
