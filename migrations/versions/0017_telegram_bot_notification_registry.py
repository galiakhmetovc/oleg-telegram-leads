"""Add Telegram bot and notification group registry tables.

Revision ID: 0017_telegram_bot_notification_registry
Revises: 0016_ai_provider_agent_registry
Create Date: 2026-04-29
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision: str = "0017_telegram_bot_notification_registry"
down_revision: str | None = "0016_ai_provider_agent_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_bots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("telegram_bot_id", sa.String(80), nullable=True),
        sa.Column("telegram_username", sa.String(160), nullable=True),
        sa.Column("token_secret_ref", sa.String(36), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token_secret_ref", name="uq_telegram_bots_token_secret_ref"),
    )
    op.create_index("ix_telegram_bots_status", "telegram_bots", ["status"])
    op.create_index("ix_telegram_bots_username", "telegram_bots", ["telegram_username"])

    op.create_table(
        "telegram_notification_groups",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("telegram_bot_id", sa.String(36), nullable=False),
        sa.Column("chat_id", sa.String(120), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("chat_type", sa.String(64), nullable=True),
        sa.Column("message_thread_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["telegram_bot_id"], ["telegram_bots.id"]),
        sa.UniqueConstraint(
            "telegram_bot_id",
            "chat_id",
            "message_thread_id",
            name="uq_telegram_notification_groups_bot_chat_thread",
        ),
    )
    op.create_index(
        "ix_telegram_notification_groups_bot_status",
        "telegram_notification_groups",
        ["telegram_bot_id", "status"],
    )

    _backfill_legacy_settings()


def downgrade() -> None:
    op.drop_index(
        "ix_telegram_notification_groups_bot_status",
        table_name="telegram_notification_groups",
    )
    op.drop_table("telegram_notification_groups")
    op.drop_index("ix_telegram_bots_username", table_name="telegram_bots")
    op.drop_index("ix_telegram_bots_status", table_name="telegram_bots")
    op.drop_table("telegram_bots")


def _backfill_legacy_settings() -> None:
    connection = op.get_bind()
    settings = sa.table(
        "settings",
        sa.column("key", sa.String),
        sa.column("value_json", sa.JSON),
        sa.column("scope", sa.String),
        sa.column("scope_id", sa.String),
    )
    token_setting = connection.execute(
        sa.select(settings.c.value_json).where(
            settings.c.key == "telegram_bot_token_secret_ref",
            settings.c.scope == "global",
            settings.c.scope_id == "",
        )
    ).scalar_one_or_none()
    if not isinstance(token_setting, dict) or not token_setting.get("secret_ref_id"):
        return
    now = datetime.now(UTC)
    bot_id = str(uuid4())
    secret_id = str(token_setting["secret_ref_id"])
    connection.execute(
        sa.text(
            """
            INSERT INTO telegram_bots (
                id, display_name, telegram_bot_id, telegram_username, token_secret_ref,
                status, created_at, updated_at
            )
            VALUES (
                :id, :display_name, NULL, NULL, :token_secret_ref,
                'active', :created_at, :updated_at
            )
            """
        ),
        {
            "id": bot_id,
            "display_name": "Telegram bot",
            "token_secret_ref": secret_id,
            "created_at": now,
            "updated_at": now,
        },
    )
    chat_id = connection.execute(
        sa.select(settings.c.value_json).where(
            settings.c.key == "telegram_lead_notification_chat_id",
            settings.c.scope == "global",
            settings.c.scope_id == "",
        )
    ).scalar_one_or_none()
    if not chat_id:
        return
    thread_id = connection.execute(
        sa.select(settings.c.value_json).where(
            settings.c.key == "telegram_lead_notification_thread_id",
            settings.c.scope == "global",
            settings.c.scope_id == "",
        )
    ).scalar_one_or_none()
    connection.execute(
        sa.text(
            """
            INSERT INTO telegram_notification_groups (
                id, telegram_bot_id, chat_id, title, chat_type, message_thread_id,
                status, created_at, updated_at
            )
            VALUES (
                :id, :telegram_bot_id, :chat_id, :title, NULL, :message_thread_id,
                'active', :created_at, :updated_at
            )
            """
        ),
        {
            "id": str(uuid4()),
            "telegram_bot_id": bot_id,
            "chat_id": str(chat_id),
            "title": str(chat_id),
            "message_thread_id": thread_id if isinstance(thread_id, int) else None,
            "created_at": now,
            "updated_at": now,
        },
    )
