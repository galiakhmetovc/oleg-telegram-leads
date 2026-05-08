"""telegram ingestion and notification outbox

Revision ID: 0007_telegram_runtime
Revises: 0006_notification_settings
Create Date: 2026-05-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0007_telegram_runtime"
down_revision: str | None = "0006_notification_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_userbot_accounts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("api_id", sa.Integer(), nullable=False),
        sa.Column("api_hash", sa.Text(), nullable=True),
        sa.Column("session_string", sa.Text(), nullable=True),
        sa.Column("phone_code_hash", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("telegram_user_id", sa.Text(), nullable=True),
        sa.Column("telegram_username", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "telegram_source_chats",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("account_id", UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("input_ref", sa.Text(), nullable=False),
        sa.Column("telegram_chat_id", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("last_message_id", sa.BigInteger(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_telegram_source_chats_account_enabled",
        "telegram_source_chats",
        ["account_id", "enabled"],
    )
    op.create_table(
        "telegram_source_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("account_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source_chat_id", UUID(as_uuid=True), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=False),
        sa.Column("message_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sender_id", sa.Text(), nullable=True),
        sa.Column("sender_username", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("raw_payload", JSONB(), nullable=False),
        sa.Column("enrichment_job_id", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "source_chat_id",
            "telegram_message_id",
            name="uq_telegram_source_message",
        ),
    )
    op.create_index(
        "ix_telegram_source_messages_created_at",
        "telegram_source_messages",
        ["created_at"],
    )
    op.create_table(
        "notification_outbox",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("route_id", sa.Text(), nullable=False),
        sa.Column("bot_id", sa.Text(), nullable=False),
        sa.Column("chat_id", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_notification_outbox_status_created_at",
        "notification_outbox",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_notification_outbox_status_created_at", table_name="notification_outbox")
    op.drop_table("notification_outbox")
    op.drop_index("ix_telegram_source_messages_created_at", table_name="telegram_source_messages")
    op.drop_table("telegram_source_messages")
    op.drop_index("ix_telegram_source_chats_account_enabled", table_name="telegram_source_chats")
    op.drop_table("telegram_source_chats")
    op.drop_table("telegram_userbot_accounts")
