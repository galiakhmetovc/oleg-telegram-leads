"""Settings table definitions."""

from sqlalchemy import Boolean, Column, DateTime, JSON, MetaData, String, Table, Text

metadata = MetaData()

settings_table = Table(
    "settings",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("key", String(160), nullable=False),
    Column("value_json", JSON, nullable=False),
    Column("value_type", String(32), nullable=False),
    Column("scope", String(64), nullable=False),
    Column("scope_id", String(128), nullable=False),
    Column("description", Text, nullable=True),
    Column("requires_restart", Boolean, nullable=False),
    Column("is_secret_ref", Boolean, nullable=False),
    Column("updated_by", String(160), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

settings_revisions_table = Table(
    "settings_revisions",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("setting_key", String(160), nullable=False),
    Column("scope", String(64), nullable=False),
    Column("scope_id", String(128), nullable=False),
    Column("old_value_hash", String(64), nullable=True),
    Column("new_value_hash", String(64), nullable=False),
    Column("old_value_json", JSON, nullable=True),
    Column("new_value_json", JSON, nullable=False),
    Column("changed_by", String(160), nullable=False),
    Column("change_reason", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
