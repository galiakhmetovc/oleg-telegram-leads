"""message reviews

Revision ID: 0013_message_reviews
Revises: 0012_userbot_cooldown
Create Date: 2026-05-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_message_reviews"
down_revision: str | None = "0012_userbot_cooldown"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "message_reviews",
        sa.Column("source_message_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("verdict", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("message_reviews")
