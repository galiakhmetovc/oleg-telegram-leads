"""Allow manual non-lead and maybe examples.

Revision ID: 0013_manual_example_input_types
Revises: 0012_lead_inbox_performance_indexes
Create Date: 2026-04-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013_manual_example_input_types"
down_revision: str | None = "0012_lead_inbox_performance_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_UPGRADED_INPUT_TYPES = (
    "input_type IN ('telegram_link', 'forwarded_message', 'manual_text', "
    "'catalog_note', 'lead_example', 'non_lead_example', 'maybe_example', "
    "'catalog_item', 'catalog_term', 'catalog_offer', 'catalog_relation', "
    "'catalog_attribute')"
)

_PREVIOUS_INPUT_TYPES = (
    "input_type IN ('telegram_link', 'forwarded_message', 'manual_text', "
    "'catalog_note', 'lead_example', 'catalog_item', 'catalog_term', "
    "'catalog_offer', 'catalog_relation', 'catalog_attribute')"
)


def upgrade() -> None:
    with op.batch_alter_table("manual_inputs") as batch_op:
        batch_op.drop_constraint("ck_manual_inputs_type", type_="check")
        batch_op.create_check_constraint("ck_manual_inputs_type", _UPGRADED_INPUT_TYPES)


def downgrade() -> None:
    with op.batch_alter_table("manual_inputs") as batch_op:
        batch_op.drop_constraint("ck_manual_inputs_type", type_="check")
        batch_op.create_check_constraint("ck_manual_inputs_type", _PREVIOUS_INPUT_TYPES)
