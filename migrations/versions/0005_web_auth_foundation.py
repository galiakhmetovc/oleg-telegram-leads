"""Create web auth and task foundation tables.

Revision ID: 0005_web_auth_foundation
Revises: 0004_lead_inbox_foundation
Create Date: 2026-04-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0005_web_auth_foundation"
down_revision: str | None = "0004_lead_inbox_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "web_users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("telegram_user_id", sa.String(80), nullable=True),
        sa.Column("telegram_username", sa.String(160), nullable=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("auth_type", sa.String(32), nullable=False),
        sa.Column("local_username", sa.String(160), nullable=True),
        sa.Column("password_hash", sa.String(512), nullable=True),
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("auth_type IN ('local', 'telegram')", name="ck_web_users_auth_type"),
        sa.CheckConstraint("role IN ('admin')", name="ck_web_users_role"),
        sa.CheckConstraint(
            "status IN ('active', 'disabled', 'pending')", name="ck_web_users_status"
        ),
    )
    op.create_index(
        "uq_web_users_local_username",
        "web_users",
        ["local_username"],
        unique=True,
    )
    op.create_index(
        "uq_web_users_telegram_user_id",
        "web_users",
        ["telegram_user_id"],
        unique=True,
    )

    op.create_table(
        "web_auth_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("auth_method", sa.String(32), nullable=False),
        sa.Column("session_token_hash", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["web_users.id"]),
        sa.CheckConstraint(
            "auth_method IN ('local', 'telegram')", name="ck_web_auth_sessions_auth_method"
        ),
    )
    op.create_index(
        "uq_web_auth_sessions_token_hash",
        "web_auth_sessions",
        ["session_token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_web_auth_sessions_user_active",
        "web_auth_sessions",
        ["user_id", "revoked_at", "expires_at"],
    )

    op.create_table(
        "tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("client_id", sa.String(36), nullable=True),
        sa.Column("lead_cluster_id", sa.String(36), nullable=True),
        sa.Column("lead_event_id", sa.String(36), nullable=True),
        sa.Column("opportunity_id", sa.String(36), nullable=True),
        sa.Column("support_case_id", sa.String(36), nullable=True),
        sa.Column("contact_reason_id", sa.String(36), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("priority", sa.String(32), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner_user_id", sa.String(36), nullable=True),
        sa.Column("assignee_user_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["lead_cluster_id"], ["lead_clusters.id"]),
        sa.ForeignKeyConstraint(["lead_event_id"], ["lead_events.id"]),
        sa.ForeignKeyConstraint(["owner_user_id"], ["web_users.id"]),
        sa.ForeignKeyConstraint(["assignee_user_id"], ["web_users.id"]),
        sa.CheckConstraint(
            "status IN ('open', 'done', 'cancelled', 'snoozed')", name="ck_tasks_status"
        ),
        sa.CheckConstraint("priority IN ('low', 'normal', 'high')", name="ck_tasks_priority"),
    )
    op.create_index(
        "ix_tasks_lead_cluster_status_due",
        "tasks",
        ["lead_cluster_id", "status", "due_at"],
    )
    op.create_index(
        "ix_tasks_assignee_status_due", "tasks", ["assignee_user_id", "status", "due_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_tasks_assignee_status_due", table_name="tasks")
    op.drop_index("ix_tasks_lead_cluster_status_due", table_name="tasks")
    op.drop_table("tasks")
    op.drop_index("ix_web_auth_sessions_user_active", table_name="web_auth_sessions")
    op.drop_index("uq_web_auth_sessions_token_hash", table_name="web_auth_sessions")
    op.drop_table("web_auth_sessions")
    op.drop_index("uq_web_users_telegram_user_id", table_name="web_users")
    op.drop_index("uq_web_users_local_username", table_name="web_users")
    op.drop_table("web_users")
