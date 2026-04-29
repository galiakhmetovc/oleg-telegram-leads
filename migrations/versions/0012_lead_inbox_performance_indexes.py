"""Add lead inbox performance indexes.

Revision ID: 0012_lead_inbox_performance_indexes
Revises: 0011_decision_evaluation_foundation
Create Date: 2026-04-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012_lead_inbox_performance_indexes"
down_revision: str | None = "0011_decision_evaluation_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_lead_clusters_last_message", "lead_clusters", ["last_message_at"])
    op.create_index("ix_lead_events_cluster_retro", "lead_events", ["lead_cluster_id", "is_retro"])
    op.create_index("ix_lead_matches_event", "lead_matches", ["lead_event_id"])
    op.create_index(
        "ix_lead_cluster_actions_to_type",
        "lead_cluster_actions",
        ["to_cluster_id", "action_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_lead_cluster_actions_to_type", table_name="lead_cluster_actions")
    op.drop_index("ix_lead_matches_event", table_name="lead_matches")
    op.drop_index("ix_lead_events_cluster_retro", table_name="lead_events")
    op.drop_index("ix_lead_clusters_last_message", table_name="lead_clusters")
