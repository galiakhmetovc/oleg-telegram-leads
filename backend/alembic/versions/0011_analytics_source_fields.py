"""analytics source fields

Revision ID: 0011_analytics_source_fields
Revises: 0010_pretty_notifications
Create Date: 2026-05-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_analytics_source_fields"
down_revision: str | None = "0010_pretty_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("analytics_candidates", sa.Column("received_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("analytics_candidates", sa.Column("source_chat_id", sa.Text(), nullable=True))
    op.add_column("analytics_candidates", sa.Column("source_chat_title", sa.Text(), nullable=True))
    op.create_index(
        "ix_analytics_candidates_run_source_chat",
        "analytics_candidates",
        ["run_id", "source_chat_id"],
    )
    op.create_index(
        "ix_analytics_candidates_run_received_at",
        "analytics_candidates",
        ["run_id", "received_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_analytics_candidates_run_received_at", table_name="analytics_candidates")
    op.drop_index("ix_analytics_candidates_run_source_chat", table_name="analytics_candidates")
    op.drop_column("analytics_candidates", "source_chat_title")
    op.drop_column("analytics_candidates", "source_chat_id")
    op.drop_column("analytics_candidates", "received_at")
