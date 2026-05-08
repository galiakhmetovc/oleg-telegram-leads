"""notification settings

Revision ID: 0006_notification_settings
Revises: 0005_analytics_review_lanes
Create Date: 2026-05-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0006_notification_settings"
down_revision: str | None = "0005_analytics_review_lanes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_settings",
        sa.Column("channel", sa.Text(), primary_key=True),
        sa.Column("config", JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("notification_settings")
