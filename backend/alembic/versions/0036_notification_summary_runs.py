"""notification summary runs

Revision ID: 0036_notification_summary_runs
Revises: 0035_lead_handling_bot
Create Date: 2026-05-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0036_notification_summary_runs"
down_revision: str | None = "0035_lead_handling_bot"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "notification_summary_runs",
        sa.Column("period_kind", sa.Text(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bot_id", sa.Text(), nullable=False),
        sa.Column("chat_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint(
            "period_kind",
            "period_start",
            "period_end",
            "bot_id",
            "chat_id",
            name="pk_notification_summary_runs",
        ),
        sa.CheckConstraint(
            "period_kind IN ('day', 'night')",
            name="ck_notification_summary_runs_period_kind",
        ),
        sa.CheckConstraint(
            "status IN ('sending', 'sent', 'failed')",
            name="ck_notification_summary_runs_status",
        ),
    )


def downgrade() -> None:
    op.drop_table("notification_summary_runs")
