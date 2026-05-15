"""lead handling bot

Revision ID: 0035_lead_handling_bot
Revises: 0034_llm_settings_queue
Create Date: 2026-05-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0035_lead_handling_bot"
down_revision: str | None = "0034_llm_settings_queue"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "lead_handlings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notification_outbox_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sales_chat_id", sa.Text(), nullable=True),
        sa.Column("sales_chat_message_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("owner_telegram_user_id", sa.Text(), nullable=True),
        sa.Column("owner_telegram_username", sa.Text(), nullable=True),
        sa.Column("owner_display_name", sa.Text(), nullable=True),
        sa.Column("last_comment", sa.Text(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_message_id"],
            ["telegram_source_messages.id"],
            name="fk_lead_handlings_source_message",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["notification_outbox_id"],
            ["notification_outbox.id"],
            name="fk_lead_handlings_notification_outbox",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("source_message_id", name="uq_lead_handlings_source_message"),
        sa.CheckConstraint(
            "status IN ('new', 'claimed', 'contacted', 'waiting', 'closed', 'not_lead')",
            name="ck_lead_handlings_status",
        ),
    )
    op.create_index("ix_lead_handlings_owner_status", "lead_handlings", ["owner_telegram_user_id", "status"])
    op.create_table(
        "lead_handling_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lead_handling_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_telegram_user_id", sa.Text(), nullable=True),
        sa.Column("actor_telegram_username", sa.Text(), nullable=True),
        sa.Column("actor_display_name", sa.Text(), nullable=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["lead_handling_id"],
            ["lead_handlings.id"],
            name="fk_lead_handling_events_handling",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_message_id"],
            ["telegram_source_messages.id"],
            name="fk_lead_handling_events_source_message",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_lead_handling_events_source_created",
        "lead_handling_events",
        ["source_message_id", "created_at"],
    )
    op.create_table(
        "lead_bot_sessions",
        sa.Column("bot_id", sa.Text(), nullable=False),
        sa.Column("telegram_user_id", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("bot_id", "telegram_user_id", name="pk_lead_bot_sessions"),
    )


def downgrade() -> None:
    op.drop_table("lead_bot_sessions")
    op.drop_index("ix_lead_handling_events_source_created", table_name="lead_handling_events")
    op.drop_table("lead_handling_events")
    op.drop_index("ix_lead_handlings_owner_status", table_name="lead_handlings")
    op.drop_table("lead_handlings")
