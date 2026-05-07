"""analytics imports

Revision ID: 0003_analytics
Revises: 0002_nlp_config_revisions
Create Date: 2026-05-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_analytics"
down_revision: str | None = "0002_nlp_config_revisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analytics_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("input_path", sa.Text(), nullable=False),
        sa.Column("run_dir", sa.Text(), nullable=False),
        sa.Column("processed", sa.Integer(), nullable=False),
        sa.Column("skipped", sa.Integer(), nullable=False),
        sa.Column("failed", sa.Integer(), nullable=False),
        sa.Column("leads", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("summary", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ux_analytics_runs_name", "analytics_runs", ["name"], unique=True)
    op.create_index("ix_analytics_runs_finished_at", "analytics_runs", ["finished_at"])

    op.create_table(
        "analytics_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analytics_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("message_id", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("temperature", sa.Text(), nullable=False),
        sa.Column("solution_areas", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("customer_segments", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("intent_signals", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("noise_signals", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("reasons", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("domain_signals", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("facts", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("signal_types", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("fact_types", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("reason_keys", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("solution_area_types", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("customer_segment_types", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'")),
    )
    op.create_index(
        "ux_analytics_candidates_run_message",
        "analytics_candidates",
        ["run_id", "message_id"],
        unique=True,
    )
    op.create_index("ix_analytics_candidates_run_score", "analytics_candidates", ["run_id", "score"])
    op.create_index("ix_analytics_candidates_temperature", "analytics_candidates", ["temperature"])
    op.create_index(
        "ix_analytics_candidates_signal_types",
        "analytics_candidates",
        ["signal_types"],
        postgresql_using="gin",
    )

    op.create_table(
        "analytics_aggregates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analytics_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index(
        "ux_analytics_aggregates_run_kind_key",
        "analytics_aggregates",
        ["run_id", "kind", "key"],
        unique=True,
    )
    op.create_index("ix_analytics_aggregates_run_kind", "analytics_aggregates", ["run_id", "kind"])


def downgrade() -> None:
    op.drop_index("ix_analytics_aggregates_run_kind", table_name="analytics_aggregates")
    op.drop_index("ux_analytics_aggregates_run_kind_key", table_name="analytics_aggregates")
    op.drop_table("analytics_aggregates")
    op.drop_index("ix_analytics_candidates_signal_types", table_name="analytics_candidates")
    op.drop_index("ix_analytics_candidates_temperature", table_name="analytics_candidates")
    op.drop_index("ix_analytics_candidates_run_score", table_name="analytics_candidates")
    op.drop_index("ux_analytics_candidates_run_message", table_name="analytics_candidates")
    op.drop_table("analytics_candidates")
    op.drop_index("ix_analytics_runs_finished_at", table_name="analytics_runs")
    op.drop_index("ux_analytics_runs_name", table_name="analytics_runs")
    op.drop_table("analytics_runs")
