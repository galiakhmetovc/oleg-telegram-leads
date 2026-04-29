"""Create backup and restore foundation tables.

Revision ID: 0010_backup_restore_foundation
Revises: 0009_external_page_jobs
Create Date: 2026-04-29
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0010_backup_restore_foundation"
down_revision: str | None = "0009_external_page_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backup_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("backup_type", sa.String(64), nullable=False),
        sa.Column("storage_backend", sa.String(64), nullable=False),
        sa.Column("storage_uri", sa.String(1024), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("manifest_json", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "backup_type IN ('sqlite', 'archives', 'artifacts', 'sessions', "
            "'config', 'secrets_manifest', 'full')",
            name="ck_backup_runs_type",
        ),
        sa.CheckConstraint(
            "storage_backend IN ('local', 's3_compatible')",
            name="ck_backup_runs_storage_backend",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'verified', 'expired')",
            name="ck_backup_runs_status",
        ),
    )
    op.create_index("ix_backup_runs_status_started", "backup_runs", ["status", "started_at"])

    op.create_table(
        "restore_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("backup_run_id", sa.String(36), nullable=False),
        sa.Column("restore_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("target_path", sa.String(1024), nullable=True),
        sa.Column("validation_status", sa.String(32), nullable=False),
        sa.Column("validation_details_json", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["backup_run_id"], ["backup_runs.id"]),
        sa.CheckConstraint(
            "restore_type IN ('sqlite', 'archives', 'artifacts', 'sessions', "
            "'config', 'full', 'dry_run')",
            name="ck_restore_runs_type",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_restore_runs_status",
        ),
        sa.CheckConstraint(
            "validation_status IN ('not_checked', 'passed', 'failed')",
            name="ck_restore_runs_validation_status",
        ),
    )
    op.create_index("ix_restore_runs_status_started", "restore_runs", ["status", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_restore_runs_status_started", table_name="restore_runs")
    op.drop_table("restore_runs")
    op.drop_index("ix_backup_runs_status_started", table_name="backup_runs")
    op.drop_table("backup_runs")
