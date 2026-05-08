"""userbot cooldown

Revision ID: 0012_userbot_cooldown
Revises: 0011_analytics_source_fields
Create Date: 2026-05-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_userbot_cooldown"
down_revision: str | None = "0011_analytics_source_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "telegram_userbot_accounts",
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("telegram_userbot_accounts", "cooldown_until")
