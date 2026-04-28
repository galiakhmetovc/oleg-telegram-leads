"""Create foundation tables.

Revision ID: 0001_foundation
Revises:
Create Date: 2026-04-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0001_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "settings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("key", sa.String(length=160), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("value_type", sa.String(length=32), nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False, server_default="global"),
        sa.Column("scope_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("requires_restart", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_secret_ref", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_by", sa.String(length=160), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "value_type IN ('bool', 'int', 'float', 'string', 'json', 'secret_ref')",
            name="ck_settings_value_type",
        ),
        sa.CheckConstraint(
            "scope IN ('global', 'userbot_account', 'monitored_source', 'ai_provider', "
            "'ai_model', 'notification', 'archive', 'backup')",
            name="ck_settings_scope",
        ),
        sa.UniqueConstraint("key", "scope", "scope_id", name="uq_settings_key_scope"),
    )

    op.create_table(
        "settings_revisions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("setting_key", sa.String(length=160), nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("scope_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("old_value_hash", sa.String(length=64), nullable=True),
        sa.Column("new_value_hash", sa.String(length=64), nullable=False),
        sa.Column("old_value_json", sa.JSON(), nullable=True),
        sa.Column("new_value_json", sa.JSON(), nullable=False),
        sa.Column("changed_by", sa.String(length=160), nullable=False),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "secret_refs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("secret_type", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("storage_backend", sa.String(length=64), nullable=False),
        sa.Column("storage_ref", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "secret_type IN ('telegram_session', 'telegram_api', 'ai_api_key', "
            "'web_session_secret', 'bootstrap_admin_password', "
            "'archive_s3_credentials', 'other')",
            name="ck_secret_refs_secret_type",
        ),
        sa.CheckConstraint(
            "storage_backend IN ('env', 'file', 'system_keyring', 'external_secret_manager')",
            name="ck_secret_refs_storage_backend",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'rotating', 'revoked', 'missing')",
            name="ck_secret_refs_status",
        ),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("actor", sa.String(length=160), nullable=False),
        sa.Column("action", sa.String(length=160), nullable=False),
        sa.Column("entity_type", sa.String(length=120), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=True),
        sa.Column("old_value_json", sa.JSON(), nullable=True),
        sa.Column("new_value_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "operational_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("entity_type", sa.String(length=120), nullable=True),
        sa.Column("entity_id", sa.String(length=128), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('source_sync', 'access_check', 'telegram_request', "
            "'ai_request', 'parser_run', 'catalog_extraction', 'notification', "
            "'crm_generation', 'scheduler')",
            name="ck_operational_events_event_type",
        ),
        sa.CheckConstraint(
            "severity IN ('debug', 'info', 'warning', 'error', 'critical')",
            name="ck_operational_events_severity",
        ),
    )
    op.create_index(
        "ix_operational_events_correlation_id",
        "operational_events",
        ["correlation_id"],
    )

    op.create_table(
        "scheduler_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("job_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("scope_type", sa.String(length=64), nullable=False),
        sa.Column("scope_id", sa.String(length=128), nullable=True),
        sa.Column("userbot_account_id", sa.String(length=36), nullable=True),
        sa.Column("monitored_source_id", sa.String(length=36), nullable=True),
        sa.Column("source_message_id", sa.String(length=36), nullable=True),
        sa.Column("idempotency_key", sa.String(length=256), nullable=True),
        sa.Column("run_after_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=160), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("checkpoint_before_json", sa.JSON(), nullable=True),
        sa.Column("checkpoint_after_json", sa.JSON(), nullable=True),
        sa.Column("result_summary_json", sa.JSON(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "job_type IN ('poll_monitored_source', 'check_source_access', "
            "'fetch_message_context', 'build_ai_batch', 'classify_message_batch', "
            "'reclassify_messages', 'retro_research_scan', 'sync_pur_channel', "
            "'download_artifact', 'parse_artifact', 'extract_catalog_facts', "
            "'generate_contact_reasons', 'send_notifications')",
            name="ck_scheduler_jobs_job_type",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'paused', 'cancelled')",
            name="ck_scheduler_jobs_status",
        ),
        sa.CheckConstraint(
            "priority IN ('low', 'normal', 'high')",
            name="ck_scheduler_jobs_priority",
        ),
        sa.CheckConstraint(
            "scope_type IN ('global', 'telegram_userbot', 'telegram_source', "
            "'ai_provider', 'ai_model', 'parser', 'archive', 'backup')",
            name="ck_scheduler_jobs_scope_type",
        ),
    )
    op.create_index(
        "ix_scheduler_jobs_due",
        "scheduler_jobs",
        ["status", "run_after_at", "priority"],
    )
    op.create_index(
        "uq_scheduler_jobs_active_idempotency",
        "scheduler_jobs",
        ["idempotency_key"],
        unique=True,
        sqlite_where=sa.text("idempotency_key IS NOT NULL AND status IN ('queued', 'running')"),
    )

    op.create_table(
        "job_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("scheduler_job_id", sa.String(length=36), nullable=False),
        sa.Column("worker_name", sa.String(length=160), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("log_correlation_id", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(["scheduler_job_id"], ["scheduler_jobs.id"]),
    )


def downgrade() -> None:
    op.drop_table("job_runs")
    op.drop_index("uq_scheduler_jobs_active_idempotency", table_name="scheduler_jobs")
    op.drop_index("ix_scheduler_jobs_due", table_name="scheduler_jobs")
    op.drop_table("scheduler_jobs")
    op.drop_index("ix_operational_events_correlation_id", table_name="operational_events")
    op.drop_table("operational_events")
    op.drop_table("audit_log")
    op.drop_table("secret_refs")
    op.drop_table("settings_revisions")
    op.drop_table("settings")
