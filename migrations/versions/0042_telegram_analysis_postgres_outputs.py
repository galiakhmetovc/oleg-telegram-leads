"""Store Telegram analysis stage outputs in Postgres.

Revision ID: 0042_telegram_analysis_postgres_outputs
Revises: 0041_telegram_prepared_documents
Create Date: 2026-05-06
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0042_telegram_analysis_postgres_outputs"
down_revision: str | None = "0041_telegram_prepared_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_analysis_stage_outputs",
        sa.Column("id", sa.String(length=160), primary_key=True),
        sa.Column("raw_export_run_id", sa.String(length=36), nullable=False),
        sa.Column("monitored_source_id", sa.String(length=36), nullable=False),
        sa.Column("stage_key", sa.String(length=80), nullable=False),
        sa.Column("output_key", sa.String(length=80), nullable=False),
        sa.Column("output_kind", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("artifact_path", sa.String(length=1024), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_telegram_analysis_stage_outputs_run_stage",
        "telegram_analysis_stage_outputs",
        ["raw_export_run_id", "stage_key"],
    )
    op.create_index(
        "uq_telegram_analysis_stage_outputs_run_stage_key",
        "telegram_analysis_stage_outputs",
        ["raw_export_run_id", "stage_key", "output_key"],
        unique=True,
    )

    op.create_table(
        "telegram_entity_candidates",
        sa.Column("id", sa.String(length=160), primary_key=True),
        sa.Column("raw_export_run_id", sa.String(length=36), nullable=False),
        sa.Column("monitored_source_id", sa.String(length=36), nullable=False),
        sa.Column("entity_id", sa.String(length=80), nullable=False),
        sa.Column("group_id", sa.String(length=80), nullable=False),
        sa.Column("canonical_text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("lemma_text", sa.Text(), nullable=False),
        sa.Column("pos_pattern_json", sa.JSON(), nullable=True),
        sa.Column("mention_count", sa.Integer(), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("source_refs_json", sa.JSON(), nullable=True),
        sa.Column("example_contexts_json", sa.JSON(), nullable=True),
        sa.Column("entity_type_counts_json", sa.JSON(), nullable=True),
        sa.Column("group_confidence", sa.String(length=32), nullable=False),
        sa.Column("group_method", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("ranking_status", sa.String(length=64), nullable=True),
        sa.Column("reasons_json", sa.JSON(), nullable=True),
        sa.Column("penalties_json", sa.JSON(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_telegram_entity_candidates_run_status",
        "telegram_entity_candidates",
        ["raw_export_run_id", "ranking_status"],
    )
    op.create_index(
        "ix_telegram_entity_candidates_run_score",
        "telegram_entity_candidates",
        ["raw_export_run_id", "score"],
    )
    op.create_index(
        "ix_telegram_entity_candidates_run_normalized",
        "telegram_entity_candidates",
        ["raw_export_run_id", "normalized_text"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_telegram_entity_candidates_run_normalized",
        table_name="telegram_entity_candidates",
    )
    op.drop_index(
        "ix_telegram_entity_candidates_run_score",
        table_name="telegram_entity_candidates",
    )
    op.drop_index(
        "ix_telegram_entity_candidates_run_status",
        table_name="telegram_entity_candidates",
    )
    op.drop_table("telegram_entity_candidates")
    op.drop_index(
        "uq_telegram_analysis_stage_outputs_run_stage_key",
        table_name="telegram_analysis_stage_outputs",
    )
    op.drop_index(
        "ix_telegram_analysis_stage_outputs_run_stage",
        table_name="telegram_analysis_stage_outputs",
    )
    op.drop_table("telegram_analysis_stage_outputs")
