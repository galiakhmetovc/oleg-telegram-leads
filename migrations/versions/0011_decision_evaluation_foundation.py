"""Create decision trace and evaluation foundation tables.

Revision ID: 0011_decision_evaluation_foundation
Revises: 0010_backup_restore_foundation
Create Date: 2026-04-29
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0011_decision_evaluation_foundation"
down_revision: str | None = "0010_backup_restore_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "decision_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("decision_type", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("dedupe_key", sa.String(255), nullable=True),
        sa.Column("source_message_id", sa.String(36), nullable=True),
        sa.Column("lead_event_id", sa.String(36), nullable=True),
        sa.Column("lead_cluster_id", sa.String(36), nullable=True),
        sa.Column("source_id", sa.String(36), nullable=True),
        sa.Column("classifier_version_id", sa.String(36), nullable=True),
        sa.Column("catalog_version_id", sa.String(36), nullable=True),
        sa.Column("catalog_hash", sa.String(64), nullable=True),
        sa.Column("prompt_hash", sa.String(64), nullable=True),
        sa.Column("prompt_version", sa.String(80), nullable=True),
        sa.Column("model", sa.String(160), nullable=True),
        sa.Column("settings_hash", sa.String(64), nullable=True),
        sa.Column("decision", sa.String(64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("input_json", sa.JSON(), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=True),
        sa.Column("output_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_message_id"], ["source_messages.id"]),
        sa.ForeignKeyConstraint(["lead_event_id"], ["lead_events.id"]),
        sa.ForeignKeyConstraint(["lead_cluster_id"], ["lead_clusters.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.ForeignKeyConstraint(["classifier_version_id"], ["classifier_versions.id"]),
        sa.ForeignKeyConstraint(["catalog_version_id"], ["catalog_versions.id"]),
        sa.CheckConstraint(
            "decision_type IN ('lead_detection', 'catalog_extraction', 'notification_policy', "
            "'clustering', 'crm_conversion', 'contact_reason', 'research_match', 'manual')",
            name="ck_decision_records_type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'superseded', 'ignored')",
            name="ck_decision_records_status",
        ),
    )
    op.create_index(
        "uq_decision_records_dedupe_key", "decision_records", ["dedupe_key"], unique=True
    )
    op.create_index("ix_decision_records_entity", "decision_records", ["entity_type", "entity_id"])
    op.create_index("ix_decision_records_source_message", "decision_records", ["source_message_id"])
    op.create_index(
        "ix_decision_records_type_created", "decision_records", ["decision_type", "created_at"]
    )

    op.create_table(
        "evaluation_datasets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("dataset_key", sa.String(160), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("dataset_type", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "dataset_type IN ('golden', 'feedback_regression', 'retro_research', "
            "'catalog_extraction', 'notification_policy', 'crm_conversion')",
            name="ck_evaluation_datasets_type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'archived', 'draft')",
            name="ck_evaluation_datasets_status",
        ),
    )
    op.create_index(
        "uq_evaluation_datasets_key", "evaluation_datasets", ["dataset_key"], unique=True
    )
    op.create_index(
        "ix_evaluation_datasets_type_status",
        "evaluation_datasets",
        ["dataset_type", "status"],
    )

    op.create_table(
        "evaluation_cases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("evaluation_dataset_id", sa.String(36), nullable=False),
        sa.Column("source_message_id", sa.String(36), nullable=True),
        sa.Column("lead_cluster_id", sa.String(36), nullable=True),
        sa.Column("lead_event_id", sa.String(36), nullable=True),
        sa.Column("feedback_event_id", sa.String(36), nullable=True),
        sa.Column("source_id", sa.String(36), nullable=True),
        sa.Column("message_text", sa.Text(), nullable=True),
        sa.Column("context_json", sa.JSON(), nullable=True),
        sa.Column("expected_decision", sa.String(32), nullable=True),
        sa.Column("expected_category_id", sa.String(36), nullable=True),
        sa.Column("expected_catalog_item_ids_json", sa.JSON(), nullable=True),
        sa.Column("expected_reason_code", sa.String(80), nullable=True),
        sa.Column("expected_notification_policy", sa.String(32), nullable=True),
        sa.Column("expected_cluster_behavior", sa.String(32), nullable=True),
        sa.Column("expected_crm_candidate_json", sa.JSON(), nullable=True),
        sa.Column("label_source", sa.String(32), nullable=False),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["evaluation_dataset_id"], ["evaluation_datasets.id"]),
        sa.ForeignKeyConstraint(["source_message_id"], ["source_messages.id"]),
        sa.ForeignKeyConstraint(["lead_cluster_id"], ["lead_clusters.id"]),
        sa.ForeignKeyConstraint(["lead_event_id"], ["lead_events.id"]),
        sa.ForeignKeyConstraint(["feedback_event_id"], ["feedback_events.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.ForeignKeyConstraint(["expected_category_id"], ["catalog_categories.id"]),
        sa.CheckConstraint(
            "expected_decision IN ('lead', 'maybe', 'not_lead') OR expected_decision IS NULL",
            name="ck_evaluation_cases_expected_decision",
        ),
        sa.CheckConstraint(
            "expected_notification_policy IN ('immediate', 'digest', 'web_only', 'suppressed') "
            "OR expected_notification_policy IS NULL",
            name="ck_evaluation_cases_notification_policy",
        ),
        sa.CheckConstraint(
            "expected_cluster_behavior IN ('new_cluster', 'merge', 'context_only', 'split') "
            "OR expected_cluster_behavior IS NULL",
            name="ck_evaluation_cases_cluster_behavior",
        ),
        sa.CheckConstraint(
            "label_source IN ('manual', 'feedback', 'import', 'synthetic')",
            name="ck_evaluation_cases_label_source",
        ),
    )
    op.create_index(
        "uq_evaluation_cases_dataset_feedback",
        "evaluation_cases",
        ["evaluation_dataset_id", "feedback_event_id"],
        unique=True,
    )
    op.create_index(
        "ix_evaluation_cases_dataset", "evaluation_cases", ["evaluation_dataset_id", "created_at"]
    )
    op.create_index("ix_evaluation_cases_source_message", "evaluation_cases", ["source_message_id"])

    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("evaluation_dataset_id", sa.String(36), nullable=False),
        sa.Column("run_type", sa.String(64), nullable=False),
        sa.Column("classifier_version_id", sa.String(36), nullable=True),
        sa.Column("catalog_hash", sa.String(64), nullable=True),
        sa.Column("prompt_hash", sa.String(64), nullable=True),
        sa.Column("model", sa.String(160), nullable=True),
        sa.Column("settings_hash", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metrics_json", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["evaluation_dataset_id"], ["evaluation_datasets.id"]),
        sa.ForeignKeyConstraint(["classifier_version_id"], ["classifier_versions.id"]),
        sa.CheckConstraint(
            "run_type IN ('lead_detection', 'catalog_extraction', 'notification_policy', "
            "'clustering', 'crm_conversion', 'full_pipeline')",
            name="ck_evaluation_runs_type",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_evaluation_runs_status",
        ),
    )
    op.create_index(
        "ix_evaluation_runs_dataset_status",
        "evaluation_runs",
        ["evaluation_dataset_id", "status", "started_at"],
    )

    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("evaluation_run_id", sa.String(36), nullable=False),
        sa.Column("evaluation_case_id", sa.String(36), nullable=False),
        sa.Column("decision_record_id", sa.String(36), nullable=True),
        sa.Column("actual_decision", sa.String(32), nullable=True),
        sa.Column("actual_category_id", sa.String(36), nullable=True),
        sa.Column("actual_catalog_item_ids_json", sa.JSON(), nullable=True),
        sa.Column("actual_notification_policy", sa.String(32), nullable=True),
        sa.Column("actual_cluster_behavior", sa.String(32), nullable=True),
        sa.Column("actual_crm_candidate_json", sa.JSON(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("failure_type", sa.String(64), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["evaluation_run_id"], ["evaluation_runs.id"]),
        sa.ForeignKeyConstraint(["evaluation_case_id"], ["evaluation_cases.id"]),
        sa.ForeignKeyConstraint(["decision_record_id"], ["decision_records.id"]),
        sa.ForeignKeyConstraint(["actual_category_id"], ["catalog_categories.id"]),
        sa.CheckConstraint(
            "actual_decision IN ('lead', 'maybe', 'not_lead') OR actual_decision IS NULL",
            name="ck_evaluation_results_actual_decision",
        ),
        sa.CheckConstraint(
            "failure_type IN ('false_positive', 'false_negative', 'wrong_category', "
            "'wrong_item', 'wrong_notification', 'wrong_cluster', 'wrong_crm_candidate', "
            "'parse_error', 'other') OR failure_type IS NULL",
            name="ck_evaluation_results_failure_type",
        ),
    )
    op.create_index(
        "uq_evaluation_results_run_case",
        "evaluation_results",
        ["evaluation_run_id", "evaluation_case_id"],
        unique=True,
    )
    op.create_index(
        "ix_evaluation_results_run_passed",
        "evaluation_results",
        ["evaluation_run_id", "passed", "failure_type"],
    )

    op.create_table(
        "quality_metric_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scope", sa.String(64), nullable=False),
        sa.Column("scope_id", sa.String(160), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("precision", sa.Float(), nullable=True),
        sa.Column("recall", sa.Float(), nullable=True),
        sa.Column("f1", sa.Float(), nullable=True),
        sa.Column("false_positive_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("false_negative_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("maybe_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("maybe_resolution_rate", sa.Float(), nullable=True),
        sa.Column("high_value_precision", sa.Float(), nullable=True),
        sa.Column("retro_precision", sa.Float(), nullable=True),
        sa.Column("telegram_notification_precision", sa.Float(), nullable=True),
        sa.Column("catalog_candidate_accept_rate", sa.Float(), nullable=True),
        sa.Column("catalog_candidate_reject_rate", sa.Float(), nullable=True),
        sa.Column("feedback_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metrics_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "scope IN ('overall', 'source', 'category', 'model', 'classifier_version', "
            "'notification_policy', 'catalog_extraction')",
            name="ck_quality_metric_snapshots_scope",
        ),
    )
    op.create_index(
        "ix_quality_metric_snapshots_scope_created",
        "quality_metric_snapshots",
        ["scope", "scope_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_quality_metric_snapshots_scope_created", table_name="quality_metric_snapshots"
    )
    op.drop_table("quality_metric_snapshots")
    op.drop_index("ix_evaluation_results_run_passed", table_name="evaluation_results")
    op.drop_index("uq_evaluation_results_run_case", table_name="evaluation_results")
    op.drop_table("evaluation_results")
    op.drop_index("ix_evaluation_runs_dataset_status", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")
    op.drop_index("ix_evaluation_cases_source_message", table_name="evaluation_cases")
    op.drop_index("ix_evaluation_cases_dataset", table_name="evaluation_cases")
    op.drop_index("uq_evaluation_cases_dataset_feedback", table_name="evaluation_cases")
    op.drop_table("evaluation_cases")
    op.drop_index("ix_evaluation_datasets_type_status", table_name="evaluation_datasets")
    op.drop_index("uq_evaluation_datasets_key", table_name="evaluation_datasets")
    op.drop_table("evaluation_datasets")
    op.drop_index("ix_decision_records_type_created", table_name="decision_records")
    op.drop_index("ix_decision_records_source_message", table_name="decision_records")
    op.drop_index("ix_decision_records_entity", table_name="decision_records")
    op.drop_index("uq_decision_records_dedupe_key", table_name="decision_records")
    op.drop_table("decision_records")
