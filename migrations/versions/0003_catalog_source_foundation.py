"""Create catalog source-of-truth tables.

Revision ID: 0003_catalog_source_foundation
Revises: 0002_telegram_sources
Create Date: 2026-04-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0003_catalog_source_foundation"
down_revision: str | None = "0002_telegram_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("origin", sa.String(255), nullable=False),
        sa.Column("external_id", sa.String(512), nullable=False),
        sa.Column("url", sa.String(1024), nullable=True),
        sa.Column("title", sa.String(512), nullable=True),
        sa.Column("author", sa.String(255), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("normalized_text", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_type IN ('telegram_message', 'telegraph_page', 'external_page', "
            "'manual_text', 'manual_link')",
            name="ck_sources_type",
        ),
    )
    op.create_index(
        "uq_sources_identity",
        "sources",
        ["source_type", "origin", "external_id"],
        unique=True,
    )
    op.create_index("ix_sources_content_hash", "sources", ["content_hash"])

    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("artifact_type", sa.String(64), nullable=False),
        sa.Column("file_name", sa.String(512), nullable=True),
        sa.Column("mime_type", sa.String(255), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("local_path", sa.String(1024), nullable=True),
        sa.Column("download_status", sa.String(32), nullable=False),
        sa.Column("skip_reason", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.CheckConstraint(
            "artifact_type IN ('document', 'image_metadata', 'video_metadata', 'audio_metadata')",
            name="ck_artifacts_type",
        ),
        sa.CheckConstraint(
            "download_status IN ('downloaded', 'skipped', 'failed')",
            name="ck_artifacts_download_status",
        ),
    )
    op.create_index("ix_artifacts_source_id", "artifacts", ["source_id"])
    op.create_index("ix_artifacts_sha256", "artifacts", ["sha256"])

    op.create_table(
        "parsed_chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("artifact_id", sa.String(36), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_estimate", sa.Integer(), nullable=False),
        sa.Column("parser_name", sa.String(160), nullable=False),
        sa.Column("parser_version", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"]),
    )
    op.create_index(
        "uq_parsed_chunks_source_artifact_index",
        "parsed_chunks",
        ["source_id", "artifact_id", "chunk_index"],
        unique=True,
    )
    op.execute(
        "CREATE VIRTUAL TABLE parsed_chunks_fts USING fts5("
        "text, content='parsed_chunks', content_rowid='rowid')"
    )
    op.execute(
        """
        CREATE TRIGGER parsed_chunks_ai AFTER INSERT ON parsed_chunks BEGIN
            INSERT INTO parsed_chunks_fts(rowid, text) VALUES (new.rowid, new.text);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER parsed_chunks_ad AFTER DELETE ON parsed_chunks BEGIN
            INSERT INTO parsed_chunks_fts(parsed_chunks_fts, rowid, text)
            VALUES ('delete', old.rowid, old.text);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER parsed_chunks_au AFTER UPDATE ON parsed_chunks BEGIN
            INSERT INTO parsed_chunks_fts(parsed_chunks_fts, rowid, text)
            VALUES ('delete', old.rowid, old.text);
            INSERT INTO parsed_chunks_fts(rowid, text) VALUES (new.rowid, new.text);
        END
        """
    )

    op.create_table(
        "extraction_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_type", sa.String(64), nullable=False),
        sa.Column("model", sa.String(160), nullable=True),
        sa.Column("prompt_version", sa.String(80), nullable=True),
        sa.Column("catalog_version_id", sa.String(36), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("stats_json", sa.JSON(), nullable=True),
        sa.Column("source_scope_json", sa.JSON(), nullable=True),
        sa.Column("extractor_version", sa.String(80), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fact_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_catalog_entity_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("token_usage_json", sa.JSON(), nullable=True),
        sa.CheckConstraint(
            "run_type IN ('channel_sync', 'document_parse', 'catalog_extraction', "
            "'manual_example_parse')",
            name="ck_extraction_runs_type",
        ),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'cancelled')",
            name="ck_extraction_runs_status",
        ),
    )

    op.create_table(
        "catalog_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("catalog_hash", sa.String(64), nullable=False),
        sa.Column("candidate_hash", sa.String(64), nullable=True),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("term_count", sa.Integer(), nullable=False),
        sa.Column("offer_count", sa.Integer(), nullable=False),
        sa.Column("included_statuses_json", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("uq_catalog_versions_version", "catalog_versions", ["version"], unique=True)

    op.create_table(
        "extracted_facts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("extraction_run_id", sa.String(36), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=True),
        sa.Column("chunk_id", sa.String(36), nullable=True),
        sa.Column("fact_type", sa.String(64), nullable=False),
        sa.Column("canonical_name", sa.String(512), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["extraction_run_id"], ["extraction_runs.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.ForeignKeyConstraint(["chunk_id"], ["parsed_chunks.id"]),
        sa.CheckConstraint(
            "fact_type IN ('category', 'product', 'service', 'bundle', 'brand', "
            "'model', 'term', 'attribute', 'offer', 'lead_intent')",
            name="ck_extracted_facts_type",
        ),
        sa.CheckConstraint(
            "status IN ('new', 'accepted', 'rejected', 'merged')",
            name="ck_extracted_facts_status",
        ),
    )

    op.create_table(
        "catalog_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("candidate_type", sa.String(64), nullable=False),
        sa.Column("proposed_action", sa.String(32), nullable=False),
        sa.Column("canonical_name", sa.String(512), nullable=False),
        sa.Column("normalized_value_json", sa.JSON(), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("target_entity_type", sa.String(64), nullable=True),
        sa.Column("target_entity_id", sa.String(36), nullable=True),
        sa.Column("merge_target_candidate_id", sa.String(36), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["merge_target_candidate_id"], ["catalog_candidates.id"]),
        sa.CheckConstraint(
            "candidate_type IN ('category', 'item', 'term', 'attribute', 'offer', "
            "'relation', 'lead_phrase', 'negative_phrase')",
            name="ck_catalog_candidates_type",
        ),
        sa.CheckConstraint(
            "proposed_action IN ('create', 'update', 'merge', 'expire', 'ignore')",
            name="ck_catalog_candidates_action",
        ),
        sa.CheckConstraint(
            "status IN ('auto_pending', 'approved', 'rejected', 'merged', 'needs_review', 'muted')",
            name="ck_catalog_candidates_status",
        ),
    )
    op.create_index(
        "uq_catalog_candidates_identity",
        "catalog_candidates",
        ["candidate_type", "canonical_name", "proposed_action"],
        unique=True,
    )

    op.create_table(
        "catalog_candidate_facts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("catalog_candidate_id", sa.String(36), nullable=False),
        sa.Column("extracted_fact_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["catalog_candidate_id"], ["catalog_candidates.id"]),
        sa.ForeignKeyConstraint(["extracted_fact_id"], ["extracted_facts.id"]),
        sa.UniqueConstraint(
            "catalog_candidate_id",
            "extracted_fact_id",
            name="uq_catalog_candidate_facts_identity",
        ),
    )

    op.create_table(
        "catalog_categories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("parent_id", sa.String(36), nullable=True),
        sa.Column("slug", sa.String(160), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["catalog_categories.id"]),
        sa.CheckConstraint(
            "status IN ('auto_pending', 'approved', 'rejected', 'muted', "
            "'needs_review', 'deprecated', 'expired')",
            name="ck_catalog_categories_status",
        ),
    )
    op.create_index("uq_catalog_categories_slug", "catalog_categories", ["slug"], unique=True)

    op.create_table(
        "catalog_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("category_id", sa.String(36), nullable=True),
        sa.Column("item_type", sa.String(64), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("canonical_name", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("first_seen_source_id", sa.String(36), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["catalog_categories.id"]),
        sa.ForeignKeyConstraint(["first_seen_source_id"], ["sources.id"]),
        sa.CheckConstraint(
            "item_type IN ('product', 'service', 'bundle', 'brand', 'model', 'solution')",
            name="ck_catalog_items_type",
        ),
        sa.CheckConstraint(
            "status IN ('auto_pending', 'approved', 'rejected', 'muted', "
            "'needs_review', 'deprecated', 'expired')",
            name="ck_catalog_items_status",
        ),
    )
    op.create_index("uq_catalog_items_canonical", "catalog_items", ["canonical_name"], unique=True)

    op.create_table(
        "catalog_terms",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("item_id", sa.String(36), nullable=True),
        sa.Column("category_id", sa.String(36), nullable=True),
        sa.Column("term", sa.String(512), nullable=False),
        sa.Column("normalized_term", sa.String(512), nullable=False),
        sa.Column("term_type", sa.String(64), nullable=False),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column("first_seen_source_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["catalog_items.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["catalog_categories.id"]),
        sa.ForeignKeyConstraint(["first_seen_source_id"], ["sources.id"]),
        sa.CheckConstraint(
            "term_type IN ('keyword', 'alias', 'brand', 'model', 'problem_phrase', "
            "'lead_phrase', 'negative_phrase')",
            name="ck_catalog_terms_type",
        ),
        sa.CheckConstraint(
            "status IN ('auto_pending', 'approved', 'rejected', 'muted', "
            "'needs_review', 'deprecated', 'expired')",
            name="ck_catalog_terms_status",
        ),
    )
    op.create_index(
        "uq_catalog_terms_identity",
        "catalog_terms",
        ["item_id", "category_id", "normalized_term", "term_type"],
        unique=True,
    )

    op.create_table(
        "catalog_attributes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("item_id", sa.String(36), nullable=False),
        sa.Column("attribute_name", sa.String(255), nullable=False),
        sa.Column("attribute_value", sa.Text(), nullable=False),
        sa.Column("value_type", sa.String(32), nullable=False),
        sa.Column("unit", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["catalog_items.id"]),
        sa.CheckConstraint(
            "value_type IN ('text', 'number', 'money', 'bool', 'date', 'json')",
            name="ck_catalog_attributes_value_type",
        ),
    )
    op.create_index(
        "ix_catalog_attributes_item_name", "catalog_attributes", ["item_id", "attribute_name"]
    )

    op.create_table(
        "catalog_offers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("item_id", sa.String(36), nullable=True),
        sa.Column("category_id", sa.String(36), nullable=True),
        sa.Column("offer_type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price_amount", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(16), nullable=True),
        sa.Column("price_text", sa.String(255), nullable=True),
        sa.Column("terms_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ttl_days", sa.Integer(), nullable=True),
        sa.Column("ttl_source", sa.String(32), nullable=False),
        sa.Column("first_seen_source_id", sa.String(36), nullable=True),
        sa.Column("last_seen_source_id", sa.String(36), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["catalog_items.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["catalog_categories.id"]),
        sa.CheckConstraint(
            "offer_type IN ('price', 'promotion', 'bundle_price', 'service_price', "
            "'campaign', 'terms')",
            name="ck_catalog_offers_type",
        ),
        sa.CheckConstraint(
            "status IN ('auto_pending', 'approved', 'needs_review', 'expired', "
            "'rejected', 'muted')",
            name="ck_catalog_offers_status",
        ),
        sa.CheckConstraint(
            "ttl_source IN ('explicit', 'default_setting', 'manual', 'none')",
            name="ck_catalog_offers_ttl_source",
        ),
    )

    op.create_table(
        "catalog_relations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("from_item_id", sa.String(36), nullable=False),
        sa.Column("to_item_id", sa.String(36), nullable=False),
        sa.Column("relation_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["from_item_id"], ["catalog_items.id"]),
        sa.ForeignKeyConstraint(["to_item_id"], ["catalog_items.id"]),
        sa.CheckConstraint(
            "relation_type IN ('brand_of', 'model_of', 'part_of_bundle', 'requires', "
            "'compatible_with', 'alternative_to', 'replaces')",
            name="ck_catalog_relations_type",
        ),
    )

    op.create_table(
        "catalog_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=True),
        sa.Column("artifact_id", sa.String(36), nullable=True),
        sa.Column("chunk_id", sa.String(36), nullable=True),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("location_json", sa.JSON(), nullable=True),
        sa.Column("extractor_version", sa.String(80), nullable=True),
        sa.Column("evidence_type", sa.String(64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"]),
        sa.ForeignKeyConstraint(["chunk_id"], ["parsed_chunks.id"]),
        sa.CheckConstraint(
            "entity_type IN ('category', 'item', 'term', 'attribute', 'relation', "
            "'offer', 'catalog_candidate', 'extracted_fact')",
            name="ck_catalog_evidence_entity_type",
        ),
        sa.CheckConstraint(
            "evidence_type IN ('ai_quote', 'manual_note', 'source_link', 'document_quote')",
            name="ck_catalog_evidence_type",
        ),
    )
    op.create_index(
        "uq_catalog_evidence_identity",
        "catalog_evidence",
        ["entity_type", "entity_id", "source_id", "artifact_id", "chunk_id", "evidence_type"],
        unique=True,
    )

    op.create_table(
        "manual_inputs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("input_type", sa.String(64), nullable=False),
        sa.Column("submission_channel", sa.String(32), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("url", sa.String(1024), nullable=True),
        sa.Column("chat_ref", sa.String(255), nullable=True),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("submitted_by", sa.String(160), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processing_status", sa.String(32), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.CheckConstraint(
            "input_type IN ('telegram_link', 'forwarded_message', 'manual_text', "
            "'catalog_note', 'lead_example', 'catalog_item', 'catalog_term', "
            "'catalog_offer', 'catalog_relation', 'catalog_attribute')",
            name="ck_manual_inputs_type",
        ),
        sa.CheckConstraint(
            "submission_channel IN ('web', 'telegram_bot', 'import')",
            name="ck_manual_inputs_channel",
        ),
        sa.CheckConstraint(
            "processing_status IN ('new', 'fetched', 'processed', 'failed')",
            name="ck_manual_inputs_status",
        ),
    )

    op.create_table(
        "classifier_examples",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("example_type", sa.String(64), nullable=False),
        sa.Column("polarity", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("source_message_id", sa.String(36), nullable=True),
        sa.Column("raw_source_id", sa.String(36), nullable=True),
        sa.Column("lead_cluster_id", sa.String(36), nullable=True),
        sa.Column("lead_event_id", sa.String(36), nullable=True),
        sa.Column("category_id", sa.String(36), nullable=True),
        sa.Column("catalog_item_id", sa.String(36), nullable=True),
        sa.Column("catalog_term_id", sa.String(36), nullable=True),
        sa.Column("reason_code", sa.String(80), nullable=True),
        sa.Column("example_text", sa.Text(), nullable=False),
        sa.Column("context_json", sa.JSON(), nullable=True),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("created_from", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["raw_source_id"], ["sources.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["catalog_categories.id"]),
        sa.ForeignKeyConstraint(["catalog_item_id"], ["catalog_items.id"]),
        sa.ForeignKeyConstraint(["catalog_term_id"], ["catalog_terms.id"]),
    )

    op.create_table(
        "classifier_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("catalog_version_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column("included_statuses_json", sa.JSON(), nullable=False),
        sa.Column("catalog_hash", sa.String(64), nullable=False),
        sa.Column("example_hash", sa.String(64), nullable=False),
        sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("keyword_index_hash", sa.String(64), nullable=False),
        sa.Column("settings_hash", sa.String(64), nullable=False),
        sa.Column("model", sa.String(160), nullable=True),
        sa.Column("model_config_hash", sa.String(64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["catalog_version_id"], ["catalog_versions.id"]),
    )
    op.create_index(
        "uq_classifier_versions_version", "classifier_versions", ["version"], unique=True
    )

    op.create_table(
        "classifier_snapshot_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("classifier_version_id", sa.String(36), nullable=False),
        sa.Column("entry_type", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=True),
        sa.Column("entity_id", sa.String(36), nullable=True),
        sa.Column("status_at_build", sa.String(32), nullable=True),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("text_value", sa.Text(), nullable=True),
        sa.Column("normalized_value", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["classifier_version_id"], ["classifier_versions.id"]),
    )
    op.create_index(
        "ix_classifier_snapshot_entries_version",
        "classifier_snapshot_entries",
        ["classifier_version_id", "entry_type"],
    )

    op.create_table(
        "classifier_version_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("classifier_version_id", sa.String(36), nullable=False),
        sa.Column("artifact_type", sa.String(64), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("content_json", sa.JSON(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["classifier_version_id"], ["classifier_versions.id"]),
    )


def downgrade() -> None:
    op.drop_table("classifier_version_artifacts")
    op.drop_index(
        "ix_classifier_snapshot_entries_version", table_name="classifier_snapshot_entries"
    )
    op.drop_table("classifier_snapshot_entries")
    op.drop_index("uq_classifier_versions_version", table_name="classifier_versions")
    op.drop_table("classifier_versions")
    op.drop_table("classifier_examples")
    op.drop_table("manual_inputs")
    op.drop_index("uq_catalog_evidence_identity", table_name="catalog_evidence")
    op.drop_table("catalog_evidence")
    op.drop_table("catalog_relations")
    op.drop_table("catalog_offers")
    op.drop_index("ix_catalog_attributes_item_name", table_name="catalog_attributes")
    op.drop_table("catalog_attributes")
    op.drop_index("uq_catalog_terms_identity", table_name="catalog_terms")
    op.drop_table("catalog_terms")
    op.drop_index("uq_catalog_items_canonical", table_name="catalog_items")
    op.drop_table("catalog_items")
    op.drop_index("uq_catalog_categories_slug", table_name="catalog_categories")
    op.drop_table("catalog_categories")
    op.drop_table("catalog_candidate_facts")
    op.drop_index("uq_catalog_candidates_identity", table_name="catalog_candidates")
    op.drop_table("catalog_candidates")
    op.drop_table("extracted_facts")
    op.drop_index("uq_catalog_versions_version", table_name="catalog_versions")
    op.drop_table("catalog_versions")
    op.drop_table("extraction_runs")
    op.execute("DROP TRIGGER IF EXISTS parsed_chunks_au")
    op.execute("DROP TRIGGER IF EXISTS parsed_chunks_ad")
    op.execute("DROP TRIGGER IF EXISTS parsed_chunks_ai")
    op.execute("DROP TABLE IF EXISTS parsed_chunks_fts")
    op.drop_index("uq_parsed_chunks_source_artifact_index", table_name="parsed_chunks")
    op.drop_table("parsed_chunks")
    op.drop_index("ix_artifacts_sha256", table_name="artifacts")
    op.drop_index("ix_artifacts_source_id", table_name="artifacts")
    op.drop_table("artifacts")
    op.drop_index("ix_sources_content_hash", table_name="sources")
    op.drop_index("uq_sources_identity", table_name="sources")
    op.drop_table("sources")
