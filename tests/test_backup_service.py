import sqlite3
import subprocess
from pathlib import Path

from sqlalchemy import select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.audit import audit_log_table, operational_events_table
from pur_leads.models.backup import backup_runs_table, restore_runs_table
from pur_leads.services.backup import BackupService
from pur_leads.services.settings import SettingsService


def test_backup_service_creates_verified_sqlite_backup_and_restore_dry_run(tmp_path):
    db_path = tmp_path / "test.db"
    backup_root = tmp_path / "backups"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        SettingsService(session).set(
            "telegram_worker_count",
            2,
            value_type="int",
            updated_by="admin",
            reason="test backup content",
        )
        service = BackupService(session, database_path=db_path, backup_root=backup_root)
        backup = service.create_database_backup(actor="admin")
        restore = service.create_restore_dry_run(backup["id"], actor="admin")

    assert backup["backup_type"] == "sqlite"
    assert backup["status"] == "verified"
    assert backup["storage_backend"] == "local"
    assert backup["size_bytes"] > 0
    assert len(backup["sha256"]) == 64
    assert backup["manifest_json"]["validation"]["quick_check"] == "ok"
    assert backup["manifest_json"]["tables"]["settings"] == 1
    assert (backup_root / backup["storage_uri"]).exists()
    assert restore["restore_type"] == "dry_run"
    assert restore["status"] == "completed"
    assert restore["validation_status"] == "passed"
    assert restore["validation_details_json"]["quick_check"] == "ok"

    with sqlite3.connect(backup_root / backup["storage_uri"]) as backup_connection:
        assert (
            backup_connection.execute(
                "select value_json from settings where key = ?", ("telegram_worker_count",)
            ).fetchone()[0]
            == 2
        )

    with session_factory() as session:
        stored_backup = (
            session.execute(select(backup_runs_table).where(backup_runs_table.c.id == backup["id"]))
            .mappings()
            .one()
        )
        stored_restore = (
            session.execute(
                select(restore_runs_table).where(restore_runs_table.c.id == restore["id"])
            )
            .mappings()
            .one()
        )
        audit_actions = [
            row["action"] for row in session.execute(select(audit_log_table)).mappings().all()
        ]
        events = session.execute(select(operational_events_table)).mappings().all()

    assert stored_backup["status"] == "verified"
    assert stored_restore["validation_status"] == "passed"
    assert "backup.created" in audit_actions
    assert "restore.dry_run" in audit_actions
    assert any(row["entity_type"] == "backup_run" for row in events)
    assert any(row["entity_type"] == "restore_run" for row in events)


def test_backup_service_creates_verified_postgres_pg_dump_backup(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    backup_root = tmp_path / "backups"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):  # noqa: ANN001
        calls.append(list(command))
        if command[0] == "pg_dump":
            Path(command[command.index("--file") + 1]).write_bytes(b"postgres dump")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command[0] == "pg_restore":
            return subprocess.CompletedProcess(
                command, 0, stdout="TABLE public.settings\n", stderr=""
            )
        raise AssertionError(command)

    monkeypatch.setattr("pur_leads.services.backup.subprocess.run", fake_run)

    with session_factory() as session:
        service = BackupService(
            session,
            backup_root=backup_root,
            database_url="postgresql+psycopg://pur_user:secret@db.local:5432/pur_leads",
        )
        backup = service.create_database_backup(actor="admin")
        restore = service.create_restore_dry_run(backup["id"], actor="admin")

    assert backup["backup_type"] == "postgres_pg_dump"
    assert backup["status"] == "verified"
    assert backup["storage_backend"] == "local"
    assert backup["manifest_json"]["database"]["host"] == "db.local"
    assert backup["manifest_json"]["database"]["database"] == "pur_leads"
    assert "secret" not in str(backup["manifest_json"])
    assert (backup_root / backup["storage_uri"]).read_bytes() == b"postgres dump"
    assert restore["validation_status"] == "passed"
    assert calls[0][:2] == ["pg_dump", "--format=custom"]
    assert "--dbname" in calls[0]
    assert calls[1][0] == "pg_restore"
