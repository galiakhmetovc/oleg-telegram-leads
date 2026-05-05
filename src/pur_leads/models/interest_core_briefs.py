"""Versioned interest-core brief tables."""

from sqlalchemy import Column, DateTime, Integer, JSON, MetaData, String, Table, Text

metadata = MetaData()

interest_core_briefs_table = Table(
    "interest_core_briefs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("context_id", String(36), nullable=False),
    Column("version", Integer, nullable=False),
    Column("status", String(32), nullable=False),
    Column("source", String(32), nullable=False),
    Column("title", String(200), nullable=True),
    Column("brief_text", Text, nullable=False),
    Column("brief_json", JSON, nullable=True),
    Column("source_refs_json", JSON, nullable=True),
    Column("prompt_version", String(80), nullable=True),
    Column("prompt_text", Text, nullable=True),
    Column("request_json", JSON, nullable=True),
    Column("response_json", JSON, nullable=True),
    Column("parsed_response_json", JSON, nullable=True),
    Column("provider", String(64), nullable=True),
    Column("model", String(160), nullable=True),
    Column("model_profile", String(160), nullable=True),
    Column("ai_provider_account_id", String(36), nullable=True),
    Column("ai_model_id", String(36), nullable=True),
    Column("ai_model_profile_id", String(36), nullable=True),
    Column("ai_agent_route_id", String(36), nullable=True),
    Column("generation_status", String(32), nullable=True),
    Column("error", Text, nullable=True),
    Column("created_by", String(160), nullable=False),
    Column("activated_by", String(160), nullable=True),
    Column("activated_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
