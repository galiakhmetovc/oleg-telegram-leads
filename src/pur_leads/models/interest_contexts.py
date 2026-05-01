"""Interest context table definitions."""

from sqlalchemy import Column, DateTime, MetaData, String, Table, Text

metadata = MetaData()

interest_contexts_table = Table(
    "interest_contexts",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("name", String(200), nullable=False),
    Column("description", Text, nullable=True),
    Column("status", String(32), nullable=False),
    Column("created_by", String(160), nullable=False),
    Column("activated_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
