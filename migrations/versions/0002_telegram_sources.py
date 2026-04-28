"""Create Telegram source ingestion tables.

Revision ID: 0002_telegram_sources
Revises: 0001_foundation
Create Date: 2026-04-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0002_telegram_sources"
down_revision: str | None = "0001_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "userbot_accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("telegram_user_id", sa.String(64), nullable=True),
        sa.Column("telegram_username", sa.String(160), nullable=True),
        sa.Column("session_name", sa.String(160), nullable=False),
        sa.Column("session_path", sa.String(512), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("priority", sa.String(32), nullable=False, server_default="normal"),
        sa.Column("max_parallel_telegram_jobs", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "flood_sleep_threshold_seconds", sa.Integer(), nullable=False, server_default="60"
        ),
        sa.Column("last_connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'needs_login', 'banned', 'disabled')",
            name="ck_userbot_accounts_status",
        ),
    )

    op.create_table(
        "monitored_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_kind", sa.String(64), nullable=False),
        sa.Column("telegram_id", sa.String(80), nullable=True),
        sa.Column("username", sa.String(160), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("invite_link_hash", sa.String(128), nullable=True),
        sa.Column("input_ref", sa.String(512), nullable=False),
        sa.Column("source_purpose", sa.String(32), nullable=False),
        sa.Column("assigned_userbot_account_id", sa.String(36), nullable=True),
        sa.Column("priority", sa.String(32), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("lead_detection_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "catalog_ingestion_enabled", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("phase_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("start_mode", sa.String(32), nullable=False),
        sa.Column("start_message_id", sa.Integer(), nullable=True),
        sa.Column("start_recent_limit", sa.Integer(), nullable=True),
        sa.Column("start_recent_days", sa.Integer(), nullable=True),
        sa.Column("historical_backfill_policy", sa.String(32), nullable=False),
        sa.Column("checkpoint_message_id", sa.Integer(), nullable=True),
        sa.Column("checkpoint_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_preview_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("preview_message_count", sa.Integer(), nullable=True),
        sa.Column("next_poll_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("poll_interval_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("added_by", sa.String(160), nullable=False),
        sa.Column("activated_by", sa.String(160), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assigned_userbot_account_id"], ["userbot_accounts.id"]),
        sa.CheckConstraint(
            "source_kind IN ('telegram_group', 'telegram_supergroup', "
            "'telegram_private_group', 'telegram_channel', 'telegram_comments', "
            "'telegram_dm')",
            name="ck_monitored_sources_kind",
        ),
        sa.CheckConstraint(
            "source_purpose IN ('lead_monitoring', 'catalog_ingestion', 'both')",
            name="ck_monitored_sources_purpose",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'checking_access', 'preview_ready', 'active', "
            "'paused', 'needs_join', 'needs_captcha', 'private_or_no_access', "
            "'flood_wait', 'banned', 'read_error', 'disabled')",
            name="ck_monitored_sources_status",
        ),
        sa.CheckConstraint(
            "start_mode IN ('from_now', 'from_message', 'recent_limit', 'recent_days')",
            name="ck_monitored_sources_start_mode",
        ),
    )

    op.create_table(
        "source_access_checks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("monitored_source_id", sa.String(36), nullable=False),
        sa.Column("userbot_account_id", sa.String(36), nullable=True),
        sa.Column("check_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("resolved_source_kind", sa.String(64), nullable=True),
        sa.Column("resolved_telegram_id", sa.String(80), nullable=True),
        sa.Column("resolved_title", sa.String(255), nullable=True),
        sa.Column("last_message_id", sa.Integer(), nullable=True),
        sa.Column("can_read_messages", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_read_history", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("flood_wait_seconds", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["monitored_source_id"], ["monitored_sources.id"]),
        sa.ForeignKeyConstraint(["userbot_account_id"], ["userbot_accounts.id"]),
    )

    op.create_table(
        "source_preview_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("monitored_source_id", sa.String(36), nullable=False),
        sa.Column("access_check_id", sa.String(36), nullable=True),
        sa.Column("telegram_message_id", sa.Integer(), nullable=False),
        sa.Column("message_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sender_display", sa.String(255), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("has_media", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("media_metadata_json", sa.JSON(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["monitored_source_id"], ["monitored_sources.id"]),
        sa.ForeignKeyConstraint(["access_check_id"], ["source_access_checks.id"]),
    )

    op.create_table(
        "source_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("monitored_source_id", sa.String(36), nullable=False),
        sa.Column("raw_source_id", sa.String(36), nullable=True),
        sa.Column("telegram_message_id", sa.Integer(), nullable=False),
        sa.Column("sender_id", sa.String(80), nullable=True),
        sa.Column("message_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("normalized_text", sa.Text(), nullable=True),
        sa.Column("has_media", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("media_metadata_json", sa.JSON(), nullable=True),
        sa.Column("reply_to_message_id", sa.Integer(), nullable=True),
        sa.Column("thread_id", sa.String(80), nullable=True),
        sa.Column("forward_metadata_json", sa.JSON(), nullable=True),
        sa.Column("raw_metadata_json", sa.JSON(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("classification_status", sa.String(32), nullable=False),
        sa.Column("archive_pointer_id", sa.String(36), nullable=True),
        sa.Column("is_archived_stub", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("text_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("caption_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("metadata_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["monitored_source_id"], ["monitored_sources.id"]),
        sa.UniqueConstraint(
            "monitored_source_id",
            "telegram_message_id",
            name="uq_source_messages_monitored_telegram_message",
        ),
    )
    op.create_index("ix_source_messages_sender_id", "source_messages", ["sender_id"])

    op.create_table(
        "sender_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("telegram_user_id", sa.String(80), nullable=True),
        sa.Column("telegram_username", sa.String(160), nullable=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("first_seen_source_message_id", sa.String(36), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sender_role", sa.String(64), nullable=False),
        sa.Column("role_confidence", sa.Float(), nullable=True),
        sa.Column("role_source", sa.String(64), nullable=True),
        sa.Column("crm_contact_id", sa.String(36), nullable=True),
        sa.Column("crm_client_id", sa.String(36), nullable=True),
        sa.Column("feedback_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["first_seen_source_message_id"], ["source_messages.id"]),
    )

    op.create_table(
        "message_context_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_message_id", sa.String(36), nullable=False),
        sa.Column("related_source_message_id", sa.String(36), nullable=False),
        sa.Column("relation_type", sa.String(64), nullable=False),
        sa.Column("distance", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_message_id"], ["source_messages.id"]),
        sa.ForeignKeyConstraint(["related_source_message_id"], ["source_messages.id"]),
        sa.UniqueConstraint(
            "source_message_id",
            "related_source_message_id",
            "relation_type",
            name="uq_message_context_links_relation",
        ),
    )


def downgrade() -> None:
    op.drop_table("message_context_links")
    op.drop_table("sender_profiles")
    op.drop_index("ix_source_messages_sender_id", table_name="source_messages")
    op.drop_table("source_messages")
    op.drop_table("source_preview_messages")
    op.drop_table("source_access_checks")
    op.drop_table("monitored_sources")
    op.drop_table("userbot_accounts")
