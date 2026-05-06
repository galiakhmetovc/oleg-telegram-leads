"""Add configurable interest intent layers.

Revision ID: 0039_interest_intent_layers
Revises: 0038_interest_core_analysis
Create Date: 2026-05-06
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0039_interest_intent_layers"
down_revision: str | None = "0038_interest_core_analysis"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "interest_intent_layers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("context_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("include_patterns_json", sa.JSON(), nullable=True),
        sa.Column("exclude_patterns_json", sa.JSON(), nullable=True),
        sa.Column("include_categories_json", sa.JSON(), nullable=True),
        sa.Column("exclude_categories_json", sa.JSON(), nullable=True),
        sa.Column("include_core_names_json", sa.JSON(), nullable=True),
        sa.Column("exclude_core_names_json", sa.JSON(), nullable=True),
        sa.Column("require_include_match", sa.Boolean(), nullable=False),
        sa.Column("min_score", sa.Float(), nullable=False),
        sa.Column("max_results", sa.Integer(), nullable=False),
        sa.Column("broad_score_weight", sa.Float(), nullable=False),
        sa.Column("intent_hit_weight", sa.Float(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'disabled', 'archived')",
            name="ck_interest_intent_layers_status",
        ),
    )
    op.create_index(
        "ix_interest_intent_layers_context_status",
        "interest_intent_layers",
        ["context_id", "status"],
    )

    op.create_table(
        "interest_intent_analysis_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("context_id", sa.String(length=36), nullable=False),
        sa.Column("intent_layer_id", sa.String(length=36), nullable=False),
        sa.Column("broad_analysis_run_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_title", sa.String(length=255), nullable=True),
        sa.Column("source_message_count", sa.Integer(), nullable=False),
        sa.Column("broad_match_count", sa.Integer(), nullable=False),
        sa.Column("matched_message_count", sa.Integer(), nullable=False),
        sa.Column("match_count", sa.Integer(), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name="ck_interest_intent_analysis_runs_status",
        ),
    )
    op.create_index(
        "ix_interest_intent_analysis_runs_context_created",
        "interest_intent_analysis_runs",
        ["context_id", "created_at"],
    )
    op.create_index(
        "ix_interest_intent_analysis_runs_broad",
        "interest_intent_analysis_runs",
        ["broad_analysis_run_id"],
    )

    op.create_table(
        "interest_intent_analysis_matches",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("context_id", sa.String(length=36), nullable=False),
        sa.Column("intent_layer_id", sa.String(length=36), nullable=False),
        sa.Column("source_message_id", sa.String(length=36), nullable=False),
        sa.Column("interest_core_match_id", sa.String(length=36), nullable=False),
        sa.Column("interest_core_item_id", sa.String(length=36), nullable=False),
        sa.Column("telegram_message_id", sa.Integer(), nullable=False),
        sa.Column("message_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sender_id", sa.String(length=80), nullable=True),
        sa.Column("message_text", sa.Text(), nullable=True),
        sa.Column("canonical_name", sa.String(length=300), nullable=True),
        sa.Column("category", sa.String(length=160), nullable=True),
        sa.Column("matched_text", sa.String(length=500), nullable=True),
        sa.Column("match_kind", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("broad_score", sa.Float(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "match_kind IN ('intent_rule')",
            name="ck_interest_intent_analysis_matches_kind",
        ),
    )
    op.create_index(
        "ix_interest_intent_analysis_matches_run_score",
        "interest_intent_analysis_matches",
        ["run_id", "score"],
    )
    op.create_index(
        "ix_interest_intent_analysis_matches_context_date",
        "interest_intent_analysis_matches",
        ["context_id", "message_date"],
    )
    op.create_index(
        "ix_interest_intent_analysis_matches_message",
        "interest_intent_analysis_matches",
        ["source_message_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_interest_intent_analysis_matches_message",
        table_name="interest_intent_analysis_matches",
    )
    op.drop_index(
        "ix_interest_intent_analysis_matches_context_date",
        table_name="interest_intent_analysis_matches",
    )
    op.drop_index(
        "ix_interest_intent_analysis_matches_run_score",
        table_name="interest_intent_analysis_matches",
    )
    op.drop_table("interest_intent_analysis_matches")
    op.drop_index(
        "ix_interest_intent_analysis_runs_broad",
        table_name="interest_intent_analysis_runs",
    )
    op.drop_index(
        "ix_interest_intent_analysis_runs_context_created",
        table_name="interest_intent_analysis_runs",
    )
    op.drop_table("interest_intent_analysis_runs")
    op.drop_index(
        "ix_interest_intent_layers_context_status",
        table_name="interest_intent_layers",
    )
    op.drop_table("interest_intent_layers")
