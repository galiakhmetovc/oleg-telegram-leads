"""Create versioned interest-core brief table.

Revision ID: 0034_interest_core_briefs
Revises: 0033_interest_context_drafts
Create Date: 2026-05-05
"""

from collections.abc import Sequence
import re

from alembic import op
import sqlalchemy as sa

revision: str = "0034_interest_core_briefs"
down_revision: str | None = "0033_interest_context_drafts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JOB_TYPES_WITH_CORE_BRIEF = (
    "job_type IN ('poll_monitored_source', 'ingest_telegram_raw', 'export_telegram_raw', "
    "'prepare_interest_context_data', 'build_interest_context_draft', "
    "'generate_interest_core_brief', 'check_source_access', 'fetch_source_preview', "
    "'fetch_message_context', 'build_ai_batch', 'classify_message_batch', "
    "'reclassify_messages', 'retro_research_scan', 'sync_pur_channel', "
    "'download_artifact', 'parse_artifact', 'extract_catalog_facts', "
    "'fetch_external_page', 'catalog_candidate_validation', 'generate_contact_reasons', "
    "'send_notifications')"
)

_PREVIOUS_JOB_TYPES = (
    "job_type IN ('poll_monitored_source', 'ingest_telegram_raw', 'export_telegram_raw', "
    "'prepare_interest_context_data', 'build_interest_context_draft', "
    "'check_source_access', 'fetch_source_preview', 'fetch_message_context', "
    "'build_ai_batch', 'classify_message_batch', 'reclassify_messages', "
    "'retro_research_scan', 'sync_pur_channel', 'download_artifact', 'parse_artifact', "
    "'extract_catalog_facts', 'fetch_external_page', 'catalog_candidate_validation', "
    "'generate_contact_reasons', 'send_notifications')"
)


def upgrade() -> None:
    op.create_table(
        "interest_core_briefs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("context_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("brief_text", sa.Text(), nullable=False),
        sa.Column("brief_json", sa.JSON(), nullable=True),
        sa.Column("source_refs_json", sa.JSON(), nullable=True),
        sa.Column("prompt_version", sa.String(length=80), nullable=True),
        sa.Column("prompt_text", sa.Text(), nullable=True),
        sa.Column("request_json", sa.JSON(), nullable=True),
        sa.Column("response_json", sa.JSON(), nullable=True),
        sa.Column("parsed_response_json", sa.JSON(), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=160), nullable=True),
        sa.Column("model_profile", sa.String(length=160), nullable=True),
        sa.Column("ai_provider_account_id", sa.String(length=36), nullable=True),
        sa.Column("ai_model_id", sa.String(length=36), nullable=True),
        sa.Column("ai_model_profile_id", sa.String(length=36), nullable=True),
        sa.Column("ai_agent_route_id", sa.String(length=36), nullable=True),
        sa.Column("generation_status", sa.String(length=32), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.Column("activated_by", sa.String(length=160), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'archived', 'failed')",
            name="ck_interest_core_briefs_status",
        ),
        sa.CheckConstraint(
            "source IN ('manual', 'llm_generated', 'edited_llm')",
            name="ck_interest_core_briefs_source",
        ),
    )
    op.create_index(
        "ix_interest_core_briefs_context_version",
        "interest_core_briefs",
        ["context_id", "version"],
        unique=True,
    )
    op.create_index(
        "ix_interest_core_briefs_context_status",
        "interest_core_briefs",
        ["context_id", "status"],
    )
    _replace_job_type_constraint(_JOB_TYPES_WITH_CORE_BRIEF)


def downgrade() -> None:
    _replace_job_type_constraint(_PREVIOUS_JOB_TYPES)
    op.drop_index("ix_interest_core_briefs_context_status", table_name="interest_core_briefs")
    op.drop_index("ix_interest_core_briefs_context_version", table_name="interest_core_briefs")
    op.drop_table("interest_core_briefs")


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
