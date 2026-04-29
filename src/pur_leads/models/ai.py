"""AI model execution coordination tables."""

from sqlalchemy import Column, DateTime, JSON, MetaData, String, Table

metadata = MetaData()

ai_model_concurrency_leases_table = Table(
    "ai_model_concurrency_leases",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("provider", String(64), nullable=False),
    Column("model", String(160), nullable=False),
    Column("normalized_model", String(160), nullable=False),
    Column("worker_name", String(160), nullable=False),
    Column("acquired_at", DateTime(timezone=True), nullable=False),
    Column("lease_expires_at", DateTime(timezone=True), nullable=False),
    Column("metadata_json", JSON, nullable=True),
)
