"""Allow AI routes to target multiple provider accounts.

Revision ID: 0020_ai_route_account_unique
Revises: 0019_ai_route_thinking_mode
Create Date: 2026-04-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0020_ai_route_account_unique"
down_revision: str | None = "0019_ai_route_thinking_mode"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("ai_agent_routes") as batch_op:
        batch_op.drop_constraint("uq_ai_agent_routes_model_role", type_="unique")
        batch_op.create_unique_constraint(
            "uq_ai_agent_routes_account_model_role",
            ["ai_agent_id", "ai_provider_account_id", "ai_model_id", "route_role"],
        )


def downgrade() -> None:
    with op.batch_alter_table("ai_agent_routes") as batch_op:
        batch_op.drop_constraint("uq_ai_agent_routes_account_model_role", type_="unique")
        batch_op.create_unique_constraint(
            "uq_ai_agent_routes_model_role",
            ["ai_agent_id", "ai_model_id", "route_role"],
        )
