from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = sa.MetaData()

enrichment_jobs = sa.Table(
    "enrichment_jobs",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("input_text", sa.Text(), nullable=False),
    sa.Column("status", sa.Text(), nullable=False),
    sa.Column("progress_percent", sa.Integer(), nullable=False),
    sa.Column("current_stage", sa.Text(), nullable=True),
    sa.Column("stage_index", sa.Integer(), nullable=False),
    sa.Column("stage_count", sa.Integer(), nullable=False),
    sa.Column("stage_progress_percent", sa.Integer(), nullable=False),
    sa.Column("message", sa.Text(), nullable=False),
    sa.Column("error", JSONB(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

enrichment_results = sa.Table(
    "enrichment_results",
    metadata,
    sa.Column("job_id", UUID(as_uuid=True), primary_key=True),
    sa.Column("result", JSONB(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

enrichment_events = sa.Table(
    "enrichment_events",
    metadata,
    sa.Column("sequence", sa.BigInteger(), primary_key=True),
    sa.Column("job_id", UUID(as_uuid=True), nullable=False),
    sa.Column("event_type", sa.Text(), nullable=False),
    sa.Column("progress_percent", sa.Integer(), nullable=False),
    sa.Column("current_stage", sa.Text(), nullable=True),
    sa.Column("stage_index", sa.Integer(), nullable=False),
    sa.Column("stage_count", sa.Integer(), nullable=False),
    sa.Column("stage_progress_percent", sa.Integer(), nullable=False),
    sa.Column("message", sa.Text(), nullable=False),
    sa.Column("payload", JSONB(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

nlp_config_revisions = sa.Table(
    "nlp_config_revisions",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("revision", sa.Integer(), nullable=False),
    sa.Column("config", JSONB(), nullable=False),
    sa.Column("is_active", sa.Boolean(), nullable=False),
    sa.Column("source", sa.Text(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

analytics_runs = sa.Table(
    "analytics_runs",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("name", sa.Text(), nullable=False),
    sa.Column("source", sa.Text(), nullable=False),
    sa.Column("input_path", sa.Text(), nullable=False),
    sa.Column("run_dir", sa.Text(), nullable=False),
    sa.Column("processed", sa.Integer(), nullable=False),
    sa.Column("skipped", sa.Integer(), nullable=False),
    sa.Column("failed", sa.Integer(), nullable=False),
    sa.Column("leads", sa.Integer(), nullable=False),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("summary", JSONB(), nullable=False),
)

analytics_candidates = sa.Table(
    "analytics_candidates",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("run_id", UUID(as_uuid=True), nullable=False),
    sa.Column("message_id", sa.Text(), nullable=False),
    sa.Column("text", sa.Text(), nullable=False),
    sa.Column("score", sa.Integer(), nullable=False),
    sa.Column("temperature", sa.Text(), nullable=False),
    sa.Column("solution_areas", JSONB(), nullable=False),
    sa.Column("customer_segments", JSONB(), nullable=False),
    sa.Column("intent_signals", JSONB(), nullable=False),
    sa.Column("noise_signals", JSONB(), nullable=False),
    sa.Column("reasons", JSONB(), nullable=False),
    sa.Column("domain_signals", JSONB(), nullable=False),
    sa.Column("facts", JSONB(), nullable=False),
    sa.Column("signal_types", sa.ARRAY(sa.Text()), nullable=False),
    sa.Column("fact_types", sa.ARRAY(sa.Text()), nullable=False),
    sa.Column("reason_keys", sa.ARRAY(sa.Text()), nullable=False),
    sa.Column("solution_area_types", sa.ARRAY(sa.Text()), nullable=False),
    sa.Column("customer_segment_types", sa.ARRAY(sa.Text()), nullable=False),
)

analytics_aggregates = sa.Table(
    "analytics_aggregates",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("run_id", UUID(as_uuid=True), nullable=False),
    sa.Column("kind", sa.Text(), nullable=False),
    sa.Column("key", sa.Text(), nullable=False),
    sa.Column("label", sa.Text(), nullable=False),
    sa.Column("count", sa.Integer(), nullable=False),
    sa.Column("payload", JSONB(), nullable=False),
)
