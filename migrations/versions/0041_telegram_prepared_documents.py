"""Store prepared Telegram search documents in the operational database.

Revision ID: 0041_telegram_prepared_documents
Revises: 0040_interest_intent_context_patterns
Create Date: 2026-05-06
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0041_telegram_prepared_documents"
down_revision: str | None = "0040_interest_intent_context_patterns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_prepared_documents",
        sa.Column("id", sa.String(length=160), primary_key=True),
        sa.Column("raw_export_run_id", sa.String(length=36), nullable=False),
        sa.Column("monitored_source_id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("telegram_message_id", sa.Integer(), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("artifact_id", sa.String(length=160), nullable=False),
        sa.Column("artifact_kind", sa.String(length=64), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("final_url", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("file_name", sa.Text(), nullable=True),
        sa.Column("reply_to_message_id", sa.Integer(), nullable=True),
        sa.Column("thread_id", sa.String(length=80), nullable=True),
        sa.Column("thread_key", sa.String(length=80), nullable=False),
        sa.Column("date", sa.String(length=64), nullable=True),
        sa.Column("message_url", sa.Text(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("clean_text", sa.Text(), nullable=True),
        sa.Column("lemmas_text", sa.Text(), nullable=True),
        sa.Column("normalization_lang", sa.String(length=32), nullable=False),
        sa.Column("tokens_json", sa.JSON(), nullable=True),
        sa.Column("lemmas_json", sa.JSON(), nullable=True),
        sa.Column("pos_tags_json", sa.JSON(), nullable=True),
        sa.Column("token_map_json", sa.JSON(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("has_text", sa.Boolean(), nullable=False),
        sa.Column("normalization_status", sa.String(length=64), nullable=False),
        sa.Column("normalization_error", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("feature_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "entity_type IN ('telegram_message', 'telegram_artifact')",
            name="ck_telegram_prepared_documents_entity_type",
        ),
    )
    op.create_index(
        "ix_telegram_prepared_documents_raw_entity",
        "telegram_prepared_documents",
        ["raw_export_run_id", "entity_type"],
    )
    op.create_index(
        "ix_telegram_prepared_documents_source_message",
        "telegram_prepared_documents",
        ["monitored_source_id", "telegram_message_id"],
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            ALTER TABLE telegram_prepared_documents
            ADD COLUMN search_vector tsvector
            GENERATED ALWAYS AS (
              to_tsvector(
                'simple',
                coalesce(clean_text, '') || ' ' || coalesce(lemmas_text, '')
              )
            ) STORED
            """
        )
        op.execute(
            """
            CREATE INDEX ix_telegram_prepared_documents_search_vector
            ON telegram_prepared_documents USING GIN (search_vector)
            """
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_telegram_prepared_documents_search_vector")
    op.drop_index(
        "ix_telegram_prepared_documents_source_message",
        table_name="telegram_prepared_documents",
    )
    op.drop_index(
        "ix_telegram_prepared_documents_raw_entity",
        table_name="telegram_prepared_documents",
    )
    op.drop_table("telegram_prepared_documents")
