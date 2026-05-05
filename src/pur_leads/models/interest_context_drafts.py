"""Interest context draft knowledge tables."""

from sqlalchemy import Column, DateTime, Float, Integer, JSON, MetaData, String, Table, Text

metadata = MetaData()

interest_context_draft_runs_table = Table(
    "interest_context_draft_runs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("context_id", String(36), nullable=False),
    Column("status", String(32), nullable=False),
    Column("algorithm_version", String(80), nullable=False),
    Column("input_summary_json", JSON, nullable=True),
    Column("output_summary_json", JSON, nullable=True),
    Column("created_by", String(160), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

interest_context_draft_items_table = Table(
    "interest_context_draft_items",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("draft_run_id", String(36), nullable=False),
    Column("context_id", String(36), nullable=False),
    Column("item_type", String(64), nullable=False),
    Column("title", String(300), nullable=False),
    Column("normalized_key", String(300), nullable=False),
    Column("description", Text, nullable=True),
    Column("score", Float, nullable=False),
    Column("confidence", String(32), nullable=False),
    Column("status", String(32), nullable=False),
    Column("evidence_count", Integer, nullable=False),
    Column("source_message_count", Integer, nullable=False),
    Column("metadata_json", JSON, nullable=True),
    Column("evidence_json", JSON, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
