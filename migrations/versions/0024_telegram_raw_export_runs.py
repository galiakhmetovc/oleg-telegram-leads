"""Add Telegram raw export run tracking.

Revision ID: 0024_telegram_raw_export_runs
Revises: 0023_source_from_beginning
Create Date: 2026-04-30
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0024_telegram_raw_export_runs"
down_revision: str | None = "0023_source_from_beginning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_raw_export_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("monitored_source_id", sa.String(36), nullable=False),
        sa.Column("source_ref", sa.String(512), nullable=False),
        sa.Column("source_kind", sa.String(64), nullable=False),
        sa.Column("telegram_id", sa.String(80), nullable=True),
        sa.Column("username", sa.String(160), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("export_format", sa.String(64), nullable=False),
        sa.Column("output_dir", sa.String(1024), nullable=False),
        sa.Column("result_json_path", sa.String(1024), nullable=False),
        sa.Column("messages_jsonl_path", sa.String(1024), nullable=False),
        sa.Column("attachments_jsonl_path", sa.String(1024), nullable=False),
        sa.Column("messages_parquet_path", sa.String(1024), nullable=False),
        sa.Column("attachments_parquet_path", sa.String(1024), nullable=False),
        sa.Column("manifest_path", sa.String(1024), nullable=False),
        sa.Column("message_count", sa.Integer(), nullable=False),
        sa.Column("attachment_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["monitored_source_id"], ["monitored_sources.id"]),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name="ck_telegram_raw_export_runs_status",
        ),
    )
    op.create_index(
        "ix_telegram_raw_export_runs_source_created",
        "telegram_raw_export_runs",
        ["monitored_source_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_telegram_raw_export_runs_source_created",
        table_name="telegram_raw_export_runs",
    )
    op.drop_table("telegram_raw_export_runs")
