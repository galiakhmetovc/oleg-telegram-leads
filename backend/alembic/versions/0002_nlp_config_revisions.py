"""nlp config revisions

Revision ID: 0002_nlp_config_revisions
Revises: 0001_enrichment_jobs
Create Date: 2026-05-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_nlp_config_revisions"
down_revision: str | None = "0001_enrichment_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "nlp_config_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source", sa.Text(), nullable=False, server_default="ui"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ux_nlp_config_revisions_revision",
        "nlp_config_revisions",
        ["revision"],
        unique=True,
    )
    op.create_index(
        "ux_nlp_config_revisions_active",
        "nlp_config_revisions",
        ["is_active"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_index("ux_nlp_config_revisions_active", table_name="nlp_config_revisions")
    op.drop_index("ux_nlp_config_revisions_revision", table_name="nlp_config_revisions")
    op.drop_table("nlp_config_revisions")
