"""add enrichment task outbox

Revision ID: 0017_enrichment_task_outbox
Revises: 0016_message_review_tags
Create Date: 2026-05-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_enrichment_task_outbox"
down_revision: str | None = "0016_message_review_tags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "enrichment_task_outbox",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["enrichment_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("job_id"),
    )
    op.create_index(
        "ix_enrichment_task_outbox_claim",
        "enrichment_task_outbox",
        ["status", "created_at", "job_id"],
    )
    op.execute(
        """
        insert into enrichment_task_outbox (
            job_id,
            task_name,
            status,
            attempts,
            last_error,
            claimed_at,
            created_at,
            updated_at,
            published_at
        )
        select
            id,
            'app.worker.tasks.enrich_text_job',
            'pending',
            0,
            null,
            null,
            created_at,
            updated_at,
            null
        from enrichment_jobs
        where status = 'queued'
        on conflict (job_id) do nothing
        """
    )


def downgrade() -> None:
    op.drop_index("ix_enrichment_task_outbox_claim", table_name="enrichment_task_outbox")
    op.drop_table("enrichment_task_outbox")
