"""Allow feedback for interest intent matches.

Revision ID: 0043_feedback_interest_intent_match
Revises: 0042_telegram_analysis_postgres_outputs
Create Date: 2026-05-06
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0043_feedback_interest_intent_match"
down_revision: str | None = "0042_telegram_analysis_postgres_outputs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TARGET_TYPES_WITH_INTEREST_INTENT_MATCH = (
    "target_type IN ('lead_cluster', 'lead_event', 'lead_match', "
    "'source_message', 'sender_profile', 'catalog_item', 'catalog_term', "
    "'category', 'source', 'manual_input', 'client', 'contact', "
    "'client_object', 'client_interest', 'client_asset', 'opportunity', "
    "'support_case', 'contact_reason', 'task', 'interest_intent_match')"
)

_PREVIOUS_TARGET_TYPES = (
    "target_type IN ('lead_cluster', 'lead_event', 'lead_match', "
    "'source_message', 'sender_profile', 'catalog_item', 'catalog_term', "
    "'category', 'source', 'manual_input', 'client', 'contact', "
    "'client_object', 'client_interest', 'client_asset', 'opportunity', "
    "'support_case', 'contact_reason', 'task')"
)


def upgrade() -> None:
    with op.batch_alter_table("feedback_events", **_batch_kwargs()) as batch_op:
        batch_op.drop_constraint("ck_feedback_events_target_type", type_="check")
        batch_op.create_check_constraint(
            "ck_feedback_events_target_type",
            _TARGET_TYPES_WITH_INTEREST_INTENT_MATCH,
        )


def downgrade() -> None:
    with op.batch_alter_table("feedback_events", **_batch_kwargs()) as batch_op:
        batch_op.drop_constraint("ck_feedback_events_target_type", type_="check")
        batch_op.create_check_constraint(
            "ck_feedback_events_target_type",
            _PREVIOUS_TARGET_TYPES,
        )


def _batch_kwargs() -> dict[str, str]:
    return {"recreate": "always"} if op.get_bind().dialect.name == "sqlite" else {}
