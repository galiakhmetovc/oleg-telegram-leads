"""Allow beginning source ingest and raw Telegram ingest jobs.

Revision ID: 0023_source_from_beginning
Revises: 0022_catalog_quality_reviews
Create Date: 2026-04-30
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0023_source_from_beginning"
down_revision: str | None = "0022_catalog_quality_reviews"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_START_MODES_WITH_BEGINNING = (
    "start_mode IN ('from_now', 'from_message', 'recent_limit', 'recent_days', 'from_beginning')"
)

_PREVIOUS_START_MODES = "start_mode IN ('from_now', 'from_message', 'recent_limit', 'recent_days')"

_JOB_TYPES_WITH_RAW_INGEST = (
    "job_type IN ('poll_monitored_source', 'ingest_telegram_raw', 'check_source_access', "
    "'fetch_source_preview', 'fetch_message_context', 'build_ai_batch', "
    "'classify_message_batch', "
    "'reclassify_messages', 'retro_research_scan', 'sync_pur_channel', "
    "'download_artifact', 'parse_artifact', 'extract_catalog_facts', "
    "'fetch_external_page', 'catalog_candidate_validation', 'generate_contact_reasons', "
    "'send_notifications')"
)

_PREVIOUS_JOB_TYPES = (
    "job_type IN ('poll_monitored_source', 'check_source_access', "
    "'fetch_source_preview', 'fetch_message_context', 'build_ai_batch', "
    "'classify_message_batch', "
    "'reclassify_messages', 'retro_research_scan', 'sync_pur_channel', "
    "'download_artifact', 'parse_artifact', 'extract_catalog_facts', "
    "'fetch_external_page', 'catalog_candidate_validation', 'generate_contact_reasons', "
    "'send_notifications')"
)


def upgrade() -> None:
    with op.batch_alter_table("monitored_sources", **_batch_kwargs()) as batch_op:
        batch_op.drop_constraint("ck_monitored_sources_start_mode", type_="check")
        batch_op.create_check_constraint(
            "ck_monitored_sources_start_mode",
            _START_MODES_WITH_BEGINNING,
        )
    with op.batch_alter_table("scheduler_jobs", **_batch_kwargs()) as batch_op:
        batch_op.drop_constraint("ck_scheduler_jobs_job_type", type_="check")
        batch_op.create_check_constraint("ck_scheduler_jobs_job_type", _JOB_TYPES_WITH_RAW_INGEST)


def downgrade() -> None:
    with op.batch_alter_table("scheduler_jobs", **_batch_kwargs()) as batch_op:
        batch_op.drop_constraint("ck_scheduler_jobs_job_type", type_="check")
        batch_op.create_check_constraint("ck_scheduler_jobs_job_type", _PREVIOUS_JOB_TYPES)
    with op.batch_alter_table("monitored_sources", **_batch_kwargs()) as batch_op:
        batch_op.drop_constraint("ck_monitored_sources_start_mode", type_="check")
        batch_op.create_check_constraint(
            "ck_monitored_sources_start_mode",
            _PREVIOUS_START_MODES,
        )


def _batch_kwargs() -> dict[str, str]:
    return {"recreate": "always"} if op.get_bind().dialect.name == "sqlite" else {}
