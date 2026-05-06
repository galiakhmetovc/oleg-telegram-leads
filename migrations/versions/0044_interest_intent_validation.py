"""Add intent validation runs and recommendations.

Revision ID: 0044_interest_intent_validation
Revises: 0043_feedback_interest_intent_match
Create Date: 2026-05-06
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0044_interest_intent_validation"
down_revision: str | None = "0043_feedback_interest_intent_match"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "interest_intent_validation_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("context_id", sa.String(length=36), nullable=False),
        sa.Column("source_intent_run_id", sa.String(length=36), nullable=False),
        sa.Column("source_intent_layer_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=True),
        sa.Column("model", sa.String(length=160), nullable=True),
        sa.Column("model_profile", sa.String(length=160), nullable=True),
        sa.Column("ai_provider_account_id", sa.String(length=36), nullable=True),
        sa.Column("ai_model_id", sa.String(length=36), nullable=True),
        sa.Column("ai_model_profile_id", sa.String(length=36), nullable=True),
        sa.Column("ai_agent_route_id", sa.String(length=36), nullable=True),
        sa.Column("prompt_version", sa.String(length=80), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=True),
        sa.Column("request_json", sa.JSON(), nullable=True),
        sa.Column("response_json", sa.JSON(), nullable=True),
        sa.Column("parsed_response_json", sa.JSON(), nullable=True),
        sa.Column("summary_json", sa.JSON(), nullable=True),
        sa.Column("recommendation_count", sa.Integer(), nullable=False),
        sa.Column("created_layer_id", sa.String(length=36), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_interest_intent_validation_runs_context",
        "interest_intent_validation_runs",
        ["context_id", "created_at"],
    )
    op.create_index(
        "ix_interest_intent_validation_runs_source_run",
        "interest_intent_validation_runs",
        ["source_intent_run_id"],
    )

    op.create_table(
        "interest_intent_validation_recommendations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("validation_run_id", sa.String(length=36), nullable=False),
        sa.Column("context_id", sa.String(length=36), nullable=False),
        sa.Column("source_intent_run_id", sa.String(length=36), nullable=False),
        sa.Column("recommendation_type", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("confidence", sa.String(length=32), nullable=False),
        sa.Column("proposed_changes_json", sa.JSON(), nullable=True),
        sa.Column("impact_preview_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.String(length=160), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_interest_intent_validation_recommendations_run",
        "interest_intent_validation_recommendations",
        ["validation_run_id", "status"],
    )
    op.create_index(
        "ix_interest_intent_validation_recommendations_context",
        "interest_intent_validation_recommendations",
        ["context_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_interest_intent_validation_recommendations_context",
        table_name="interest_intent_validation_recommendations",
    )
    op.drop_index(
        "ix_interest_intent_validation_recommendations_run",
        table_name="interest_intent_validation_recommendations",
    )
    op.drop_table("interest_intent_validation_recommendations")
    op.drop_index(
        "ix_interest_intent_validation_runs_source_run",
        table_name="interest_intent_validation_runs",
    )
    op.drop_index(
        "ix_interest_intent_validation_runs_context",
        table_name="interest_intent_validation_runs",
    )
    op.drop_table("interest_intent_validation_runs")
