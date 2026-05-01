"""Allow Postgres database backup records.

Revision ID: 0027_postgres_backup_type
Revises: 0026_entity_enrichment_registry
Create Date: 2026-05-01
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0027_postgres_backup_type"
down_revision: str | None = "0026_entity_enrichment_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BACKUP_TYPES_WITH_POSTGRES = (
    "backup_type IN ('sqlite', 'postgres_pg_dump', 'archives', 'artifacts', "
    "'sessions', 'config', 'secrets_manifest', 'full')"
)

_PREVIOUS_BACKUP_TYPES = (
    "backup_type IN ('sqlite', 'archives', 'artifacts', 'sessions', "
    "'config', 'secrets_manifest', 'full')"
)


def upgrade() -> None:
    with op.batch_alter_table("backup_runs", **_batch_kwargs()) as batch_op:
        batch_op.drop_constraint("ck_backup_runs_type", type_="check")
        batch_op.create_check_constraint("ck_backup_runs_type", _BACKUP_TYPES_WITH_POSTGRES)


def downgrade() -> None:
    with op.batch_alter_table("backup_runs", **_batch_kwargs()) as batch_op:
        batch_op.drop_constraint("ck_backup_runs_type", type_="check")
        batch_op.create_check_constraint("ck_backup_runs_type", _PREVIOUS_BACKUP_TYPES)


def _batch_kwargs() -> dict[str, str]:
    return {"recreate": "always"} if op.get_bind().dialect.name == "sqlite" else {}
