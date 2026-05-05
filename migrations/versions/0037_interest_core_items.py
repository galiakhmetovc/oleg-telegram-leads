"""Create approved interest-core item table.

Revision ID: 0037_interest_core_items
Revises: 0036_interest_core_candidate_reviews
Create Date: 2026-05-05
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0037_interest_core_items"
down_revision: str | None = "0036_interest_core_candidate_reviews"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "interest_core_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("context_id", sa.String(length=36), nullable=False),
        sa.Column("source_review_id", sa.String(length=36), nullable=True),
        sa.Column("source_candidate_id", sa.String(length=80), nullable=True),
        sa.Column("item_type", sa.String(length=64), nullable=False),
        sa.Column("canonical_name", sa.String(length=300), nullable=False),
        sa.Column("category", sa.String(length=160), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("confidence", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("synonyms_json", sa.JSON(), nullable=True),
        sa.Column("lead_signals_json", sa.JSON(), nullable=True),
        sa.Column("noise_patterns_json", sa.JSON(), nullable=True),
        sa.Column("evidence_refs_json", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "item_type IN ('interest', 'need_signal', 'noise_pattern')",
            name="ck_interest_core_items_type",
        ),
        sa.CheckConstraint(
            "confidence IN ('low', 'medium', 'high')",
            name="ck_interest_core_items_confidence",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_interest_core_items_status",
        ),
    )
    op.create_index(
        "ix_interest_core_items_context_status",
        "interest_core_items",
        ["context_id", "status"],
    )
    op.create_index(
        "ix_interest_core_items_context_name",
        "interest_core_items",
        ["context_id", "canonical_name"],
        unique=False,
    )
    op.create_index(
        "ix_interest_core_items_source_review",
        "interest_core_items",
        ["source_review_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_interest_core_items_source_review", table_name="interest_core_items")
    op.drop_index("ix_interest_core_items_context_name", table_name="interest_core_items")
    op.drop_index("ix_interest_core_items_context_status", table_name="interest_core_items")
    op.drop_table("interest_core_items")
