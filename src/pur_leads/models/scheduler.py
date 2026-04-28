"""Scheduler table definitions."""

from sqlalchemy import Column, DateTime, Integer, JSON, MetaData, String, Table, Text

metadata = MetaData()

scheduler_jobs_table = Table(
    "scheduler_jobs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("job_type", String(80), nullable=False),
    Column("status", String(32), nullable=False),
    Column("priority", String(32), nullable=False),
    Column("scope_type", String(64), nullable=False),
    Column("scope_id", String(128), nullable=True),
    Column("userbot_account_id", String(36), nullable=True),
    Column("monitored_source_id", String(36), nullable=True),
    Column("source_message_id", String(36), nullable=True),
    Column("idempotency_key", String(256), nullable=True),
    Column("run_after_at", DateTime(timezone=True), nullable=False),
    Column("next_retry_at", DateTime(timezone=True), nullable=True),
    Column("locked_by", String(160), nullable=True),
    Column("locked_at", DateTime(timezone=True), nullable=True),
    Column("lease_expires_at", DateTime(timezone=True), nullable=True),
    Column("attempt_count", Integer, nullable=False),
    Column("max_attempts", Integer, nullable=False),
    Column("checkpoint_before_json", JSON, nullable=True),
    Column("checkpoint_after_json", JSON, nullable=True),
    Column("result_summary_json", JSON, nullable=True),
    Column("payload_json", JSON, nullable=True),
    Column("last_error", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

job_runs_table = Table(
    "job_runs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("scheduler_job_id", String(36), nullable=False),
    Column("worker_name", String(160), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("status", String(32), nullable=False),
    Column("duration_ms", Integer, nullable=True),
    Column("result_json", JSON, nullable=True),
    Column("error", Text, nullable=True),
    Column("log_correlation_id", String(128), nullable=True),
)
