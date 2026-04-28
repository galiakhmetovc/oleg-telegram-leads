"""Create CRM memory tables.

Revision ID: 0006_crm_memory
Revises: 0005_web_auth_foundation
Create Date: 2026-04-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0006_crm_memory"
down_revision: str | None = "0005_web_auth_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("client_type", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=True),
        sa.Column("owner_user_id", sa.String(36), nullable=True),
        sa.Column("assignee_user_id", sa.String(36), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["web_users.id"]),
        sa.ForeignKeyConstraint(["assignee_user_id"], ["web_users.id"]),
        sa.CheckConstraint(
            "client_type IN ('person', 'family', 'company', 'cottage_settlement', "
            "'hoa_tsn', 'residential_complex', 'unknown')",
            name="ck_clients_type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'archived', 'do_not_contact')",
            name="ck_clients_status",
        ),
        sa.CheckConstraint(
            "source_type IN ('manual', 'lead', 'import')",
            name="ck_clients_source_type",
        ),
    )
    op.create_index("ix_clients_status_updated", "clients", ["status", "updated_at"])

    op.create_table(
        "contacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("client_id", sa.String(36), nullable=False),
        sa.Column("contact_name", sa.String(255), nullable=True),
        sa.Column("telegram_user_id", sa.String(80), nullable=True),
        sa.Column("telegram_username", sa.String(160), nullable=True),
        sa.Column("phone", sa.String(80), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("whatsapp", sa.String(80), nullable=True),
        sa.Column("preferred_channel", sa.String(32), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.CheckConstraint(
            "preferred_channel IN ('telegram', 'phone', 'whatsapp', 'email', 'unknown')",
            name="ck_contacts_preferred_channel",
        ),
        sa.CheckConstraint(
            "source_type IN ('manual', 'lead', 'import')",
            name="ck_contacts_source_type",
        ),
    )
    op.create_index("ix_contacts_client", "contacts", ["client_id", "is_primary"])
    op.create_index("ix_contacts_telegram_user_id", "contacts", ["telegram_user_id"])
    op.create_index("ix_contacts_telegram_username", "contacts", ["telegram_username"])
    op.create_index("ix_contacts_phone", "contacts", ["phone"])
    op.create_index("ix_contacts_email", "contacts", ["email"])

    op.create_table(
        "client_objects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("client_id", sa.String(36), nullable=False),
        sa.Column("object_type", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("location_text", sa.Text(), nullable=True),
        sa.Column("project_stage", sa.String(32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.CheckConstraint(
            "object_type IN ('apartment', 'house', 'dacha', 'cottage_settlement', "
            "'office', 'retail', 'warehouse', 'production', 'unknown')",
            name="ck_client_objects_type",
        ),
        sa.CheckConstraint(
            "project_stage IN ('design', 'construction', 'renovation', 'operation', 'unknown')",
            name="ck_client_objects_project_stage",
        ),
    )
    op.create_index("ix_client_objects_client", "client_objects", ["client_id", "object_type"])

    op.create_table(
        "client_interests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("client_id", sa.String(36), nullable=False),
        sa.Column("client_object_id", sa.String(36), nullable=True),
        sa.Column("category_id", sa.String(36), nullable=True),
        sa.Column("catalog_item_id", sa.String(36), nullable=True),
        sa.Column("catalog_term_id", sa.String(36), nullable=True),
        sa.Column("interest_text", sa.Text(), nullable=False),
        sa.Column("interest_status", sa.String(32), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.ForeignKeyConstraint(["client_object_id"], ["client_objects.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["catalog_categories.id"]),
        sa.ForeignKeyConstraint(["catalog_item_id"], ["catalog_items.id"]),
        sa.ForeignKeyConstraint(["catalog_term_id"], ["catalog_terms.id"]),
        sa.CheckConstraint(
            "interest_status IN ('interested', 'postponed', 'not_found', 'too_expensive', "
            "'bought_elsewhere', 'already_has', 'unknown', 'closed')",
            name="ck_client_interests_status",
        ),
        sa.CheckConstraint(
            "source_type IN ('lead', 'manual', 'support', 'import')",
            name="ck_client_interests_source_type",
        ),
    )
    op.create_index("ix_client_interests_client", "client_interests", ["client_id"])
    op.create_index(
        "ix_client_interests_reactivation",
        "client_interests",
        ["interest_status", "category_id", "catalog_item_id", "catalog_term_id", "next_check_at"],
    )

    op.create_table(
        "client_assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("client_id", sa.String(36), nullable=False),
        sa.Column("client_object_id", sa.String(36), nullable=True),
        sa.Column("category_id", sa.String(36), nullable=True),
        sa.Column("catalog_item_id", sa.String(36), nullable=True),
        sa.Column("asset_name", sa.String(255), nullable=False),
        sa.Column("asset_status", sa.String(32), nullable=False),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("warranty_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("service_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.ForeignKeyConstraint(["client_object_id"], ["client_objects.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["catalog_categories.id"]),
        sa.ForeignKeyConstraint(["catalog_item_id"], ["catalog_items.id"]),
        sa.CheckConstraint(
            "asset_status IN ('planned', 'installed', 'active', 'needs_service', "
            "'retired', 'unknown')",
            name="ck_client_assets_status",
        ),
        sa.CheckConstraint(
            "source_type IN ('manual', 'lead', 'support', 'import')",
            name="ck_client_assets_source_type",
        ),
    )
    op.create_index("ix_client_assets_client", "client_assets", ["client_id", "asset_status"])
    op.create_index("ix_client_assets_service_due", "client_assets", ["asset_status", "service_due_at"])

    op.create_table(
        "opportunities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("client_id", sa.String(36), nullable=False),
        sa.Column("client_object_id", sa.String(36), nullable=True),
        sa.Column("source_lead_cluster_id", sa.String(36), nullable=True),
        sa.Column("source_lead_event_id", sa.String(36), nullable=True),
        sa.Column("primary_category_id", sa.String(36), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("lost_reason", sa.String(64), nullable=True),
        sa.Column("estimated_value", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(16), nullable=True),
        sa.Column("owner_user_id", sa.String(36), nullable=True),
        sa.Column("assignee_user_id", sa.String(36), nullable=True),
        sa.Column("next_step", sa.String(255), nullable=True),
        sa.Column("next_step_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.ForeignKeyConstraint(["client_object_id"], ["client_objects.id"]),
        sa.ForeignKeyConstraint(["source_lead_cluster_id"], ["lead_clusters.id"]),
        sa.ForeignKeyConstraint(["source_lead_event_id"], ["lead_events.id"]),
        sa.ForeignKeyConstraint(["primary_category_id"], ["catalog_categories.id"]),
        sa.ForeignKeyConstraint(["owner_user_id"], ["web_users.id"]),
        sa.ForeignKeyConstraint(["assignee_user_id"], ["web_users.id"]),
        sa.CheckConstraint(
            "status IN ('new', 'qualified', 'contacted', 'proposal', 'won', 'lost', "
            "'not_lead', 'snoozed')",
            name="ck_opportunities_status",
        ),
        sa.CheckConstraint(
            "lost_reason IS NULL OR lost_reason IN ('no_intent', 'not_our_topic', "
            "'too_far', 'too_small', 'too_expensive', 'competitor', 'no_response', "
            "'duplicate', 'other')",
            name="ck_opportunities_lost_reason",
        ),
    )
    op.create_index("ix_opportunities_client", "opportunities", ["client_id", "status"])
    op.create_index("ix_opportunities_queue", "opportunities", ["status", "next_step_at"])

    op.create_table(
        "support_cases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("client_id", sa.String(36), nullable=False),
        sa.Column("client_object_id", sa.String(36), nullable=True),
        sa.Column("client_asset_id", sa.String(36), nullable=True),
        sa.Column("source_lead_cluster_id", sa.String(36), nullable=True),
        sa.Column("source_lead_event_id", sa.String(36), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("priority", sa.String(32), nullable=False),
        sa.Column("issue_text", sa.Text(), nullable=True),
        sa.Column("resolution_text", sa.Text(), nullable=True),
        sa.Column("owner_user_id", sa.String(36), nullable=True),
        sa.Column("assignee_user_id", sa.String(36), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.ForeignKeyConstraint(["client_object_id"], ["client_objects.id"]),
        sa.ForeignKeyConstraint(["client_asset_id"], ["client_assets.id"]),
        sa.ForeignKeyConstraint(["source_lead_cluster_id"], ["lead_clusters.id"]),
        sa.ForeignKeyConstraint(["source_lead_event_id"], ["lead_events.id"]),
        sa.ForeignKeyConstraint(["owner_user_id"], ["web_users.id"]),
        sa.ForeignKeyConstraint(["assignee_user_id"], ["web_users.id"]),
        sa.CheckConstraint(
            "status IN ('new', 'in_progress', 'waiting_client', 'resolved', 'closed')",
            name="ck_support_cases_status",
        ),
        sa.CheckConstraint(
            "priority IN ('low', 'normal', 'high', 'urgent')",
            name="ck_support_cases_priority",
        ),
    )
    op.create_index("ix_support_cases_client", "support_cases", ["client_id", "status"])
    op.create_index("ix_support_cases_queue", "support_cases", ["status", "priority", "updated_at"])

    op.create_table(
        "contact_reasons",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("client_id", sa.String(36), nullable=False),
        sa.Column("contact_id", sa.String(36), nullable=True),
        sa.Column("client_object_id", sa.String(36), nullable=True),
        sa.Column("client_interest_id", sa.String(36), nullable=True),
        sa.Column("client_asset_id", sa.String(36), nullable=True),
        sa.Column("catalog_item_id", sa.String(36), nullable=True),
        sa.Column("catalog_offer_id", sa.String(36), nullable=True),
        sa.Column("catalog_attribute_id", sa.String(36), nullable=True),
        sa.Column("source_id", sa.String(36), nullable=True),
        sa.Column("source_lead_cluster_id", sa.String(36), nullable=True),
        sa.Column("source_lead_event_id", sa.String(36), nullable=True),
        sa.Column("reason_type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("reason_text", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"]),
        sa.ForeignKeyConstraint(["client_object_id"], ["client_objects.id"]),
        sa.ForeignKeyConstraint(["client_interest_id"], ["client_interests.id"]),
        sa.ForeignKeyConstraint(["client_asset_id"], ["client_assets.id"]),
        sa.ForeignKeyConstraint(["catalog_item_id"], ["catalog_items.id"]),
        sa.ForeignKeyConstraint(["catalog_offer_id"], ["catalog_offers.id"]),
        sa.ForeignKeyConstraint(["catalog_attribute_id"], ["catalog_attributes.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.ForeignKeyConstraint(["source_lead_cluster_id"], ["lead_clusters.id"]),
        sa.ForeignKeyConstraint(["source_lead_event_id"], ["lead_events.id"]),
        sa.CheckConstraint(
            "reason_type IN ('new_matching_product', 'new_matching_offer', "
            "'support_followup', 'maintenance_due', 'warranty_followup', "
            "'upgrade_available', 'price_change', 'seasonal', 'catalog_reactivation', "
            "'manual')",
            name="ck_contact_reasons_type",
        ),
        sa.CheckConstraint(
            "priority IN ('low', 'normal', 'high')",
            name="ck_contact_reasons_priority",
        ),
        sa.CheckConstraint(
            "status IN ('new', 'accepted', 'dismissed', 'done', 'snoozed')",
            name="ck_contact_reasons_status",
        ),
    )
    op.create_index("ix_contact_reasons_client", "contact_reasons", ["client_id", "status"])
    op.create_index("ix_contact_reasons_queue", "contact_reasons", ["status", "due_at", "priority"])

    op.create_table(
        "touchpoints",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("client_id", sa.String(36), nullable=False),
        sa.Column("contact_id", sa.String(36), nullable=True),
        sa.Column("opportunity_id", sa.String(36), nullable=True),
        sa.Column("support_case_id", sa.String(36), nullable=True),
        sa.Column("contact_reason_id", sa.String(36), nullable=True),
        sa.Column("lead_cluster_id", sa.String(36), nullable=True),
        sa.Column("lead_event_id", sa.String(36), nullable=True),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("direction", sa.String(32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("outcome", sa.String(255), nullable=True),
        sa.Column("next_step", sa.String(255), nullable=True),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"]),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"]),
        sa.ForeignKeyConstraint(["support_case_id"], ["support_cases.id"]),
        sa.ForeignKeyConstraint(["contact_reason_id"], ["contact_reasons.id"]),
        sa.ForeignKeyConstraint(["lead_cluster_id"], ["lead_clusters.id"]),
        sa.ForeignKeyConstraint(["lead_event_id"], ["lead_events.id"]),
        sa.CheckConstraint(
            "channel IN ('telegram', 'phone', 'whatsapp', 'email', 'meeting', 'other')",
            name="ck_touchpoints_channel",
        ),
        sa.CheckConstraint(
            "direction IN ('inbound', 'outbound', 'internal_note')",
            name="ck_touchpoints_direction",
        ),
    )
    op.create_index("ix_touchpoints_client_created", "touchpoints", ["client_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_touchpoints_client_created", table_name="touchpoints")
    op.drop_table("touchpoints")
    op.drop_index("ix_contact_reasons_queue", table_name="contact_reasons")
    op.drop_index("ix_contact_reasons_client", table_name="contact_reasons")
    op.drop_table("contact_reasons")
    op.drop_index("ix_support_cases_queue", table_name="support_cases")
    op.drop_index("ix_support_cases_client", table_name="support_cases")
    op.drop_table("support_cases")
    op.drop_index("ix_opportunities_queue", table_name="opportunities")
    op.drop_index("ix_opportunities_client", table_name="opportunities")
    op.drop_table("opportunities")
    op.drop_index("ix_client_assets_service_due", table_name="client_assets")
    op.drop_index("ix_client_assets_client", table_name="client_assets")
    op.drop_table("client_assets")
    op.drop_index("ix_client_interests_reactivation", table_name="client_interests")
    op.drop_index("ix_client_interests_client", table_name="client_interests")
    op.drop_table("client_interests")
    op.drop_index("ix_client_objects_client", table_name="client_objects")
    op.drop_table("client_objects")
    op.drop_index("ix_contacts_email", table_name="contacts")
    op.drop_index("ix_contacts_phone", table_name="contacts")
    op.drop_index("ix_contacts_telegram_username", table_name="contacts")
    op.drop_index("ix_contacts_telegram_user_id", table_name="contacts")
    op.drop_index("ix_contacts_client", table_name="contacts")
    op.drop_table("contacts")
    op.drop_index("ix_clients_status_updated", table_name="clients")
    op.drop_table("clients")
