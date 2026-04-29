"""Add notification event journal.

Revision ID: 0008_notification_events
Revises: 0007_scheduler_preview_job
Create Date: 2026-04-29
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0008_notification_events"
down_revision: str | None = "0007_scheduler_preview_job"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("notification_type", sa.String(64), nullable=False),
        sa.Column("notification_policy", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("dedupe_key", sa.String(256), nullable=True),
        sa.Column("lead_cluster_id", sa.String(36), nullable=True),
        sa.Column("lead_event_id", sa.String(36), nullable=True),
        sa.Column("scheduler_job_id", sa.String(36), nullable=True),
        sa.Column("monitored_source_id", sa.String(36), nullable=True),
        sa.Column("source_message_id", sa.String(36), nullable=True),
        sa.Column("target_ref", sa.String(128), nullable=True),
        sa.Column("provider_message_id", sa.String(128), nullable=True),
        sa.Column("suppressed_reason", sa.String(128), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["lead_cluster_id"], ["lead_clusters.id"]),
        sa.ForeignKeyConstraint(["lead_event_id"], ["lead_events.id"]),
        sa.ForeignKeyConstraint(["scheduler_job_id"], ["scheduler_jobs.id"]),
        sa.ForeignKeyConstraint(["monitored_source_id"], ["monitored_sources.id"]),
        sa.ForeignKeyConstraint(["source_message_id"], ["source_messages.id"]),
        sa.CheckConstraint("channel IN ('telegram', 'web')", name="ck_notification_channel"),
        sa.CheckConstraint(
            "notification_type IN ('lead', 'maybe', 'retro_lead', "
            "'reclassification_lead', 'digest', 'task', 'source_issue', "
            "'contact_reason', 'operator_help')",
            name="ck_notification_type",
        ),
        sa.CheckConstraint(
            "notification_policy IN ('immediate', 'digest', 'suppressed')",
            name="ck_notification_policy",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'sent', 'suppressed', 'failed', 'cancelled')",
            name="ck_notification_status",
        ),
    )
    op.create_index(
        "ix_notification_events_cluster",
        "notification_events",
        ["lead_cluster_id", "channel", "status", "created_at"],
    )
    op.create_index(
        "ix_notification_events_dedupe",
        "notification_events",
        ["dedupe_key", "channel", "status"],
    )
    op.create_index(
        "ix_notification_events_scheduler_job",
        "notification_events",
        ["scheduler_job_id"],
    )
    op.create_index(
        "ix_notification_events_created",
        "notification_events",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_notification_events_created", table_name="notification_events")
    op.drop_index("ix_notification_events_scheduler_job", table_name="notification_events")
    op.drop_index("ix_notification_events_dedupe", table_name="notification_events")
    op.drop_index("ix_notification_events_cluster", table_name="notification_events")
    op.drop_table("notification_events")
