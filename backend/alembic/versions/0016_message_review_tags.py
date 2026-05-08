"""message review structured tags

Revision ID: 0016_message_review_tags
Revises: 0015_outbox_idempotency
Create Date: 2026-05-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_message_review_tags"
down_revision: str | None = "0015_outbox_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "message_reviews",
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.alter_column("message_reviews", "tags", server_default=None)


def downgrade() -> None:
    op.drop_column("message_reviews", "tags")
