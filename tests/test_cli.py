from sqlalchemy import inspect
from sqlalchemy import select

from pur_leads.cli import main
from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.audit import operational_events_table
from pur_leads.services.scheduler import SchedulerService


def test_cli_db_upgrade_creates_database(tmp_path):
    db_path = tmp_path / "cli.db"

    main(["--database-path", str(db_path), "db", "upgrade"])

    tables = set(inspect(create_sqlite_engine(db_path)).get_table_names())
    assert "settings" in tables
    assert "scheduler_jobs" in tables


def test_cli_settings_set_and_list(tmp_path, capsys):
    db_path = tmp_path / "cli.db"
    main(["--database-path", str(db_path), "db", "upgrade"])

    main(["--database-path", str(db_path), "settings", "set", "telegram_worker_count", "2"])
    main(["--database-path", str(db_path), "settings", "list"])

    output = capsys.readouterr().out
    assert "telegram_worker_count=2" in output


def test_cli_worker_once_reports_noop(tmp_path, capsys):
    db_path = tmp_path / "cli.db"
    main(["--database-path", str(db_path), "db", "upgrade"])

    main(["--database-path", str(db_path), "worker", "once"])

    output = capsys.readouterr().out
    assert "no queued jobs" in output


def test_cli_worker_once_uses_canonical_handler_registry(tmp_path, capsys):
    db_path = tmp_path / "cli.db"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        job = SchedulerService(session).enqueue(
            job_type="classify_message_batch",
            scope_type="telegram_source",
        )

    main(["--database-path", str(db_path), "worker", "once"])

    with session_factory() as session:
        stored = SchedulerService(session).repository.get(job.id)
        event = session.execute(select(operational_events_table)).mappings().one()
    output = capsys.readouterr().out
    assert stored is not None
    assert "failed job" in output
    assert stored.last_error == "classify_message_batch adapter is not configured"
    assert event["details_json"]["reason"] == "handler_exception"
