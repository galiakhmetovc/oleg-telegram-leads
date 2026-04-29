from sqlalchemy import inspect

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database


def test_sqlite_engine_enables_required_pragmas(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")

    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 30000
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one().lower() == "wal"


def test_foundation_migration_creates_core_tables(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")

    upgrade_database(engine)

    tables = set(inspect(engine).get_table_names())
    assert {
        "settings",
        "settings_revisions",
        "secret_refs",
        "audit_log",
        "operational_events",
        "scheduler_jobs",
        "job_runs",
        "notification_events",
        "backup_runs",
        "restore_runs",
        "decision_records",
        "evaluation_datasets",
        "evaluation_cases",
        "evaluation_runs",
        "evaluation_results",
        "catalog_quality_reviews",
        "quality_metric_snapshots",
        "ai_providers",
        "ai_provider_accounts",
        "ai_models",
        "ai_model_profiles",
        "ai_model_limits",
        "ai_agents",
        "ai_agent_routes",
        "ai_runs",
        "ai_run_outputs",
        "ai_model_concurrency_leases",
    }.issubset(tables)
