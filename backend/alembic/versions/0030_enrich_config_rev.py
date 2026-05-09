"""enrichment config revision

Revision ID: 0030_enrich_config_rev
Revises: 0029_video_kit_help_intent
Create Date: 2026-05-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030_enrich_config_rev"
down_revision: str | None = "0029_video_kit_help_intent"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "enrichment_jobs",
        sa.Column("nlp_config_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("enrichment_jobs", sa.Column("nlp_config_revision", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_enrichment_jobs_nlp_config_revision",
        "enrichment_jobs",
        "nlp_config_revisions",
        ["nlp_config_revision_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_enrichment_jobs_nlp_config_revision",
        "enrichment_jobs",
        ["nlp_config_revision"],
    )


def downgrade() -> None:
    op.drop_index("ix_enrichment_jobs_nlp_config_revision", table_name="enrichment_jobs")
    op.drop_constraint(
        "fk_enrichment_jobs_nlp_config_revision",
        "enrichment_jobs",
        type_="foreignkey",
    )
    op.drop_column("enrichment_jobs", "nlp_config_revision")
    op.drop_column("enrichment_jobs", "nlp_config_revision_id")
