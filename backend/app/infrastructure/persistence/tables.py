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
