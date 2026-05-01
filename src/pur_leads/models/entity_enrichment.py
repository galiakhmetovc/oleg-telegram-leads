"""Canonical entity enrichment table definitions."""

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    JSON,
    MetaData,
    String,
    Table,
    Text,
)

metadata = MetaData()

canonical_entities_table = Table(
    "canonical_entities",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("canonical_name", String(512), nullable=False),
    Column("normalized_name", String(512), nullable=False),
    Column("entity_type", String(64), nullable=False),
    Column("status", String(32), nullable=False),
    Column("confidence", Float, nullable=True),
    Column("created_from_result_id", String(36), nullable=True),
    Column("metadata_json", JSON, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

canonical_entity_aliases_table = Table(
    "canonical_entity_aliases",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("canonical_entity_id", String(36), nullable=False),
    Column("alias", String(512), nullable=False),
    Column("normalized_alias", String(512), nullable=False),
    Column("alias_type", String(64), nullable=False),
    Column("status", String(32), nullable=False),
    Column("confidence", Float, nullable=True),
    Column("evidence_refs_json", JSON, nullable=True),
    Column("created_from_result_id", String(36), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

entity_enrichment_runs_table = Table(
    "entity_enrichment_runs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("raw_export_run_id", String(36), nullable=False),
    Column("ranked_entities_path", String(1024), nullable=False),
    Column("context_snapshot_id", String(80), nullable=False),
    Column("provider", String(64), nullable=True),
    Column("model", String(160), nullable=True),
    Column("model_profile", String(160), nullable=True),
    Column("prompt_version", String(80), nullable=False),
    Column("status", String(32), nullable=False),
    Column("metrics_json", JSON, nullable=True),
    Column("error", Text, nullable=True),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

entity_enrichment_results_table = Table(
    "entity_enrichment_results",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("run_id", String(36), nullable=False),
    Column("sequence_index", Integer, nullable=False),
    Column("ranked_entity_id", String(36), nullable=False),
    Column("ranked_entity_text", String(512), nullable=False),
    Column("canonical_entity_id", String(36), nullable=True),
    Column("action", String(64), nullable=False),
    Column("status", String(64), nullable=False),
    Column("confidence", Float, nullable=True),
    Column("reason", Text, nullable=True),
    Column("prompt_text", Text, nullable=False),
    Column("request_json", JSON, nullable=True),
    Column("response_json", JSON, nullable=True),
    Column("parsed_response_json", JSON, nullable=True),
    Column("context_snapshot_json", JSON, nullable=True),
    Column("source_refs_json", JSON, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

canonical_merge_candidates_table = Table(
    "canonical_merge_candidates",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("left_canonical_entity_id", String(36), nullable=True),
    Column("right_canonical_entity_id", String(36), nullable=True),
    Column("proposed_name", String(512), nullable=False),
    Column("normalized_name", String(512), nullable=False),
    Column("reason", Text, nullable=True),
    Column("status", String(32), nullable=False),
    Column("evidence_json", JSON, nullable=True),
    Column("created_from_result_id", String(36), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
