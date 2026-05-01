from sqlalchemy import inspect
from sqlalchemy import text

from pur_leads.db.engine import create_database_engine, create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.models.catalog import catalog_quality_reviews_table


def test_sqlite_engine_enables_required_pragmas(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")

    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 30000
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one().lower() == "wal"


def test_database_engine_uses_postgres_url_when_configured():
    engine = create_database_engine(
        database_url="postgresql+psycopg://pur:secret@db.example.test:5432/pur_leads",
        sqlite_path="ignored.sqlite3",
    )

    assert engine.url.get_backend_name() == "postgresql"
    assert engine.url.get_driver_name() == "psycopg"
    assert engine.url.database == "pur_leads"


def test_database_engine_falls_back_to_sqlite_path(tmp_path):
    engine = create_database_engine(database_url=None, sqlite_path=tmp_path / "fallback.db")

    assert engine.url.get_backend_name() == "sqlite"


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
        "telegram_raw_export_runs",
        "canonical_entities",
        "canonical_entity_aliases",
        "entity_enrichment_runs",
        "entity_enrichment_results",
        "canonical_merge_candidates",
        "trace_spans",
        "trace_span_events",
        "trace_span_links",
    }.issubset(tables)


def test_catalog_quality_review_migration_handles_partial_table_from_concurrent_startup(
    tmp_path,
):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine, revision="0021_ai_model_profiles")
    with engine.begin() as connection:
        catalog_quality_reviews_table.create(connection)
        connection.execute(text("create table _alembic_tmp_scheduler_jobs (id text)"))

    upgrade_database(engine)

    with engine.connect() as connection:
        assert connection.execute(text("select version_num from alembic_version")).scalar_one() == (
            "0028_trace_foundation"
        )
        scheduler_sql = connection.execute(
            text("select sql from sqlite_master where type='table' and name='scheduler_jobs'")
        ).scalar_one()
        assert "catalog_candidate_validation" in scheduler_sql
        assert "export_telegram_raw" in scheduler_sql
        assert "trace_id" in scheduler_sql
        job_runs_sql = connection.execute(
            text("select sql from sqlite_master where type='table' and name='job_runs'")
        ).scalar_one()
        assert "span_id" in job_runs_sql
        assert "_alembic_tmp_scheduler_jobs" not in set(inspect(engine).get_table_names())
