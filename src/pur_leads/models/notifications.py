"""Notification event table definitions."""

from sqlalchemy import Column, DateTime, JSON, MetaData, String, Table, Text

metadata = MetaData()

notification_events_table = Table(
    "notification_events",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("channel", String(32), nullable=False),
    Column("notification_type", String(64), nullable=False),
    Column("notification_policy", String(32), nullable=False),
    Column("status", String(32), nullable=False),
    Column("dedupe_key", String(256), nullable=True),
    Column("lead_cluster_id", String(36), nullable=True),
    Column("lead_event_id", String(36), nullable=True),
    Column("scheduler_job_id", String(36), nullable=True),
    Column("monitored_source_id", String(36), nullable=True),
    Column("source_message_id", String(36), nullable=True),
    Column("target_ref", String(128), nullable=True),
    Column("provider_message_id", String(128), nullable=True),
    Column("suppressed_reason", String(128), nullable=True),
    Column("error", Text, nullable=True),
    Column("payload_json", JSON, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("queued_at", DateTime(timezone=True), nullable=True),
    Column("sent_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
