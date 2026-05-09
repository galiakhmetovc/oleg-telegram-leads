"""golden examples

Revision ID: 0027_golden_examples
Revises: 0026_config_v3_taxonomy
Create Date: 2026-05-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027_golden_examples"
down_revision: str | None = "0026_config_v3_taxonomy"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "golden_examples",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("expected_verdict", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("source_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_chat_title", sa.Text(), nullable=True),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_message_url", sa.Text(), nullable=True),
        sa.Column("last_enrichment_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["last_enrichment_job_id"], ["enrichment_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_message_id"], ["telegram_source_messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_message_id", name="uq_golden_examples_source_message_id"),
    )
    op.create_index(
        "ix_golden_examples_created_at",
        "golden_examples",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_golden_examples_created_at", table_name="golden_examples")
    op.drop_table("golden_examples")
