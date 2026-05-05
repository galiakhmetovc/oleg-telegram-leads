"""Create interest context draft tables.

Revision ID: 0033_interest_context_drafts
Revises: 0032_interest_context_scheduler_scope
Create Date: 2026-05-05
"""

from collections.abc import Sequence
import re

from alembic import op
import sqlalchemy as sa

revision: str = "0033_interest_context_drafts"
down_revision: str | None = "0032_interest_context_scheduler_scope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JOB_TYPES_WITH_DRAFT = (
    "job_type IN ('poll_monitored_source', 'ingest_telegram_raw', 'export_telegram_raw', "
    "'prepare_interest_context_data', 'build_interest_context_draft', "
    "'check_source_access', 'fetch_source_preview', 'fetch_message_context', "
    "'build_ai_batch', 'classify_message_batch', 'reclassify_messages', "
    "'retro_research_scan', 'sync_pur_channel', 'download_artifact', 'parse_artifact', "
    "'extract_catalog_facts', 'fetch_external_page', 'catalog_candidate_validation', "
    "'generate_contact_reasons', 'send_notifications')"
)

_PREVIOUS_JOB_TYPES = (
    "job_type IN ('poll_monitored_source', 'ingest_telegram_raw', 'export_telegram_raw', "
    "'prepare_interest_context_data', 'check_source_access', 'fetch_source_preview', "
    "'fetch_message_context', 'build_ai_batch', 'classify_message_batch', "
    "'reclassify_messages', 'retro_research_scan', 'sync_pur_channel', "
    "'download_artifact', 'parse_artifact', 'extract_catalog_facts', "
    "'fetch_external_page', 'catalog_candidate_validation', 'generate_contact_reasons', "
    "'send_notifications')"
)


def upgrade() -> None:
    op.create_table(
        "interest_context_draft_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("context_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("algorithm_version", sa.String(length=80), nullable=False),
        sa.Column("input_summary_json", sa.JSON(), nullable=True),
        sa.Column("output_summary_json", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name="ck_interest_context_draft_runs_status",
        ),
    )
    op.create_index(
        "ix_interest_context_draft_runs_context_created",
        "interest_context_draft_runs",
        ["context_id", "created_at"],
    )

    op.create_table(
        "interest_context_draft_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("draft_run_id", sa.String(length=36), nullable=False),
        sa.Column("context_id", sa.String(length=36), nullable=False),
        sa.Column("item_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("normalized_key", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("source_message_count", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["draft_run_id"], ["interest_context_draft_runs.id"]),
        sa.CheckConstraint(
            "item_type IN ('term', 'theme')",
            name="ck_interest_context_draft_items_type",
        ),
        sa.CheckConstraint(
            "confidence IN ('low', 'medium', 'high')",
            name="ck_interest_context_draft_items_confidence",
        ),
        sa.CheckConstraint(
            "status IN ('pending_review', 'approved', 'rejected')",
            name="ck_interest_context_draft_items_status",
        ),
    )
    op.create_index(
        "ix_interest_context_draft_items_context_score",
        "interest_context_draft_items",
        ["context_id", "score"],
    )
    op.create_index(
        "uq_interest_context_draft_items_identity",
        "interest_context_draft_items",
        ["draft_run_id", "item_type", "normalized_key"],
        unique=True,
    )

    _replace_job_type_constraint(_JOB_TYPES_WITH_DRAFT)


def downgrade() -> None:
    _replace_job_type_constraint(_PREVIOUS_JOB_TYPES)
    op.drop_index(
        "uq_interest_context_draft_items_identity",
        table_name="interest_context_draft_items",
    )
    op.drop_index(
        "ix_interest_context_draft_items_context_score",
        table_name="interest_context_draft_items",
    )
    op.drop_table("interest_context_draft_items")
    op.drop_index(
        "ix_interest_context_draft_runs_context_created",
        table_name="interest_context_draft_runs",
    )
    op.drop_table("interest_context_draft_runs")


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
