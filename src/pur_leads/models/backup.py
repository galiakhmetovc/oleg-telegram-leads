"""Backup and restore table definitions."""

from sqlalchemy import Column, DateTime, Integer, JSON, MetaData, String, Table, Text

metadata = MetaData()

backup_runs_table = Table(
    "backup_runs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("backup_type", String(64), nullable=False),
    Column("storage_backend", String(64), nullable=False),
    Column("storage_uri", String(1024), nullable=False),
    Column("status", String(32), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("size_bytes", Integer, nullable=True),
    Column("sha256", String(64), nullable=True),
    Column("manifest_json", JSON, nullable=True),
    Column("error", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

restore_runs_table = Table(
    "restore_runs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("backup_run_id", String(36), nullable=False),
    Column("restore_type", String(64), nullable=False),
    Column("status", String(32), nullable=False),
    Column("target_path", String(1024), nullable=True),
    Column("validation_status", String(32), nullable=False),
    Column("validation_details_json", JSON, nullable=True),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("error", Text, nullable=True),
    Column("created_by", String(160), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
