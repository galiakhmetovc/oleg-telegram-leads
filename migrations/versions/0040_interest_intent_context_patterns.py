"""Add context pattern controls to intent layers.

Revision ID: 0040_interest_intent_context_patterns
Revises: 0039_interest_intent_layers
Create Date: 2026-05-06
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0040_interest_intent_context_patterns"
down_revision: str | None = "0039_interest_intent_layers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("interest_intent_layers", **_batch_kwargs()) as batch_op:
        batch_op.add_column(sa.Column("context_patterns_json", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "require_context_match",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("interest_intent_layers", **_batch_kwargs()) as batch_op:
        batch_op.drop_column("require_context_match")
        batch_op.drop_column("context_patterns_json")


def _batch_kwargs() -> dict[str, str]:
    return {"recreate": "always"} if op.get_bind().dialect.name == "sqlite" else {}
