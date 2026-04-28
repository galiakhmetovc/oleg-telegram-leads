"""Create lead inbox foundation tables.

Revision ID: 0004_lead_inbox_foundation
Revises: 0003_catalog_source_foundation
Create Date: 2026-04-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0004_lead_inbox_foundation"
down_revision: str | None = "0003_catalog_source_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lead_clusters",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("monitored_source_id", sa.String(36), nullable=True),
        sa.Column("chat_id", sa.String(80), nullable=True),
        sa.Column("primary_sender_id", sa.String(80), nullable=True),
        sa.Column("primary_sender_name", sa.String(255), nullable=True),
        sa.Column("primary_lead_event_id", sa.String(36), nullable=True),
        sa.Column("primary_source_message_id", sa.String(36), nullable=True),
        sa.Column("category_id", sa.String(36), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("cluster_status", sa.String(32), nullable=False),
        sa.Column("review_status", sa.String(32), nullable=False),
        sa.Column("work_outcome", sa.String(64), nullable=False),
        sa.Column("first_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lead_event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence_max", sa.Float(), nullable=True),
        sa.Column("commercial_value_score_max", sa.Float(), nullable=True),
        sa.Column("negative_score_min", sa.Float(), nullable=True),
        sa.Column("dedupe_key", sa.String(255), nullable=True),
        sa.Column("merge_strategy", sa.String(32), nullable=False),
        sa.Column("merge_reason", sa.Text(), nullable=True),
        sa.Column("last_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notify_update_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duplicate_of_cluster_id", sa.String(36), nullable=True),
        sa.Column("primary_task_id", sa.String(36), nullable=True),
        sa.Column("converted_entity_type", sa.String(64), nullable=True),
        sa.Column("converted_entity_id", sa.String(36), nullable=True),
        sa.Column("crm_candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("crm_conversion_action_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["monitored_source_id"], ["monitored_sources.id"]),
        sa.ForeignKeyConstraint(["primary_source_message_id"], ["source_messages.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["catalog_categories.id"]),
        sa.CheckConstraint(
            "cluster_status IN ('new', 'in_work', 'maybe', 'snoozed', 'not_lead', "
            "'duplicate', 'converted', 'closed')",
            name="ck_lead_clusters_status",
        ),
        sa.CheckConstraint(
            "review_status IN ('unreviewed', 'confirmed', 'rejected', 'needs_more_info')",
            name="ck_lead_clusters_review_status",
        ),
        sa.CheckConstraint(
            "work_outcome IN ('none', 'contact_task_created', 'contacted', "
            "'no_response', 'opportunity_created', 'support_case_created', "
            "'client_interest_created', 'contact_reason_created', 'closed_no_action')",
            name="ck_lead_clusters_work_outcome",
        ),
        sa.CheckConstraint(
            "merge_strategy IN ('auto', 'manual', 'imported', 'none')",
            name="ck_lead_clusters_merge_strategy",
        ),
    )
    op.create_index(
        "ix_lead_clusters_queue",
        "lead_clusters",
        [
            "cluster_status",
            "review_status",
            "monitored_source_id",
            "category_id",
            "confidence_max",
            "last_message_at",
        ],
    )

    op.create_table(
        "lead_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_message_id", sa.String(36), nullable=False),
        sa.Column("monitored_source_id", sa.String(36), nullable=False),
        sa.Column("raw_source_id", sa.String(36), nullable=True),
        sa.Column("chat_id", sa.String(80), nullable=True),
        sa.Column("telegram_message_id", sa.Integer(), nullable=False),
        sa.Column("message_url", sa.String(1024), nullable=True),
        sa.Column("sender_id", sa.String(80), nullable=True),
        sa.Column("sender_name", sa.String(255), nullable=True),
        sa.Column("message_text", sa.Text(), nullable=True),
        sa.Column("lead_cluster_id", sa.String(36), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("classifier_version_id", sa.String(36), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("detection_mode", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("commercial_value_score", sa.Float(), nullable=True),
        sa.Column("negative_score", sa.Float(), nullable=True),
        sa.Column("high_value_signals_json", sa.JSON(), nullable=True),
        sa.Column("negative_signals_json", sa.JSON(), nullable=True),
        sa.Column("notify_reason", sa.String(255), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("event_status", sa.String(32), nullable=False),
        sa.Column("event_review_status", sa.String(32), nullable=False),
        sa.Column("duplicate_of_lead_event_id", sa.String(36), nullable=True),
        sa.Column("is_retro", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("original_detected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_message_id"], ["source_messages.id"]),
        sa.ForeignKeyConstraint(["monitored_source_id"], ["monitored_sources.id"]),
        sa.ForeignKeyConstraint(["raw_source_id"], ["sources.id"]),
        sa.ForeignKeyConstraint(["lead_cluster_id"], ["lead_clusters.id"]),
        sa.ForeignKeyConstraint(["classifier_version_id"], ["classifier_versions.id"]),
        sa.CheckConstraint(
            "decision IN ('lead', 'not_lead', 'maybe')", name="ck_lead_events_decision"
        ),
        sa.CheckConstraint(
            "detection_mode IN ('live', 'reclassification', 'retro_research', 'manual')",
            name="ck_lead_events_detection_mode",
        ),
        sa.CheckConstraint(
            "event_status IN ('active', 'context_only', 'duplicate', 'superseded', 'ignored')",
            name="ck_lead_events_status",
        ),
        sa.CheckConstraint(
            "event_review_status IN ('unreviewed', 'confirmed', 'rejected', 'needs_more_info')",
            name="ck_lead_events_review_status",
        ),
    )
    op.create_index(
        "uq_lead_events_detection_identity",
        "lead_events",
        ["source_message_id", "classifier_version_id", "detection_mode"],
        unique=True,
    )
    op.create_index(
        "ix_lead_events_cluster", "lead_events", ["lead_cluster_id", "decision", "event_status"]
    )

    op.create_table(
        "lead_cluster_members",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("lead_cluster_id", sa.String(36), nullable=False),
        sa.Column("source_message_id", sa.String(36), nullable=True),
        sa.Column("lead_event_id", sa.String(36), nullable=True),
        sa.Column("member_role", sa.String(32), nullable=False),
        sa.Column("added_by", sa.String(32), nullable=False),
        sa.Column("merge_score", sa.Float(), nullable=True),
        sa.Column("merge_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["lead_cluster_id"], ["lead_clusters.id"]),
        sa.ForeignKeyConstraint(["source_message_id"], ["source_messages.id"]),
        sa.ForeignKeyConstraint(["lead_event_id"], ["lead_events.id"]),
        sa.CheckConstraint(
            "member_role IN ('primary', 'trigger', 'clarification', 'context', "
            "'negative_context', 'system')",
            name="ck_lead_cluster_members_role",
        ),
        sa.CheckConstraint(
            "added_by IN ('system', 'oleg', 'admin')", name="ck_lead_cluster_members_added_by"
        ),
    )
    op.create_index("ix_lead_cluster_members_cluster", "lead_cluster_members", ["lead_cluster_id"])

    op.create_table(
        "lead_cluster_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("from_cluster_id", sa.String(36), nullable=True),
        sa.Column("to_cluster_id", sa.String(36), nullable=True),
        sa.Column("source_message_id", sa.String(36), nullable=True),
        sa.Column("lead_event_id", sa.String(36), nullable=True),
        sa.Column("actor", sa.String(160), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["from_cluster_id"], ["lead_clusters.id"]),
        sa.ForeignKeyConstraint(["to_cluster_id"], ["lead_clusters.id"]),
        sa.CheckConstraint(
            "action_type IN ('auto_merge', 'manual_merge', 'split', 'mark_context_only', "
            "'set_primary', 'mark_duplicate', 'undo_merge')",
            name="ck_lead_cluster_actions_type",
        ),
    )

    op.create_table(
        "lead_matches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("lead_event_id", sa.String(36), nullable=False),
        sa.Column("source_message_id", sa.String(36), nullable=False),
        sa.Column("classifier_snapshot_entry_id", sa.String(36), nullable=True),
        sa.Column("catalog_item_id", sa.String(36), nullable=True),
        sa.Column("catalog_term_id", sa.String(36), nullable=True),
        sa.Column("catalog_offer_id", sa.String(36), nullable=True),
        sa.Column("category_id", sa.String(36), nullable=True),
        sa.Column("match_type", sa.String(64), nullable=False),
        sa.Column("matched_text", sa.Text(), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("item_status_at_detection", sa.String(32), nullable=True),
        sa.Column("term_status_at_detection", sa.String(32), nullable=True),
        sa.Column("offer_status_at_detection", sa.String(32), nullable=True),
        sa.Column("matched_weight", sa.Float(), nullable=True),
        sa.Column("matched_status_snapshot", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["lead_event_id"], ["lead_events.id"]),
        sa.ForeignKeyConstraint(["source_message_id"], ["source_messages.id"]),
        sa.ForeignKeyConstraint(
            ["classifier_snapshot_entry_id"], ["classifier_snapshot_entries.id"]
        ),
        sa.CheckConstraint(
            "match_type IN ('term', 'semantic', 'category', 'manual_example', 'llm_reason')",
            name="ck_lead_matches_type",
        ),
    )

    op.create_table(
        "feedback_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("reason_code", sa.String(80), nullable=True),
        sa.Column("feedback_scope", sa.String(64), nullable=False),
        sa.Column("learning_effect", sa.String(80), nullable=False),
        sa.Column("application_status", sa.String(32), nullable=False),
        sa.Column("applied_entity_type", sa.String(64), nullable=True),
        sa.Column("applied_entity_id", sa.String(36), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.CheckConstraint(
            "target_type IN ('lead_cluster', 'lead_event', 'lead_match', "
            "'source_message', 'sender_profile', 'catalog_item', 'catalog_term', "
            "'category', 'source', 'manual_input', 'client', 'contact', "
            "'client_object', 'client_interest', 'client_asset', 'opportunity', "
            "'support_case', 'contact_reason', 'task')",
            name="ck_feedback_events_target_type",
        ),
        sa.CheckConstraint(
            "application_status IN ('recorded', 'queued', 'applied', 'needs_review', 'ignored')",
            name="ck_feedback_events_application_status",
        ),
    )
    op.create_index("ix_feedback_events_target", "feedback_events", ["target_type", "target_id"])

    op.create_table(
        "crm_conversion_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("lead_cluster_id", sa.String(36), nullable=False),
        sa.Column("lead_event_id", sa.String(36), nullable=True),
        sa.Column("candidate_type", sa.String(64), nullable=False),
        sa.Column("extracted_json", sa.JSON(), nullable=False),
        sa.Column("display_summary", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_by", sa.String(32), nullable=False),
        sa.Column("created_entity_type", sa.String(64), nullable=True),
        sa.Column("created_entity_id", sa.String(36), nullable=True),
        sa.Column("reviewed_by", sa.String(160), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["lead_cluster_id"], ["lead_clusters.id"]),
        sa.ForeignKeyConstraint(["lead_event_id"], ["lead_events.id"]),
        sa.CheckConstraint(
            "status IN ('proposed', 'accepted', 'rejected', 'edited', 'converted', 'superseded')",
            name="ck_crm_conversion_candidates_status",
        ),
    )

    op.create_table(
        "crm_conversion_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("lead_cluster_id", sa.String(36), nullable=False),
        sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("used_candidate_ids_json", sa.JSON(), nullable=True),
        sa.Column("created_entity_type", sa.String(64), nullable=True),
        sa.Column("created_entity_id", sa.String(36), nullable=True),
        sa.Column("linked_client_id", sa.String(36), nullable=True),
        sa.Column("linked_contact_id", sa.String(36), nullable=True),
        sa.Column("manual_changes_json", sa.JSON(), nullable=True),
        sa.Column("next_step", sa.String(255), nullable=True),
        sa.Column("next_step_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["lead_cluster_id"], ["lead_clusters.id"]),
    )


def downgrade() -> None:
    op.drop_table("crm_conversion_actions")
    op.drop_table("crm_conversion_candidates")
    op.drop_index("ix_feedback_events_target", table_name="feedback_events")
    op.drop_table("feedback_events")
    op.drop_table("lead_matches")
    op.drop_table("lead_cluster_actions")
    op.drop_index("ix_lead_cluster_members_cluster", table_name="lead_cluster_members")
    op.drop_table("lead_cluster_members")
    op.drop_index("ix_lead_events_cluster", table_name="lead_events")
    op.drop_index("uq_lead_events_detection_identity", table_name="lead_events")
    op.drop_table("lead_events")
    op.drop_index("ix_lead_clusters_queue", table_name="lead_clusters")
    op.drop_table("lead_clusters")
