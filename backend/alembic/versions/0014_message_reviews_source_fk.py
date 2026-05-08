"""message reviews source foreign key

Revision ID: 0014_message_reviews_source_fk
Revises: 0013_message_reviews
Create Date: 2026-05-08
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014_message_reviews_source_fk"
down_revision: str | None = "0013_message_reviews"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_message_reviews_source_message",
        "message_reviews",
        "telegram_source_messages",
        ["source_message_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_message_reviews_source_message", "message_reviews", type_="foreignkey")
