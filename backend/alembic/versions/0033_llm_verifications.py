"""llm verifications

Revision ID: 0033_llm_verifications
Revises: 0032_alias_fact_duplicate_repair
Create Date: 2026-05-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0033_llm_verifications"
down_revision: str | None = "0032_alias_fact_duplicate_repair"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "llm_verifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("enrichment_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("context_pack", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_response", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_message_id"],
            ["telegram_source_messages.id"],
            name="fk_llm_verifications_source_message",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["enrichment_job_id"],
            ["enrichment_jobs.id"],
            name="fk_llm_verifications_enrichment_job",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_llm_verifications_source_message_created",
        "llm_verifications",
        ["source_message_id", "created_at"],
    )
    op.create_index("ix_llm_verifications_status", "llm_verifications", ["status"])


def downgrade() -> None:
    op.drop_index("ix_llm_verifications_status", table_name="llm_verifications")
    op.drop_index("ix_llm_verifications_source_message_created", table_name="llm_verifications")
    op.drop_table("llm_verifications")
