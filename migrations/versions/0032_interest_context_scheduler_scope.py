"""Allow scheduler jobs scoped to interest contexts.

Revision ID: 0032_interest_context_scheduler_scope
Revises: 0031_scheduler_partial_idempotency_index
Create Date: 2026-05-05
"""

from collections.abc import Sequence
import re

from alembic import op
import sqlalchemy as sa

revision: str = "0032_interest_context_scheduler_scope"
down_revision: str | None = "0031_scheduler_partial_idempotency_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCOPE_TYPES_WITH_INTEREST_CONTEXT = (
    "scope_type IN ('global', 'telegram_userbot', 'telegram_source', "
    "'interest_context', 'ai_provider', 'ai_model', 'parser', 'archive', 'backup')"
)

_PREVIOUS_SCOPE_TYPES = (
    "scope_type IN ('global', 'telegram_userbot', 'telegram_source', "
    "'ai_provider', 'ai_model', 'parser', 'archive', 'backup')"
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        if not _scheduler_jobs_allow_interest_context_scope(bind):
            _replace_sqlite_scheduler_scope_type_constraint(
                bind,
                _SCOPE_TYPES_WITH_INTEREST_CONTEXT,
            )
        return
    with op.batch_alter_table("scheduler_jobs") as batch_op:
        batch_op.drop_constraint("ck_scheduler_jobs_scope_type", type_="check")
        batch_op.create_check_constraint(
            "ck_scheduler_jobs_scope_type",
            _SCOPE_TYPES_WITH_INTEREST_CONTEXT,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        _replace_sqlite_scheduler_scope_type_constraint(bind, _PREVIOUS_SCOPE_TYPES)
        return
    with op.batch_alter_table("scheduler_jobs") as batch_op:
        batch_op.drop_constraint("ck_scheduler_jobs_scope_type", type_="check")
        batch_op.create_check_constraint("ck_scheduler_jobs_scope_type", _PREVIOUS_SCOPE_TYPES)


def _scheduler_jobs_allow_interest_context_scope(bind) -> bool:  # noqa: ANN001
    sql = bind.execute(
        sa.text("select sql from sqlite_master where type='table' and name='scheduler_jobs'")
    ).scalar_one()
    return "'interest_context'" in str(sql)


def _replace_sqlite_scheduler_scope_type_constraint(bind, replacement: str) -> None:  # noqa: ANN001
    sql = str(
        bind.execute(
            sa.text("select sql from sqlite_master where type='table' and name='scheduler_jobs'")
        ).scalar_one()
    )
    updated = re.sub(r"scope_type\s+IN\s*\([^)]*\)", replacement, sql, count=1)
    if updated == sql and replacement not in sql:
        raise RuntimeError("Could not locate scheduler scope_type check constraint")
    bind.execute(sa.text("PRAGMA writable_schema=ON"))
    bind.execute(
        sa.text(
            "update sqlite_master set sql = :sql where type = 'table' and name = 'scheduler_jobs'"
        ),
        {"sql": updated},
    )
    schema_version = int(bind.execute(sa.text("PRAGMA schema_version")).scalar_one())
    bind.execute(sa.text(f"PRAGMA schema_version = {schema_version + 1}"))
    bind.execute(sa.text("PRAGMA writable_schema=OFF"))
