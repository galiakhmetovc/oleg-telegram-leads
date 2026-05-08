"""runtime log indexes

Revision ID: 0009_runtime_log_indexes
Revises: 0008_runtime_analytics_cleanup
Create Date: 2026-05-08
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009_runtime_log_indexes"
down_revision: str | None = "0008_runtime_analytics_cleanup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_enrichment_events_created_at",
        "enrichment_events",
        ["created_at"],
    )
    op.create_index(
        "ix_notification_outbox_created_at",
        "notification_outbox",
        ["created_at"],
    )
    op.create_index(
        "ix_telegram_source_chats_updated_at",
        "telegram_source_chats",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_telegram_source_chats_updated_at", table_name="telegram_source_chats")
    op.drop_index("ix_notification_outbox_created_at", table_name="notification_outbox")
    op.drop_index("ix_enrichment_events_created_at", table_name="enrichment_events")
