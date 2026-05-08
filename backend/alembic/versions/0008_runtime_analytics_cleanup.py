"""runtime analytics cleanup

Revision ID: 0008_runtime_analytics_cleanup
Revises: 0007_telegram_runtime
Create Date: 2026-05-08
"""

from __future__ import annotations

from alembic import op

revision: str = "0008_runtime_analytics_cleanup"
down_revision: str | None = "0007_telegram_runtime"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("delete from analytics_aggregates")
    op.execute("delete from analytics_candidates")
    op.execute("delete from analytics_runs")


def downgrade() -> None:
    pass
