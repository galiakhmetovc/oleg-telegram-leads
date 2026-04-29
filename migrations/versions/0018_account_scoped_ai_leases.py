"""Scope AI concurrency leases by provider account.

Revision ID: 0018_account_scoped_ai_leases
Revises: 0017_telegram_bot_notification_registry
Create Date: 2026-04-29
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0018_account_scoped_ai_leases"
down_revision: str | None = "0017_telegram_bot_notification_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("ai_model_concurrency_leases") as batch_op:
        batch_op.add_column(sa.Column("ai_provider_account_id", sa.String(36), nullable=True))
    op.create_index(
        "ix_ai_model_leases_account_model_expires",
        "ai_model_concurrency_leases",
        ["ai_provider_account_id", "provider", "normalized_model", "lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_model_leases_account_model_expires",
        table_name="ai_model_concurrency_leases",
    )
    with op.batch_alter_table("ai_model_concurrency_leases") as batch_op:
        batch_op.drop_column("ai_provider_account_id")
