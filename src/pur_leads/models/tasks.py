"""Task table definitions."""

from sqlalchemy import Column, DateTime, MetaData, String, Table, Text

metadata = MetaData()

tasks_table = Table(
    "tasks",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("client_id", String(36), nullable=True),
    Column("lead_cluster_id", String(36), nullable=True),
    Column("lead_event_id", String(36), nullable=True),
    Column("opportunity_id", String(36), nullable=True),
    Column("support_case_id", String(36), nullable=True),
    Column("contact_reason_id", String(36), nullable=True),
    Column("title", String(255), nullable=False),
    Column("description", Text, nullable=True),
    Column("status", String(32), nullable=False),
    Column("priority", String(32), nullable=False),
    Column("due_at", DateTime(timezone=True), nullable=True),
    Column("owner_user_id", String(36), nullable=True),
    Column("assignee_user_id", String(36), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True), nullable=True),
)
