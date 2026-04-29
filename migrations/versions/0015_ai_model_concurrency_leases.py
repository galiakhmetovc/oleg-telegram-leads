"""Add AI model concurrency lease table.

Revision ID: 0015_ai_model_concurrency_leases
Revises: 0014_lead_llm_shadow_decisions
Create Date: 2026-04-29
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0015_ai_model_concurrency_leases"
down_revision: str | None = "0014_lead_llm_shadow_decisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_model_concurrency_leases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("normalized_model", sa.String(160), nullable=False),
        sa.Column("worker_name", sa.String(160), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
    )
    op.create_index(
        "ix_ai_model_leases_model_expires",
        "ai_model_concurrency_leases",
        ["provider", "normalized_model", "lease_expires_at"],
    )
    op.create_index(
        "ix_ai_model_leases_worker",
        "ai_model_concurrency_leases",
        ["worker_name"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_model_leases_worker", table_name="ai_model_concurrency_leases")
    op.drop_index("ix_ai_model_leases_model_expires", table_name="ai_model_concurrency_leases")
    op.drop_table("ai_model_concurrency_leases")
