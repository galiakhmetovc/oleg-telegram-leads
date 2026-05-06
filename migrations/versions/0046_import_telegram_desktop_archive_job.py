"""Allow background Telegram Desktop archive import jobs.

Revision ID: 0046_import_telegram_desktop_archive_job
Revises: 0045_structured_intent_conditions
Create Date: 2026-05-06
"""

from collections.abc import Sequence
import re

from alembic import op
import sqlalchemy as sa

revision: str = "0046_import_telegram_desktop_archive_job"
down_revision: str | None = "0045_structured_intent_conditions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JOB_TYPES_WITH_ARCHIVE_IMPORT = (
    "job_type IN ('poll_monitored_source', 'ingest_telegram_raw', 'export_telegram_raw', "
    "'import_telegram_desktop_archive', 'prepare_interest_context_data', "
    "'build_interest_context_draft', 'generate_interest_core_brief', "
    "'enhance_interest_core_candidates', 'check_source_access', 'fetch_source_preview', "
    "'fetch_message_context', 'build_ai_batch', 'classify_message_batch', "
    "'reclassify_messages', 'retro_research_scan', 'sync_pur_channel', "
    "'download_artifact', 'parse_artifact', 'extract_catalog_facts', "
    "'fetch_external_page', 'catalog_candidate_validation', 'generate_contact_reasons', "
    "'send_notifications')"
)

_PREVIOUS_JOB_TYPES = (
    "job_type IN ('poll_monitored_source', 'ingest_telegram_raw', 'export_telegram_raw', "
    "'prepare_interest_context_data', 'build_interest_context_draft', "
    "'generate_interest_core_brief', 'enhance_interest_core_candidates', "
    "'check_source_access', 'fetch_source_preview', 'fetch_message_context', "
    "'build_ai_batch', 'classify_message_batch', 'reclassify_messages', "
    "'retro_research_scan', 'sync_pur_channel', 'download_artifact', 'parse_artifact', "
    "'extract_catalog_facts', 'fetch_external_page', 'catalog_candidate_validation', "
    "'generate_contact_reasons', 'send_notifications')"
)


def upgrade() -> None:
    _replace_job_type_constraint(_JOB_TYPES_WITH_ARCHIVE_IMPORT)


def downgrade() -> None:
    _replace_job_type_constraint(_PREVIOUS_JOB_TYPES)


def _replace_job_type_constraint(replacement: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        sql = str(
            bind.execute(
                sa.text(
                    "select sql from sqlite_master where type='table' and name='scheduler_jobs'"
                )
            ).scalar_one()
        )
        updated = re.sub(r"job_type\s+IN\s*\([^)]*\)", replacement, sql, count=1)
        if updated == sql and replacement not in sql:
            raise RuntimeError("Could not locate scheduler job_type check constraint")
        bind.execute(sa.text("PRAGMA writable_schema=ON"))
        bind.execute(
            sa.text(
                "update sqlite_master set sql = :sql "
                "where type = 'table' and name = 'scheduler_jobs'"
            ),
            {"sql": updated},
        )
        schema_version = int(bind.execute(sa.text("PRAGMA schema_version")).scalar_one())
        bind.execute(sa.text(f"PRAGMA schema_version = {schema_version + 1}"))
        bind.execute(sa.text("PRAGMA writable_schema=OFF"))
        return
    with op.batch_alter_table("scheduler_jobs") as batch_op:
        batch_op.drop_constraint("ck_scheduler_jobs_job_type", type_="check")
        batch_op.create_check_constraint("ck_scheduler_jobs_job_type", replacement)
