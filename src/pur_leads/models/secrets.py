"""Secret reference table definitions."""

from sqlalchemy import Column, DateTime, MetaData, String, Table

metadata = MetaData()

secret_refs_table = Table(
    "secret_refs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("secret_type", String(64), nullable=False),
    Column("display_name", String(160), nullable=False),
    Column("storage_backend", String(64), nullable=False),
    Column("storage_ref", String(512), nullable=False),
    Column("status", String(32), nullable=False),
    Column("last_rotated_at", DateTime(timezone=True), nullable=True),
    Column("last_checked_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
