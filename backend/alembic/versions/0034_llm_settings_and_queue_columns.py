"""llm settings and queue columns

Revision ID: 0034_llm_settings_queue
Revises: 0033_llm_verifications
Create Date: 2026-05-13 15:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0034_llm_settings_queue"
down_revision: str | None = "0033_llm_verifications"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "llm_settings",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column("llm_verifications", sa.Column("route_id", sa.Text(), nullable=True))
    op.add_column("llm_verifications", sa.Column("prompt", sa.Text(), nullable=True))
    op.add_column(
        "llm_verifications",
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("llm_verifications", sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column("llm_verifications", "attempts", server_default=None)


def downgrade() -> None:
    op.drop_column("llm_verifications", "claimed_at")
    op.drop_column("llm_verifications", "attempts")
    op.drop_column("llm_verifications", "prompt")
    op.drop_column("llm_verifications", "route_id")
    op.drop_table("llm_settings")
