"""Add interest contexts.

Revision ID: 0029_interest_contexts
Revises: 0028_trace_foundation
Create Date: 2026-05-01
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0029_interest_contexts"
down_revision: str | None = "0028_trace_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "interest_contexts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_interest_contexts_status", "interest_contexts", ["status"])
    op.create_index("ix_interest_contexts_created_by", "interest_contexts", ["created_by"])

    with op.batch_alter_table("monitored_sources") as batch_op:
        batch_op.drop_constraint("ck_monitored_sources_purpose", type_="check")
        batch_op.add_column(sa.Column("interest_context_id", sa.String(36), nullable=True))
        batch_op.create_check_constraint(
            "ck_monitored_sources_purpose",
            "source_purpose IN "
            "('lead_monitoring', 'catalog_ingestion', 'both', 'interest_context_seed')",
        )
    op.create_index(
        "ix_monitored_sources_interest_context_id",
        "monitored_sources",
        ["interest_context_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_monitored_sources_interest_context_id",
        table_name="monitored_sources",
    )
    with op.batch_alter_table("monitored_sources") as batch_op:
        batch_op.drop_constraint("ck_monitored_sources_purpose", type_="check")
        batch_op.drop_column("interest_context_id")
        batch_op.create_check_constraint(
            "ck_monitored_sources_purpose",
            "source_purpose IN ('lead_monitoring', 'catalog_ingestion', 'both')",
        )

    op.drop_index("ix_interest_contexts_created_by", table_name="interest_contexts")
    op.drop_index("ix_interest_contexts_status", table_name="interest_contexts")
    op.drop_table("interest_contexts")
