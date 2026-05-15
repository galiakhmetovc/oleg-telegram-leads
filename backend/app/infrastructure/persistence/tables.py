from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = sa.MetaData()

enrichment_jobs = sa.Table(
    "enrichment_jobs",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("input_text", sa.Text(), nullable=False),
    sa.Column("status", sa.Text(), nullable=False),
    sa.Column("progress_percent", sa.Integer(), nullable=False),
    sa.Column("current_stage", sa.Text(), nullable=True),
    sa.Column("stage_index", sa.Integer(), nullable=False),
    sa.Column("stage_count", sa.Integer(), nullable=False),
    sa.Column("stage_progress_percent", sa.Integer(), nullable=False),
    sa.Column("message", sa.Text(), nullable=False),
    sa.Column("error", JSONB(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column(
        "nlp_config_revision_id",
        UUID(as_uuid=True),
        sa.ForeignKey("nlp_config_revisions.id", ondelete="SET NULL"),
        nullable=True,
    ),
    sa.Column("nlp_config_revision", sa.Integer(), nullable=True),
)

enrichment_results = sa.Table(
    "enrichment_results",
    metadata,
    sa.Column("job_id", UUID(as_uuid=True), primary_key=True),
    sa.Column("result", JSONB(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

enrichment_events = sa.Table(
    "enrichment_events",
    metadata,
    sa.Column("sequence", sa.BigInteger(), primary_key=True),
    sa.Column("job_id", UUID(as_uuid=True), nullable=False),
    sa.Column("event_type", sa.Text(), nullable=False),
    sa.Column("progress_percent", sa.Integer(), nullable=False),
    sa.Column("current_stage", sa.Text(), nullable=True),
    sa.Column("stage_index", sa.Integer(), nullable=False),
    sa.Column("stage_count", sa.Integer(), nullable=False),
    sa.Column("stage_progress_percent", sa.Integer(), nullable=False),
    sa.Column("message", sa.Text(), nullable=False),
    sa.Column("payload", JSONB(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

enrichment_task_outbox = sa.Table(
    "enrichment_task_outbox",
    metadata,
    sa.Column(
        "job_id",
        UUID(as_uuid=True),
        sa.ForeignKey("enrichment_jobs.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column("task_name", sa.Text(), nullable=False),
    sa.Column("status", sa.Text(), nullable=False),
    sa.Column("attempts", sa.Integer(), nullable=False),
    sa.Column("last_error", sa.Text(), nullable=True),
    sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
)

nlp_config_revisions = sa.Table(
    "nlp_config_revisions",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("revision", sa.Integer(), nullable=False),
    sa.Column("config", JSONB(), nullable=False),
    sa.Column("is_active", sa.Boolean(), nullable=False),
    sa.Column("source", sa.Text(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

notification_settings = sa.Table(
    "notification_settings",
    metadata,
    sa.Column("channel", sa.Text(), primary_key=True),
    sa.Column("config", JSONB(), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

telegram_userbot_accounts = sa.Table(
    "telegram_userbot_accounts",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("name", sa.Text(), nullable=False),
    sa.Column("phone", sa.Text(), nullable=False),
    sa.Column("api_id", sa.Integer(), nullable=False),
    sa.Column("api_hash", sa.Text(), nullable=True),
    sa.Column("session_string", sa.Text(), nullable=True),
    sa.Column("phone_code_hash", sa.Text(), nullable=True),
    sa.Column("enabled", sa.Boolean(), nullable=False),
    sa.Column("status", sa.Text(), nullable=False),
    sa.Column("last_error", sa.Text(), nullable=True),
    sa.Column("telegram_user_id", sa.Text(), nullable=True),
    sa.Column("telegram_username", sa.Text(), nullable=True),
    sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

telegram_source_chats = sa.Table(
    "telegram_source_chats",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("account_id", UUID(as_uuid=True), nullable=False),
    sa.Column("title", sa.Text(), nullable=False),
    sa.Column("input_ref", sa.Text(), nullable=False),
    sa.Column("telegram_chat_id", sa.Text(), nullable=True),
    sa.Column("enabled", sa.Boolean(), nullable=False),
    sa.Column("status", sa.Text(), nullable=False),
    sa.Column("last_message_id", sa.BigInteger(), nullable=True),
    sa.Column("last_error", sa.Text(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

telegram_source_messages = sa.Table(
    "telegram_source_messages",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("account_id", UUID(as_uuid=True), nullable=False),
    sa.Column("source_chat_id", UUID(as_uuid=True), nullable=False),
    sa.Column("telegram_message_id", sa.BigInteger(), nullable=False),
    sa.Column("message_date", sa.DateTime(timezone=True), nullable=True),
    sa.Column("sender_id", sa.Text(), nullable=True),
    sa.Column("sender_username", sa.Text(), nullable=True),
    sa.Column("text", sa.Text(), nullable=False),
    sa.Column("raw_payload", JSONB(), nullable=False),
    sa.Column("enrichment_job_id", UUID(as_uuid=True), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("source_chat_id", "telegram_message_id", name="uq_telegram_source_message"),
)

message_reviews = sa.Table(
    "message_reviews",
    metadata,
    sa.Column(
        "source_message_id",
        UUID(as_uuid=True),
        sa.ForeignKey("telegram_source_messages.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column("verdict", sa.Text(), nullable=True),
    sa.Column("comment", sa.Text(), nullable=False),
    sa.Column("tags", JSONB(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

golden_examples = sa.Table(
    "golden_examples",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("title", sa.Text(), nullable=False),
    sa.Column("text", sa.Text(), nullable=False),
    sa.Column("expected_verdict", sa.Text(), nullable=True),
    sa.Column("comment", sa.Text(), nullable=False),
    sa.Column(
        "source_message_id",
        UUID(as_uuid=True),
        sa.ForeignKey("telegram_source_messages.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    ),
    sa.Column("source_chat_title", sa.Text(), nullable=True),
    sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
    sa.Column("telegram_message_url", sa.Text(), nullable=True),
    sa.Column(
        "last_enrichment_job_id",
        UUID(as_uuid=True),
        sa.ForeignKey("enrichment_jobs.id", ondelete="SET NULL"),
        nullable=True,
    ),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

notification_outbox = sa.Table(
    "notification_outbox",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("route_id", sa.Text(), nullable=False),
    sa.Column("bot_id", sa.Text(), nullable=False),
    sa.Column("chat_id", sa.Text(), nullable=False),
    sa.Column("source_message_id", UUID(as_uuid=True), nullable=True),
    sa.Column("enrichment_job_id", UUID(as_uuid=True), nullable=True),
    sa.Column("text", sa.Text(), nullable=False),
    sa.Column("status", sa.Text(), nullable=False),
    sa.Column("attempts", sa.Integer(), nullable=False),
    sa.Column("last_error", sa.Text(), nullable=True),
    sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
)

lead_handlings = sa.Table(
    "lead_handlings",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column(
        "source_message_id",
        UUID(as_uuid=True),
        sa.ForeignKey("telegram_source_messages.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column(
        "notification_outbox_id",
        UUID(as_uuid=True),
        sa.ForeignKey("notification_outbox.id", ondelete="SET NULL"),
        nullable=True,
    ),
    sa.Column("sales_chat_id", sa.Text(), nullable=True),
    sa.Column("sales_chat_message_id", sa.BigInteger(), nullable=True),
    sa.Column("status", sa.Text(), nullable=False),
    sa.Column("owner_telegram_user_id", sa.Text(), nullable=True),
    sa.Column("owner_telegram_username", sa.Text(), nullable=True),
    sa.Column("owner_display_name", sa.Text(), nullable=True),
    sa.Column("last_comment", sa.Text(), nullable=True),
    sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("source_message_id", name="uq_lead_handlings_source_message"),
    sa.CheckConstraint(
        "status IN ('new', 'claimed', 'contacted', 'waiting', 'closed', 'not_lead')",
        name="ck_lead_handlings_status",
    ),
)

lead_handling_events = sa.Table(
    "lead_handling_events",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column(
        "lead_handling_id",
        UUID(as_uuid=True),
        sa.ForeignKey("lead_handlings.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column(
        "source_message_id",
        UUID(as_uuid=True),
        sa.ForeignKey("telegram_source_messages.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("actor_telegram_user_id", sa.Text(), nullable=True),
    sa.Column("actor_telegram_username", sa.Text(), nullable=True),
    sa.Column("actor_display_name", sa.Text(), nullable=True),
    sa.Column("event_type", sa.Text(), nullable=False),
    sa.Column("payload", JSONB(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

lead_bot_sessions = sa.Table(
    "lead_bot_sessions",
    metadata,
    sa.Column("bot_id", sa.Text(), nullable=False),
    sa.Column("telegram_user_id", sa.Text(), nullable=False),
    sa.Column("state", sa.Text(), nullable=False),
    sa.Column("payload", JSONB(), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint("bot_id", "telegram_user_id", name="pk_lead_bot_sessions"),
)

analytics_runs = sa.Table(
    "analytics_runs",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("name", sa.Text(), nullable=False),
    sa.Column("source", sa.Text(), nullable=False),
    sa.Column("input_path", sa.Text(), nullable=False),
    sa.Column("run_dir", sa.Text(), nullable=False),
    sa.Column("processed", sa.Integer(), nullable=False),
    sa.Column("skipped", sa.Integer(), nullable=False),
    sa.Column("failed", sa.Integer(), nullable=False),
    sa.Column("leads", sa.Integer(), nullable=False),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("summary", JSONB(), nullable=False),
)

analytics_candidates = sa.Table(
    "analytics_candidates",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("run_id", UUID(as_uuid=True), nullable=False),
    sa.Column("message_id", sa.Text(), nullable=False),
    sa.Column("text", sa.Text(), nullable=False),
    sa.Column("score", sa.Integer(), nullable=False),
    sa.Column("temperature", sa.Text(), nullable=False),
    sa.Column("review_lane", sa.Text(), nullable=False),
    sa.Column("solution_areas", JSONB(), nullable=False),
    sa.Column("customer_segments", JSONB(), nullable=False),
    sa.Column("intent_signals", JSONB(), nullable=False),
    sa.Column("noise_signals", JSONB(), nullable=False),
    sa.Column("reasons", JSONB(), nullable=False),
    sa.Column("domain_signals", JSONB(), nullable=False),
    sa.Column("facts", JSONB(), nullable=False),
    sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("source_chat_id", sa.Text(), nullable=True),
    sa.Column("source_chat_title", sa.Text(), nullable=True),
    sa.Column("signal_types", sa.ARRAY(sa.Text()), nullable=False),
    sa.Column("fact_types", sa.ARRAY(sa.Text()), nullable=False),
    sa.Column("reason_keys", sa.ARRAY(sa.Text()), nullable=False),
    sa.Column("solution_area_types", sa.ARRAY(sa.Text()), nullable=False),
    sa.Column("customer_segment_types", sa.ARRAY(sa.Text()), nullable=False),
)

analytics_aggregates = sa.Table(
    "analytics_aggregates",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("run_id", UUID(as_uuid=True), nullable=False),
    sa.Column("kind", sa.Text(), nullable=False),
    sa.Column("key", sa.Text(), nullable=False),
    sa.Column("label", sa.Text(), nullable=False),
    sa.Column("count", sa.Integer(), nullable=False),
    sa.Column("payload", JSONB(), nullable=False),
)
