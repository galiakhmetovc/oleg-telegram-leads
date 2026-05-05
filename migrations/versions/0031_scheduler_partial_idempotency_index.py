"""Make scheduler idempotency unique only for active jobs.

Revision ID: 0031_scheduler_partial_idempotency_index
Revises: 0030_prepare_interest_context_data_job
Create Date: 2026-05-05
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0031_scheduler_partial_idempotency_index"
down_revision: str | None = "0030_prepare_interest_context_data_job"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTIVE_IDEMPOTENCY_WHERE = sa.text(
    "idempotency_key IS NOT NULL AND status IN ('queued', 'running')"
)


def upgrade() -> None:
    op.drop_index("uq_scheduler_jobs_active_idempotency", table_name="scheduler_jobs")
    op.create_index(
        "uq_scheduler_jobs_active_idempotency",
        "scheduler_jobs",
        ["idempotency_key"],
        unique=True,
        postgresql_where=_ACTIVE_IDEMPOTENCY_WHERE,
        sqlite_where=_ACTIVE_IDEMPOTENCY_WHERE,
    )


def downgrade() -> None:
    op.drop_index("uq_scheduler_jobs_active_idempotency", table_name="scheduler_jobs")
    op.create_index(
        "uq_scheduler_jobs_active_idempotency",
        "scheduler_jobs",
        ["idempotency_key"],
        unique=True,
        sqlite_where=_ACTIVE_IDEMPOTENCY_WHERE,
    )
