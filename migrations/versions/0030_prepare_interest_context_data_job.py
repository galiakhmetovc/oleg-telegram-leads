"""Allow interest context data preparation jobs.

Revision ID: 0030_prepare_interest_context_data_job
Revises: 0029_interest_contexts
Create Date: 2026-05-05
"""

from collections.abc import Sequence
import re

from alembic import op
import sqlalchemy as sa

revision: str = "0030_prepare_interest_context_data_job"
down_revision: str | None = "0029_interest_contexts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JOB_TYPES_WITH_PREPARE_INTEREST_CONTEXT_DATA = (
    "job_type IN ('poll_monitored_source', 'ingest_telegram_raw', 'export_telegram_raw', "
    "'prepare_interest_context_data', 'check_source_access', 'fetch_source_preview', "
    "'fetch_message_context', 'build_ai_batch', 'classify_message_batch', "
    "'reclassify_messages', 'retro_research_scan', 'sync_pur_channel', "
    "'download_artifact', 'parse_artifact', 'extract_catalog_facts', "
    "'fetch_external_page', 'catalog_candidate_validation', 'generate_contact_reasons', "
    "'send_notifications')"
)

_PREVIOUS_JOB_TYPES = (
    "job_type IN ('poll_monitored_source', 'ingest_telegram_raw', 'export_telegram_raw', "
    "'check_source_access', 'fetch_source_preview', 'fetch_message_context', "
    "'build_ai_batch', 'classify_message_batch', "
    "'reclassify_messages', 'retro_research_scan', 'sync_pur_channel', "
    "'download_artifact', 'parse_artifact', 'extract_catalog_facts', "
    "'fetch_external_page', 'catalog_candidate_validation', 'generate_contact_reasons', "
    "'send_notifications')"
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_scheduler_jobs"))
        if not _scheduler_jobs_allow_prepare_interest_context_data(bind):
            _replace_sqlite_scheduler_job_type_constraint(
                bind,
                _JOB_TYPES_WITH_PREPARE_INTEREST_CONTEXT_DATA,
            )
        return
    with op.batch_alter_table("scheduler_jobs", **_batch_kwargs()) as batch_op:
        batch_op.drop_constraint("ck_scheduler_jobs_job_type", type_="check")
        batch_op.create_check_constraint(
            "ck_scheduler_jobs_job_type",
            _JOB_TYPES_WITH_PREPARE_INTEREST_CONTEXT_DATA,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_scheduler_jobs"))
        _replace_sqlite_scheduler_job_type_constraint(bind, _PREVIOUS_JOB_TYPES)
        return
    with op.batch_alter_table("scheduler_jobs", **_batch_kwargs()) as batch_op:
        batch_op.drop_constraint("ck_scheduler_jobs_job_type", type_="check")
        batch_op.create_check_constraint("ck_scheduler_jobs_job_type", _PREVIOUS_JOB_TYPES)


def _scheduler_jobs_allow_prepare_interest_context_data(bind) -> bool:  # noqa: ANN001
    sql = bind.execute(
        sa.text("select sql from sqlite_master where type='table' and name='scheduler_jobs'")
    ).scalar_one()
    return "prepare_interest_context_data" in str(sql)


def _replace_sqlite_scheduler_job_type_constraint(bind, replacement: str) -> None:  # noqa: ANN001
    sql = str(
        bind.execute(
            sa.text("select sql from sqlite_master where type='table' and name='scheduler_jobs'")
        ).scalar_one()
    )
    updated = re.sub(r"job_type\s+IN\s*\([^)]*\)", replacement, sql, count=1)
    if updated == sql and replacement not in sql:
        raise RuntimeError("Could not locate scheduler job_type check constraint")
    bind.execute(sa.text("PRAGMA writable_schema=ON"))
    bind.execute(
        sa.text(
            "update sqlite_master set sql = :sql where type = 'table' and name = 'scheduler_jobs'"
        ),
        {"sql": updated},
    )
    schema_version = int(bind.execute(sa.text("PRAGMA schema_version")).scalar_one())
    bind.execute(sa.text(f"PRAGMA schema_version = {schema_version + 1}"))
    bind.execute(sa.text("PRAGMA writable_schema=OFF"))


def _batch_kwargs() -> dict[str, str]:
    return {"recreate": "always"} if op.get_bind().dialect.name == "sqlite" else {}
