from sqlalchemy import inspect

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database


def test_evaluation_migration_creates_decision_and_quality_tables(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")

    upgrade_database(engine)

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {
        "decision_records",
        "evaluation_datasets",
        "evaluation_cases",
        "evaluation_runs",
        "evaluation_results",
        "quality_metric_snapshots",
    }.issubset(tables)

    decision_columns = _column_names(inspector, "decision_records")
    assert {
        "decision_type",
        "entity_type",
        "entity_id",
        "source_message_id",
        "classifier_version_id",
        "catalog_hash",
        "prompt_hash",
        "model",
        "decision",
        "confidence",
        "reason",
        "input_json",
        "evidence_json",
        "created_at",
    }.issubset(decision_columns)

    case_columns = _column_names(inspector, "evaluation_cases")
    assert {
        "evaluation_dataset_id",
        "source_message_id",
        "lead_cluster_id",
        "lead_event_id",
        "source_id",
        "message_text",
        "context_json",
        "expected_decision",
        "expected_category_id",
        "expected_catalog_item_ids_json",
        "expected_reason_code",
        "expected_notification_policy",
        "expected_cluster_behavior",
        "expected_crm_candidate_json",
        "label_source",
    }.issubset(case_columns)


def _column_names(inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}
