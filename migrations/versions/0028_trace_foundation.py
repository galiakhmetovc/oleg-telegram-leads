"""Add product trace foundation.

Revision ID: 0028_trace_foundation
Revises: 0027_postgres_backup_type
Create Date: 2026-05-01
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0028_trace_foundation"
down_revision: str | None = "0027_postgres_backup_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("scheduler_jobs") as batch_op:
        batch_op.add_column(sa.Column("trace_id", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("parent_span_id", sa.String(16), nullable=True))
        batch_op.add_column(sa.Column("trace_context_json", sa.JSON(), nullable=True))
    op.create_index("ix_scheduler_jobs_trace_id", "scheduler_jobs", ["trace_id"])

    with op.batch_alter_table("job_runs") as batch_op:
        batch_op.add_column(sa.Column("trace_id", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("span_id", sa.String(16), nullable=True))
        batch_op.add_column(sa.Column("parent_span_id", sa.String(16), nullable=True))
    op.create_index("ix_job_runs_trace_id", "job_runs", ["trace_id"])

    op.create_table(
        "trace_spans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("trace_id", sa.String(32), nullable=False),
        sa.Column("span_id", sa.String(16), nullable=False),
        sa.Column("parent_span_id", sa.String(16), nullable=True),
        sa.Column("span_name", sa.String(240), nullable=False),
        sa.Column("span_kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("status_message", sa.Text(), nullable=True),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("web_session_id", sa.String(36), nullable=True),
        sa.Column("actor", sa.String(160), nullable=True),
        sa.Column("request_id", sa.String(128), nullable=True),
        sa.Column("request_method", sa.String(16), nullable=True),
        sa.Column("request_path", sa.String(512), nullable=True),
        sa.Column("http_status_code", sa.Integer(), nullable=True),
        sa.Column("resource_type", sa.String(120), nullable=True),
        sa.Column("resource_id", sa.String(128), nullable=True),
        sa.Column("attributes_json", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_trace_spans_trace_id", "trace_spans", ["trace_id"])
    op.create_index("ix_trace_spans_request_id", "trace_spans", ["request_id"])
    op.create_index("ix_trace_spans_user_id", "trace_spans", ["user_id"])
    op.create_index("ix_trace_spans_web_session_id", "trace_spans", ["web_session_id"])
    op.create_index(
        "ix_trace_spans_resource",
        "trace_spans",
        ["resource_type", "resource_id"],
    )

    op.create_table(
        "trace_span_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("trace_id", sa.String(32), nullable=False),
        sa.Column("span_id", sa.String(16), nullable=False),
        sa.Column("event_name", sa.String(240), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("entity_type", sa.String(120), nullable=True),
        sa.Column("entity_id", sa.String(128), nullable=True),
        sa.Column("attributes_json", sa.JSON(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_trace_span_events_trace_id", "trace_span_events", ["trace_id"])
    op.create_index("ix_trace_span_events_span_id", "trace_span_events", ["span_id"])

    op.create_table(
        "trace_span_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("trace_id", sa.String(32), nullable=False),
        sa.Column("span_id", sa.String(16), nullable=False),
        sa.Column("linked_trace_id", sa.String(32), nullable=False),
        sa.Column("linked_span_id", sa.String(16), nullable=True),
        sa.Column("link_type", sa.String(80), nullable=False),
        sa.Column("attributes_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_trace_span_links_trace_id", "trace_span_links", ["trace_id"])
    op.create_index(
        "ix_trace_span_links_linked_trace_id",
        "trace_span_links",
        ["linked_trace_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_trace_span_links_linked_trace_id", table_name="trace_span_links")
    op.drop_index("ix_trace_span_links_trace_id", table_name="trace_span_links")
    op.drop_table("trace_span_links")
    op.drop_index("ix_trace_span_events_span_id", table_name="trace_span_events")
    op.drop_index("ix_trace_span_events_trace_id", table_name="trace_span_events")
    op.drop_table("trace_span_events")
    op.drop_index("ix_trace_spans_resource", table_name="trace_spans")
    op.drop_index("ix_trace_spans_web_session_id", table_name="trace_spans")
    op.drop_index("ix_trace_spans_user_id", table_name="trace_spans")
    op.drop_index("ix_trace_spans_request_id", table_name="trace_spans")
    op.drop_index("ix_trace_spans_trace_id", table_name="trace_spans")
    op.drop_table("trace_spans")
    op.drop_index("ix_job_runs_trace_id", table_name="job_runs")
    with op.batch_alter_table("job_runs") as batch_op:
        batch_op.drop_column("parent_span_id")
        batch_op.drop_column("span_id")
        batch_op.drop_column("trace_id")
    op.drop_index("ix_scheduler_jobs_trace_id", table_name="scheduler_jobs")
    with op.batch_alter_table("scheduler_jobs") as batch_op:
        batch_op.drop_column("trace_context_json")
        batch_op.drop_column("parent_span_id")
        batch_op.drop_column("trace_id")
