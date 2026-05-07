"""enrichment jobs

Revision ID: 0001_enrichment_jobs
Revises:
Create Date: 2026-05-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_enrichment_jobs"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "enrichment_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_stage", sa.Text(), nullable=True),
        sa.Column("stage_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stage_progress_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("error", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status in ('queued', 'running', 'completed', 'failed')",
            name="ck_enrichment_jobs_status",
        ),
    )
    op.create_table(
        "enrichment_results",
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("enrichment_jobs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "enrichment_events",
        sa.Column("sequence", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("enrichment_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False),
        sa.Column("current_stage", sa.Text(), nullable=True),
        sa.Column("stage_index", sa.Integer(), nullable=False),
        sa.Column("stage_count", sa.Integer(), nullable=False),
        sa.Column("stage_progress_percent", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_enrichment_events_job_sequence", "enrichment_events", ["job_id", "sequence"])
    op.create_index("ix_enrichment_jobs_status", "enrichment_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_enrichment_jobs_status", table_name="enrichment_jobs")
    op.drop_index("ix_enrichment_events_job_sequence", table_name="enrichment_events")
    op.drop_table("enrichment_events")
    op.drop_table("enrichment_results")
    op.drop_table("enrichment_jobs")
