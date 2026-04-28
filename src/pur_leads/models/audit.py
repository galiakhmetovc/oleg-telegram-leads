"""Audit and operational event table definitions."""

from sqlalchemy import Column, DateTime, JSON, MetaData, String, Table, Text

metadata = MetaData()

audit_log_table = Table(
    "audit_log",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("actor", String(160), nullable=False),
    Column("action", String(160), nullable=False),
    Column("entity_type", String(120), nullable=False),
    Column("entity_id", String(128), nullable=True),
    Column("old_value_json", JSON, nullable=True),
    Column("new_value_json", JSON, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

operational_events_table = Table(
    "operational_events",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("event_type", String(64), nullable=False),
    Column("severity", String(32), nullable=False),
    Column("entity_type", String(120), nullable=True),
    Column("entity_id", String(128), nullable=True),
    Column("correlation_id", String(128), nullable=True),
    Column("message", Text, nullable=False),
    Column("details_json", JSON, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
