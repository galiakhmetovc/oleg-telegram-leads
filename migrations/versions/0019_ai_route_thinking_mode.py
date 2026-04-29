"""Add provider-neutral thinking mode to AI agent routes.

Revision ID: 0019_ai_route_thinking_mode
Revises: 0018_account_scoped_ai_leases
Create Date: 2026-04-29
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0019_ai_route_thinking_mode"
down_revision: str | None = "0018_account_scoped_ai_leases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("ai_agent_routes") as batch_op:
        batch_op.add_column(
            sa.Column("thinking_mode", sa.String(32), nullable=False, server_default="off")
        )


def downgrade() -> None:
    with op.batch_alter_table("ai_agent_routes") as batch_op:
        batch_op.drop_column("thinking_mode")
