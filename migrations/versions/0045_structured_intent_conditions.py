"""Add structured intent-layer exclusion conditions.

Revision ID: 0045_structured_intent_conditions
Revises: 0044_interest_intent_validation
Create Date: 2026-05-06
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0045_structured_intent_conditions"
down_revision: str | None = "0044_interest_intent_validation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("interest_intent_layers", **_batch_kwargs()) as batch_op:
        batch_op.add_column(sa.Column("exclude_lemmas_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("exclude_phrases_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("semantic_negative_examples_json", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "semantic_negative_threshold",
                sa.Float(),
                nullable=False,
                server_default="0.78",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("interest_intent_layers", **_batch_kwargs()) as batch_op:
        batch_op.drop_column("semantic_negative_threshold")
        batch_op.drop_column("semantic_negative_examples_json")
        batch_op.drop_column("exclude_phrases_json")
        batch_op.drop_column("exclude_lemmas_json")


def _batch_kwargs() -> dict[str, str]:
    return {"recreate": "always"} if op.get_bind().dialect.name == "sqlite" else {}
