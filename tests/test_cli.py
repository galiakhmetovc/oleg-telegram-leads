from sqlalchemy import inspect

from pur_leads.cli import main
from pur_leads.db.engine import create_sqlite_engine


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
