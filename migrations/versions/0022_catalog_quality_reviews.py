"""Add catalog quality review jobs.

Revision ID: 0022_catalog_quality_reviews
Revises: 0021_ai_model_profiles
Create Date: 2026-04-29
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0022_catalog_quality_reviews"
down_revision: str | None = "0021_ai_model_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_UPGRADED_JOB_TYPES = (
    "job_type IN ('poll_monitored_source', 'check_source_access', "
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
    "'fetch_external_page', 'generate_contact_reasons', 'send_notifications')"
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "catalog_quality_reviews" not in set(inspector.get_table_names()):
        op.create_table(
            "catalog_quality_reviews",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("catalog_candidate_id", sa.String(36), nullable=False),
            sa.Column("scheduler_job_id", sa.String(36), nullable=True),
            sa.Column("ai_provider_account_id", sa.String(36), nullable=True),
            sa.Column("ai_model_id", sa.String(36), nullable=True),
            sa.Column("ai_model_profile_id", sa.String(36), nullable=True),
            sa.Column("ai_agent_route_id", sa.String(36), nullable=True),
            sa.Column("validator_provider", sa.String(64), nullable=True),
            sa.Column("validator_model", sa.String(160), nullable=False),
            sa.Column("validator_profile", sa.String(120), nullable=True),
            sa.Column("validator_route_role", sa.String(64), nullable=True),
            sa.Column("prompt_version", sa.String(80), nullable=True),
            sa.Column("decision", sa.String(32), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("proposed_changes_json", sa.JSON(), nullable=True),
            sa.Column("evidence_json", sa.JSON(), nullable=True),
            sa.Column("raw_output_json", sa.JSON(), nullable=True),
            sa.Column("token_usage_json", sa.JSON(), nullable=True),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("created_by", sa.String(160), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["catalog_candidate_id"], ["catalog_candidates.id"]),
            sa.ForeignKeyConstraint(["scheduler_job_id"], ["scheduler_jobs.id"]),
            sa.ForeignKeyConstraint(["ai_provider_account_id"], ["ai_provider_accounts.id"]),
            sa.ForeignKeyConstraint(["ai_model_id"], ["ai_models.id"]),
            sa.ForeignKeyConstraint(["ai_model_profile_id"], ["ai_model_profiles.id"]),
            sa.ForeignKeyConstraint(["ai_agent_route_id"], ["ai_agent_routes.id"]),
            sa.CheckConstraint(
                "decision IN ('confirm', 'revise', 'reject', 'merge', 'needs_human')",
                name="ck_catalog_quality_reviews_decision",
            ),
            sa.CheckConstraint(
                "status IN ('completed', 'ignored', 'superseded')",
                name="ck_catalog_quality_reviews_status",
            ),
        )
        inspector = sa.inspect(bind)

    existing_indexes = {index["name"] for index in inspector.get_indexes("catalog_quality_reviews")}
    if "ix_catalog_quality_reviews_candidate_created" not in existing_indexes:
        op.create_index(
            "ix_catalog_quality_reviews_candidate_created",
            "catalog_quality_reviews",
            ["catalog_candidate_id", "created_at"],
        )
    if "ix_catalog_quality_reviews_validator" not in existing_indexes:
        op.create_index(
            "ix_catalog_quality_reviews_validator",
            "catalog_quality_reviews",
            ["validator_model", "validator_profile", "status"],
        )
    if not _scheduler_jobs_allow_quality_validation(bind):
        op.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_scheduler_jobs"))
        with op.batch_alter_table("scheduler_jobs") as batch_op:
            batch_op.drop_constraint("ck_scheduler_jobs_job_type", type_="check")
            batch_op.create_check_constraint("ck_scheduler_jobs_job_type", _UPGRADED_JOB_TYPES)


def downgrade() -> None:
    with op.batch_alter_table("scheduler_jobs") as batch_op:
        batch_op.drop_constraint("ck_scheduler_jobs_job_type", type_="check")
        batch_op.create_check_constraint("ck_scheduler_jobs_job_type", _PREVIOUS_JOB_TYPES)
    op.drop_index("ix_catalog_quality_reviews_validator", table_name="catalog_quality_reviews")
    op.drop_index(
        "ix_catalog_quality_reviews_candidate_created",
        table_name="catalog_quality_reviews",
    )
    op.drop_table("catalog_quality_reviews")


def _scheduler_jobs_allow_quality_validation(bind) -> bool:  # noqa: ANN001
    sql = bind.execute(
        sa.text("select sql from sqlite_master where type='table' and name='scheduler_jobs'")
    ).scalar_one()
    return "catalog_candidate_validation" in str(sql)
