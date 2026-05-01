"""Add canonical entity enrichment registry.

Revision ID: 0026_entity_enrichment_registry
Revises: 0025_export_telegram_raw_job
Create Date: 2026-04-30
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0026_entity_enrichment_registry"
down_revision: str | None = "0025_export_telegram_raw_job"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "canonical_entities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("canonical_name", sa.String(512), nullable=False),
        sa.Column("normalized_name", sa.String(512), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_from_result_id", sa.String(36), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('auto_pending', 'approved', 'rejected', 'merged')",
            name="ck_canonical_entities_status",
        ),
        sa.UniqueConstraint("normalized_name", name="uq_canonical_entities_normalized_name"),
    )
    op.create_index(
        "ix_canonical_entities_type_status",
        "canonical_entities",
        ["entity_type", "status"],
    )

    op.create_table(
        "canonical_entity_aliases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("canonical_entity_id", sa.String(36), nullable=False),
        sa.Column("alias", sa.String(512), nullable=False),
        sa.Column("normalized_alias", sa.String(512), nullable=False),
        sa.Column("alias_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("evidence_refs_json", sa.JSON(), nullable=True),
        sa.Column("created_from_result_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["canonical_entity_id"], ["canonical_entities.id"]),
        sa.CheckConstraint(
            "status IN ('auto_pending', 'approved', 'rejected')",
            name="ck_canonical_entity_aliases_status",
        ),
        sa.UniqueConstraint("normalized_alias", name="uq_canonical_entity_aliases_normalized"),
    )
    op.create_index(
        "ix_canonical_entity_aliases_entity",
        "canonical_entity_aliases",
        ["canonical_entity_id"],
    )

    op.create_table(
        "entity_enrichment_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("raw_export_run_id", sa.String(36), nullable=False),
        sa.Column("ranked_entities_path", sa.String(1024), nullable=False),
        sa.Column("context_snapshot_id", sa.String(80), nullable=False),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("model", sa.String(160), nullable=True),
        sa.Column("model_profile", sa.String(160), nullable=True),
        sa.Column("prompt_version", sa.String(80), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["raw_export_run_id"], ["telegram_raw_export_runs.id"]),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name="ck_entity_enrichment_runs_status",
        ),
    )
    op.create_index(
        "ix_entity_enrichment_runs_raw_created",
        "entity_enrichment_runs",
        ["raw_export_run_id", "created_at"],
    )

    op.create_table(
        "entity_enrichment_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("sequence_index", sa.Integer(), nullable=False),
        sa.Column("ranked_entity_id", sa.String(36), nullable=False),
        sa.Column("ranked_entity_text", sa.String(512), nullable=False),
        sa.Column("canonical_entity_id", sa.String(36), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=True),
        sa.Column("response_json", sa.JSON(), nullable=True),
        sa.Column("parsed_response_json", sa.JSON(), nullable=True),
        sa.Column("context_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("source_refs_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["entity_enrichment_runs.id"]),
        sa.ForeignKeyConstraint(["canonical_entity_id"], ["canonical_entities.id"]),
        sa.UniqueConstraint("run_id", "ranked_entity_id", name="uq_entity_enrichment_result"),
    )
    op.create_index(
        "ix_entity_enrichment_results_entity",
        "entity_enrichment_results",
        ["canonical_entity_id"],
    )

    op.create_table(
        "canonical_merge_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("left_canonical_entity_id", sa.String(36), nullable=True),
        sa.Column("right_canonical_entity_id", sa.String(36), nullable=True),
        sa.Column("proposed_name", sa.String(512), nullable=False),
        sa.Column("normalized_name", sa.String(512), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=True),
        sa.Column("created_from_result_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["left_canonical_entity_id"], ["canonical_entities.id"]),
        sa.ForeignKeyConstraint(["right_canonical_entity_id"], ["canonical_entities.id"]),
        sa.CheckConstraint(
            "status IN ('pending_review', 'approved', 'rejected', 'merged')",
            name="ck_canonical_merge_candidates_status",
        ),
    )
    op.create_index(
        "ix_canonical_merge_candidates_status",
        "canonical_merge_candidates",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_canonical_merge_candidates_status",
        table_name="canonical_merge_candidates",
    )
    op.drop_table("canonical_merge_candidates")
    op.drop_index(
        "ix_entity_enrichment_results_entity",
        table_name="entity_enrichment_results",
    )
    op.drop_table("entity_enrichment_results")
    op.drop_index(
        "ix_entity_enrichment_runs_raw_created",
        table_name="entity_enrichment_runs",
    )
    op.drop_table("entity_enrichment_runs")
    op.drop_index(
        "ix_canonical_entity_aliases_entity",
        table_name="canonical_entity_aliases",
    )
    op.drop_table("canonical_entity_aliases")
    op.drop_index("ix_canonical_entities_type_status", table_name="canonical_entities")
    op.drop_table("canonical_entities")
