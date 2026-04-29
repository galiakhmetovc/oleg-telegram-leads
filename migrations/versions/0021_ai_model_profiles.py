"""Add AI model profiles.

Revision ID: 0021_ai_model_profiles
Revises: 0020_ai_route_account_unique
Create Date: 2026-04-29
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0021_ai_model_profiles"
down_revision: str | None = "0020_ai_route_account_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_model_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("ai_model_id", sa.String(36), nullable=False),
        sa.Column("profile_key", sa.String(120), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("max_input_tokens", sa.Integer(), nullable=True),
        sa.Column("max_output_tokens", sa.Integer(), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("thinking_mode", sa.String(32), nullable=False),
        sa.Column("structured_output_required", sa.Boolean(), nullable=False),
        sa.Column("response_format_json", sa.JSON(), nullable=True),
        sa.Column("provider_options_json", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ai_model_id"], ["ai_models.id"]),
        sa.UniqueConstraint("ai_model_id", "profile_key", name="uq_ai_model_profiles_key"),
    )
    with op.batch_alter_table("ai_agent_routes") as batch_op:
        batch_op.drop_constraint("uq_ai_agent_routes_account_model_role", type_="unique")
        batch_op.add_column(sa.Column("ai_model_profile_id", sa.String(36), nullable=True))
        batch_op.create_unique_constraint(
            "uq_ai_agent_routes_account_profile_role",
            ["ai_agent_id", "ai_provider_account_id", "ai_model_profile_id", "route_role"],
        )


def downgrade() -> None:
    with op.batch_alter_table("ai_agent_routes") as batch_op:
        batch_op.drop_constraint("uq_ai_agent_routes_account_profile_role", type_="unique")
        batch_op.drop_column("ai_model_profile_id")
        batch_op.create_unique_constraint(
            "uq_ai_agent_routes_account_model_role",
            ["ai_agent_id", "ai_provider_account_id", "ai_model_id", "route_role"],
        )
    op.drop_table("ai_model_profiles")
