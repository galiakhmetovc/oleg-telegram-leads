"""Allow lead LLM shadow decision records.

Revision ID: 0014_lead_llm_shadow_decisions
Revises: 0013_manual_example_input_types
Create Date: 2026-04-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014_lead_llm_shadow_decisions"
down_revision: str | None = "0013_manual_example_input_types"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_UPGRADED_DECISION_TYPES = (
    "decision_type IN ('lead_detection', 'lead_detection_shadow', 'catalog_extraction', "
    "'notification_policy', 'clustering', 'crm_conversion', 'contact_reason', "
    "'research_match', 'manual')"
)

_PREVIOUS_DECISION_TYPES = (
    "decision_type IN ('lead_detection', 'catalog_extraction', 'notification_policy', "
    "'clustering', 'crm_conversion', 'contact_reason', 'research_match', 'manual')"
)


def upgrade() -> None:
    with op.batch_alter_table("decision_records") as batch_op:
        batch_op.drop_constraint("ck_decision_records_type", type_="check")
        batch_op.create_check_constraint("ck_decision_records_type", _UPGRADED_DECISION_TYPES)


def downgrade() -> None:
    with op.batch_alter_table("decision_records") as batch_op:
        batch_op.drop_constraint("ck_decision_records_type", type_="check")
        batch_op.create_check_constraint("ck_decision_records_type", _PREVIOUS_DECISION_TYPES)
