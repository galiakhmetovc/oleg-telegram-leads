"""notification outbox idempotency keys

Revision ID: 0015_outbox_idempotency
Revises: 0014_message_reviews_source_fk
Create Date: 2026-05-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_outbox_idempotency"
down_revision: str | None = "0014_message_reviews_source_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notification_outbox",
        sa.Column("source_message_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "notification_outbox",
        sa.Column("enrichment_job_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "notification_outbox",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_notification_outbox_source_message",
        "notification_outbox",
        "telegram_source_messages",
        ["source_message_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_notification_outbox_enrichment_job",
        "notification_outbox",
        "enrichment_jobs",
        ["enrichment_job_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ux_notification_outbox_source_route",
        "notification_outbox",
        ["source_message_id", "route_id"],
        unique=True,
        postgresql_where=sa.text("source_message_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ux_notification_outbox_source_route", table_name="notification_outbox")
    op.drop_constraint("fk_notification_outbox_enrichment_job", "notification_outbox", type_="foreignkey")
    op.drop_constraint("fk_notification_outbox_source_message", "notification_outbox", type_="foreignkey")
    op.drop_column("notification_outbox", "claimed_at")
    op.drop_column("notification_outbox", "enrichment_job_id")
    op.drop_column("notification_outbox", "source_message_id")
