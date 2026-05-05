"""Persist reviewable LLM recommendations for interest-core candidates.

Revision ID: 0036_interest_core_candidate_reviews
Revises: 0035_interest_core_candidate_enhancement
Create Date: 2026-05-05
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0036_interest_core_candidate_reviews"
down_revision: str | None = "0035_interest_core_candidate_enhancement"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "interest_core_candidate_reviews",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("context_id", sa.String(length=36), nullable=False),
        sa.Column("enhancement_job_id", sa.String(length=36), nullable=False),
        sa.Column("draft_run_id", sa.String(length=36), nullable=True),
        sa.Column("source_candidate_id", sa.String(length=80), nullable=True),
        sa.Column("recommendation_type", sa.String(length=32), nullable=False),
        sa.Column("canonical_name", sa.String(length=300), nullable=True),
        sa.Column("category", sa.String(length=160), nullable=True),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("merge_into_candidate_id", sa.String(length=80), nullable=True),
        sa.Column("confidence", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("synonyms_json", sa.JSON(), nullable=True),
        sa.Column("lead_signals_json", sa.JSON(), nullable=True),
        sa.Column("noise_patterns_json", sa.JSON(), nullable=True),
        sa.Column("evidence_refs_json", sa.JSON(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.String(length=160), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "recommendation_type IN ('improved', 'new', 'rejected')",
            name="ck_interest_core_candidate_reviews_type",
        ),
        sa.CheckConstraint(
            "decision IN ('keep', 'merge', 'reject', 'needs_review', 'new')",
            name="ck_interest_core_candidate_reviews_decision",
        ),
        sa.CheckConstraint(
            "confidence IN ('low', 'medium', 'high')",
            name="ck_interest_core_candidate_reviews_confidence",
        ),
        sa.CheckConstraint(
            "status IN ('pending_review', 'approved', 'rejected', 'applied')",
            name="ck_interest_core_candidate_reviews_status",
        ),
    )
    op.create_index(
        "ix_interest_core_candidate_reviews_context_status",
        "interest_core_candidate_reviews",
        ["context_id", "status"],
    )
    op.create_index(
        "ix_interest_core_candidate_reviews_job",
        "interest_core_candidate_reviews",
        ["enhancement_job_id"],
    )
    op.create_index(
        "ix_interest_core_candidate_reviews_context_job",
        "interest_core_candidate_reviews",
        ["context_id", "enhancement_job_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_interest_core_candidate_reviews_context_job",
        table_name="interest_core_candidate_reviews",
    )
    op.drop_index(
        "ix_interest_core_candidate_reviews_job",
        table_name="interest_core_candidate_reviews",
    )
    op.drop_index(
        "ix_interest_core_candidate_reviews_context_status",
        table_name="interest_core_candidate_reviews",
    )
    op.drop_table("interest_core_candidate_reviews")
