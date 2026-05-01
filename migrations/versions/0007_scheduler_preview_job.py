"""Allow source preview scheduler jobs.

Revision ID: 0007_scheduler_preview_job
Revises: 0006_crm_memory
Create Date: 2026-04-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007_scheduler_preview_job"
down_revision: str | None = "0006_crm_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JOB_TYPES_WITH_PREVIEW = (
    "job_type IN ('poll_monitored_source', 'check_source_access', "
    "'fetch_source_preview', 'fetch_message_context', 'build_ai_batch', "
    "'classify_message_batch', 'reclassify_messages', 'retro_research_scan', "
    "'sync_pur_channel', 'download_artifact', 'parse_artifact', "
    "'extract_catalog_facts', 'generate_contact_reasons', 'send_notifications')"
)

_JOB_TYPES_WITHOUT_PREVIEW = (
    "job_type IN ('poll_monitored_source', 'check_source_access', "
    "'fetch_message_context', 'build_ai_batch', 'classify_message_batch', "
    "'reclassify_messages', 'retro_research_scan', 'sync_pur_channel', "
    "'download_artifact', 'parse_artifact', 'extract_catalog_facts', "
    "'generate_contact_reasons', 'send_notifications')"
)


def upgrade() -> None:
    with op.batch_alter_table("scheduler_jobs", **_batch_kwargs()) as batch_op:
        batch_op.drop_constraint("ck_scheduler_jobs_job_type", type_="check")
        batch_op.create_check_constraint("ck_scheduler_jobs_job_type", _JOB_TYPES_WITH_PREVIEW)


def downgrade() -> None:
    with op.batch_alter_table("scheduler_jobs", **_batch_kwargs()) as batch_op:
        batch_op.drop_constraint("ck_scheduler_jobs_job_type", type_="check")
        batch_op.create_check_constraint("ck_scheduler_jobs_job_type", _JOB_TYPES_WITHOUT_PREVIEW)


def _batch_kwargs() -> dict[str, str]:
    return {"recreate": "always"} if op.get_bind().dialect.name == "sqlite" else {}
