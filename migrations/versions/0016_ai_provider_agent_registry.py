"""Add AI provider, model, and agent registry tables.

Revision ID: 0016_ai_provider_agent_registry
Revises: 0015_ai_model_concurrency_leases
Create Date: 2026-04-29
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0016_ai_provider_agent_registry"
down_revision: str | None = "0015_ai_model_concurrency_leases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_providers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider_key", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("provider_type", sa.String(80), nullable=False),
        sa.Column("default_base_url", sa.String(512), nullable=True),
        sa.Column("documentation_url", sa.String(512), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider_key", name="uq_ai_providers_key"),
    )
    op.create_table(
        "ai_provider_accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("ai_provider_id", sa.String(36), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("base_url", sa.String(512), nullable=True),
        sa.Column("auth_secret_ref", sa.String(512), nullable=True),
        sa.Column("plan_type", sa.String(80), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("request_timeout_seconds", sa.Float(), nullable=False),
        sa.Column("policy_warning_required", sa.Boolean(), nullable=False),
        sa.Column("policy_warning_acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ai_provider_id"], ["ai_providers.id"]),
        sa.UniqueConstraint("ai_provider_id", "display_name", name="uq_ai_provider_accounts_name"),
    )
    op.create_table(
        "ai_models",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("ai_provider_id", sa.String(36), nullable=False),
        sa.Column("provider_model_name", sa.String(160), nullable=False),
        sa.Column("normalized_model_name", sa.String(160), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("model_type", sa.String(64), nullable=False),
        sa.Column("context_window_tokens", sa.Integer(), nullable=True),
        sa.Column("max_output_tokens", sa.Integer(), nullable=True),
        sa.Column("supports_structured_output", sa.Boolean(), nullable=False),
        sa.Column("supports_json_mode", sa.Boolean(), nullable=False),
        sa.Column("supports_thinking", sa.Boolean(), nullable=False),
        sa.Column("supports_tools", sa.Boolean(), nullable=False),
        sa.Column("supports_streaming", sa.Boolean(), nullable=False),
        sa.Column("supports_image_input", sa.Boolean(), nullable=False),
        sa.Column("supports_document_input", sa.Boolean(), nullable=False),
        sa.Column("supports_audio_input", sa.Boolean(), nullable=False),
        sa.Column("supports_video_input", sa.Boolean(), nullable=False),
        sa.Column("default_temperature", sa.Float(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("source_url", sa.String(512), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ai_provider_id"], ["ai_providers.id"]),
        sa.UniqueConstraint(
            "ai_provider_id",
            "normalized_model_name",
            name="uq_ai_models_provider_normalized_name",
        ),
    )
    op.create_table(
        "ai_model_limits",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("ai_provider_id", sa.String(36), nullable=False),
        sa.Column("ai_model_id", sa.String(36), nullable=False),
        sa.Column("limit_scope", sa.String(64), nullable=False),
        sa.Column("raw_limit", sa.Integer(), nullable=False),
        sa.Column("utilization_ratio", sa.Float(), nullable=False),
        sa.Column("effective_limit", sa.Integer(), nullable=False),
        sa.Column("window_seconds", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("quota_multiplier_json", sa.JSON(), nullable=True),
        sa.Column("source_url", sa.String(512), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ai_provider_id"], ["ai_providers.id"]),
        sa.ForeignKeyConstraint(["ai_model_id"], ["ai_models.id"]),
        sa.UniqueConstraint("ai_model_id", "limit_scope", name="uq_ai_model_limits_scope"),
    )
    op.create_table(
        "ai_agents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agent_key", sa.String(120), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("task_type", sa.String(80), nullable=False),
        sa.Column("input_schema_json", sa.JSON(), nullable=True),
        sa.Column("output_schema_json", sa.JSON(), nullable=True),
        sa.Column("default_strategy", sa.String(80), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("agent_key", name="uq_ai_agents_key"),
    )
    op.create_table(
        "ai_agent_routes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("ai_agent_id", sa.String(36), nullable=False),
        sa.Column("ai_provider_account_id", sa.String(36), nullable=False),
        sa.Column("ai_model_id", sa.String(36), nullable=False),
        sa.Column("route_role", sa.String(64), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("max_input_tokens", sa.Integer(), nullable=True),
        sa.Column("max_output_tokens", sa.Integer(), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("thinking_enabled", sa.Boolean(), nullable=False),
        sa.Column("structured_output_required", sa.Boolean(), nullable=False),
        sa.Column("fallback_on_error", sa.Boolean(), nullable=False),
        sa.Column("fallback_on_rate_limit", sa.Boolean(), nullable=False),
        sa.Column("fallback_on_invalid_output", sa.Boolean(), nullable=False),
        sa.Column("route_conditions_json", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ai_agent_id"], ["ai_agents.id"]),
        sa.ForeignKeyConstraint(["ai_provider_account_id"], ["ai_provider_accounts.id"]),
        sa.ForeignKeyConstraint(["ai_model_id"], ["ai_models.id"]),
        sa.UniqueConstraint(
            "ai_agent_id",
            "ai_model_id",
            "route_role",
            name="uq_ai_agent_routes_model_role",
        ),
    )
    op.create_table(
        "ai_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("ai_agent_id", sa.String(36), nullable=False),
        sa.Column("agent_key", sa.String(120), nullable=False),
        sa.Column("task_type", sa.String(80), nullable=False),
        sa.Column("scheduler_job_id", sa.String(36), nullable=True),
        sa.Column("source_id", sa.String(36), nullable=True),
        sa.Column("source_message_id", sa.String(36), nullable=True),
        sa.Column("artifact_id", sa.String(36), nullable=True),
        sa.Column("lead_event_id", sa.String(36), nullable=True),
        sa.Column("lead_cluster_id", sa.String(36), nullable=True),
        sa.Column("catalog_version_id", sa.String(36), nullable=True),
        sa.Column("input_hash", sa.String(64), nullable=True),
        sa.Column("settings_hash", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("strategy", sa.String(80), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ai_agent_id"], ["ai_agents.id"]),
    )
    op.create_table(
        "ai_run_outputs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("ai_run_id", sa.String(36), nullable=False),
        sa.Column("ai_agent_route_id", sa.String(36), nullable=True),
        sa.Column("ai_provider_account_id", sa.String(36), nullable=True),
        sa.Column("ai_model_id", sa.String(36), nullable=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("model_type", sa.String(64), nullable=False),
        sa.Column("route_role", sa.String(64), nullable=False),
        sa.Column("request_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("request_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_tokens", sa.Integer(), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("thinking_enabled", sa.Boolean(), nullable=False),
        sa.Column("raw_request_json", sa.JSON(), nullable=True),
        sa.Column("raw_response_json", sa.JSON(), nullable=True),
        sa.Column("parsed_output_json", sa.JSON(), nullable=True),
        sa.Column("schema_validation_json", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ai_run_id"], ["ai_runs.id"]),
        sa.ForeignKeyConstraint(["ai_agent_route_id"], ["ai_agent_routes.id"]),
        sa.ForeignKeyConstraint(["ai_provider_account_id"], ["ai_provider_accounts.id"]),
        sa.ForeignKeyConstraint(["ai_model_id"], ["ai_models.id"]),
    )
    with op.batch_alter_table("ai_model_concurrency_leases") as batch_op:
        batch_op.add_column(sa.Column("ai_model_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("ai_run_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("ai_run_output_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("raw_limit", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("utilization_ratio", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("effective_limit", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ai_model_concurrency_leases") as batch_op:
        batch_op.drop_column("effective_limit")
        batch_op.drop_column("utilization_ratio")
        batch_op.drop_column("raw_limit")
        batch_op.drop_column("ai_run_output_id")
        batch_op.drop_column("ai_run_id")
        batch_op.drop_column("ai_model_id")
    op.drop_table("ai_run_outputs")
    op.drop_table("ai_runs")
    op.drop_table("ai_agent_routes")
    op.drop_table("ai_agents")
    op.drop_table("ai_model_limits")
    op.drop_table("ai_models")
    op.drop_table("ai_provider_accounts")
    op.drop_table("ai_providers")
