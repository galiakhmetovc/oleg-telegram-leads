"""Local backup and restore validation behavior."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.models.backup import backup_runs_table, restore_runs_table
from pur_leads.services.audit import AuditService


class BackupService:
    def __init__(
        self,
        session: Session,
        *,
        backup_root: Path,
        database_path: Path | None = None,
        database_url: str | None = None,
    ) -> None:
        self.session = session
        self.database_path = Path(database_path) if database_path is not None else None
        self.database_url = database_url
        self.backup_root = Path(backup_root)
        self.audit = AuditService(session)

    def create_database_backup(self, *, actor: str) -> dict[str, Any]:
        if self.database_url:
            return self.create_postgres_backup(actor=actor)
        return self.create_sqlite_backup(actor=actor)

    def create_sqlite_backup(self, *, actor: str) -> dict[str, Any]:
        if self.database_path is None:
            raise ValueError("SQLite database path is not configured")
        now = utc_now()
        backup_id = new_id()
        relative_path = self._backup_relative_path(now=now, backup_id=backup_id)
        target_path = self.backup_root / relative_path
        self.session.execute(
            backup_runs_table.insert().values(
                id=backup_id,
                backup_type="sqlite",
                storage_backend="local",
                storage_uri=relative_path.as_posix(),
                status="running",
                started_at=now,
                finished_at=None,
                size_bytes=None,
                sha256=None,
                manifest_json={"source_database": self.database_path.name},
                error=None,
                created_at=now,
            )
        )
        self.session.commit()

        try:
            self._copy_sqlite_database(target_path)
            validation = self._validate_sqlite_backup(target_path)
            if validation["quick_check"] != "ok":
                raise ValueError(str(validation.get("error") or "SQLite backup validation failed"))
            sha256 = _sha256_file(target_path)
            size_bytes = target_path.stat().st_size
            finished_at = utc_now()
            manifest = {
                "source_database": self.database_path.name,
                "storage_uri": relative_path.as_posix(),
                "created_at": now.isoformat(),
                "finished_at": finished_at.isoformat(),
                "size_bytes": size_bytes,
                "sha256": sha256,
                "validation": validation,
                "tables": self._table_counts(target_path),
            }
            self.session.execute(
                update(backup_runs_table)
                .where(backup_runs_table.c.id == backup_id)
                .values(
                    status="verified",
                    finished_at=finished_at,
                    size_bytes=size_bytes,
                    sha256=sha256,
                    manifest_json=manifest,
                    error=None,
                )
            )
            self.audit.record_change(
                actor=actor,
                action="backup.created",
                entity_type="backup_run",
                entity_id=backup_id,
                old_value_json=None,
                new_value_json={
                    "backup_type": "sqlite",
                    "status": "verified",
                    "storage_backend": "local",
                    "storage_uri": relative_path.as_posix(),
                    "size_bytes": size_bytes,
                    "sha256": sha256,
                },
            )
            self.audit.record_event(
                event_type="scheduler",
                severity="info",
                message="SQLite backup verified",
                entity_type="backup_run",
                entity_id=backup_id,
                details_json={"storage_uri": relative_path.as_posix(), "size_bytes": size_bytes},
            )
            self.session.commit()
            return self.get_backup(backup_id)
        except Exception as exc:
            self.session.execute(
                update(backup_runs_table)
                .where(backup_runs_table.c.id == backup_id)
                .values(status="failed", finished_at=utc_now(), error=str(exc))
            )
            self.audit.record_event(
                event_type="scheduler",
                severity="error",
                message="SQLite backup failed",
                entity_type="backup_run",
                entity_id=backup_id,
                details_json={"error": str(exc)},
            )
            self.session.commit()
            raise

    def create_postgres_backup(self, *, actor: str) -> dict[str, Any]:
        if self.database_url is None:
            raise ValueError("Postgres database URL is not configured")
        url = make_url(self.database_url)
        if url.get_backend_name() != "postgresql":
            raise ValueError("Database URL is not a Postgres URL")

        now = utc_now()
        backup_id = new_id()
        relative_path = self._postgres_backup_relative_path(now=now, backup_id=backup_id)
        target_path = self.backup_root / relative_path
        database_manifest = _postgres_database_manifest(url)
        self.session.execute(
            backup_runs_table.insert().values(
                id=backup_id,
                backup_type="postgres_pg_dump",
                storage_backend="local",
                storage_uri=relative_path.as_posix(),
                status="running",
                started_at=now,
                finished_at=None,
                size_bytes=None,
                sha256=None,
                manifest_json={"database": database_manifest},
                error=None,
                created_at=now,
            )
        )
        self.session.commit()

        try:
            self._dump_postgres_database(target_path, url)
            validation = self._validate_postgres_backup(target_path)
            if validation["quick_check"] != "ok":
                raise ValueError(
                    str(validation.get("error") or "Postgres backup validation failed")
                )
            sha256 = _sha256_file(target_path)
            size_bytes = target_path.stat().st_size
            finished_at = utc_now()
            manifest = {
                "database": database_manifest,
                "storage_uri": relative_path.as_posix(),
                "created_at": now.isoformat(),
                "finished_at": finished_at.isoformat(),
                "size_bytes": size_bytes,
                "sha256": sha256,
                "validation": validation,
            }
            self.session.execute(
                update(backup_runs_table)
                .where(backup_runs_table.c.id == backup_id)
                .values(
                    status="verified",
                    finished_at=finished_at,
                    size_bytes=size_bytes,
                    sha256=sha256,
                    manifest_json=manifest,
                    error=None,
                )
            )
            self.audit.record_change(
                actor=actor,
                action="backup.created",
                entity_type="backup_run",
                entity_id=backup_id,
                old_value_json=None,
                new_value_json={
                    "backup_type": "postgres_pg_dump",
                    "status": "verified",
                    "storage_backend": "local",
                    "storage_uri": relative_path.as_posix(),
                    "size_bytes": size_bytes,
                    "sha256": sha256,
                },
            )
            self.audit.record_event(
                event_type="scheduler",
                severity="info",
                message="Postgres backup verified",
                entity_type="backup_run",
                entity_id=backup_id,
                details_json={"storage_uri": relative_path.as_posix(), "size_bytes": size_bytes},
            )
            self.session.commit()
            return self.get_backup(backup_id)
        except Exception as exc:
            self.session.execute(
                update(backup_runs_table)
                .where(backup_runs_table.c.id == backup_id)
                .values(status="failed", finished_at=utc_now(), error=str(exc))
            )
            self.audit.record_event(
                event_type="scheduler",
                severity="error",
                message="Postgres backup failed",
                entity_type="backup_run",
                entity_id=backup_id,
                details_json={"error": str(exc)},
            )
            self.session.commit()
            raise

    def create_restore_dry_run(self, backup_id: str, *, actor: str) -> dict[str, Any]:
        backup = self.get_backup(backup_id)
        now = utc_now()
        restore_id = new_id()
        self.session.execute(
            restore_runs_table.insert().values(
                id=restore_id,
                backup_run_id=backup_id,
                restore_type="dry_run",
                status="running",
                target_path=None,
                validation_status="not_checked",
                validation_details_json=None,
                started_at=now,
                finished_at=None,
                error=None,
                created_by=actor,
                created_at=now,
            )
        )
        self.session.commit()

        backup_path = self.backup_root / str(backup["storage_uri"])
        validation = self._validate_backup(backup, backup_path)
        passed = validation["quick_check"] == "ok"
        status = "completed" if passed else "failed"
        finished_at = utc_now()
        self.session.execute(
            update(restore_runs_table)
            .where(restore_runs_table.c.id == restore_id)
            .values(
                status=status,
                validation_status="passed" if passed else "failed",
                validation_details_json=validation,
                finished_at=finished_at,
                error=None if passed else validation.get("error"),
            )
        )
        self.audit.record_change(
            actor=actor,
            action="restore.dry_run",
            entity_type="restore_run",
            entity_id=restore_id,
            old_value_json=None,
            new_value_json={
                "backup_run_id": backup_id,
                "status": status,
                "validation_status": "passed" if passed else "failed",
            },
        )
        self.audit.record_event(
            event_type="scheduler",
            severity="info" if passed else "error",
            message="Restore dry run validated" if passed else "Restore dry run failed",
            entity_type="restore_run",
            entity_id=restore_id,
            details_json={"backup_run_id": backup_id, "validation": validation},
        )
        self.session.commit()
        return self.get_restore(restore_id)

    def get_backup(self, backup_id: str) -> dict[str, Any]:
        row = (
            self.session.execute(
                select(backup_runs_table).where(backup_runs_table.c.id == backup_id)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise KeyError(backup_id)
        return dict(row)

    def get_restore(self, restore_id: str) -> dict[str, Any]:
        row = (
            self.session.execute(
                select(restore_runs_table).where(restore_runs_table.c.id == restore_id)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise KeyError(restore_id)
        return dict(row)

    def list_backups(self, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = (
            self.session.execute(
                select(backup_runs_table)
                .order_by(backup_runs_table.c.started_at.desc())
                .limit(limit)
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    def list_restores(self, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = (
            self.session.execute(
                select(restore_runs_table)
                .order_by(restore_runs_table.c.started_at.desc())
                .limit(limit)
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    def _copy_sqlite_database(self, target_path: Path) -> None:
        if self.database_path is None:
            raise ValueError("SQLite database path is not configured")
        if not self.database_path.exists():
            raise FileNotFoundError(f"Database does not exist: {self.database_path}")
        self.session.commit()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(_readonly_sqlite_uri(self.database_path), uri=True) as source:
            with sqlite3.connect(target_path) as target:
                source.backup(target)

    def _validate_sqlite_backup(self, backup_path: Path) -> dict[str, Any]:
        if not backup_path.exists():
            return {"quick_check": "failed", "error": "backup file does not exist"}
        try:
            with sqlite3.connect(_readonly_sqlite_uri(backup_path), uri=True) as connection:
                quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
                table_count = connection.execute(
                    "SELECT count(*) FROM sqlite_master WHERE type = 'table'"
                ).fetchone()[0]
                has_settings = (
                    connection.execute(
                        "SELECT count(*) FROM sqlite_master WHERE type = 'table' AND name = ?",
                        ("settings",),
                    ).fetchone()[0]
                    == 1
                )
            return {
                "quick_check": quick_check,
                "table_count": table_count,
                "has_settings_table": has_settings,
            }
        except sqlite3.Error as exc:
            return {"quick_check": "failed", "error": str(exc)}

    def _dump_postgres_database(self, target_path: Path, url: URL) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            "pg_dump",
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            "--file",
            str(target_path),
        ]
        command.extend(_postgres_connection_args(url))
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=900,
            env=_postgres_command_env(url),
        )
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "pg_dump failed").strip())

    def _validate_postgres_backup(self, backup_path: Path) -> dict[str, Any]:
        if not backup_path.exists():
            return {"quick_check": "failed", "error": "backup file does not exist"}
        result = subprocess.run(
            ["pg_restore", "--list", str(backup_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            return {
                "quick_check": "failed",
                "error": (result.stderr or result.stdout or "pg_restore validation failed").strip(),
            }
        entries = [line for line in result.stdout.splitlines() if line.strip()]
        return {
            "quick_check": "ok",
            "format": "pg_dump_custom",
            "entry_count": len(entries),
            "sample_entries": entries[:20],
        }

    def _validate_backup(self, backup: dict[str, Any], backup_path: Path) -> dict[str, Any]:
        if backup.get("backup_type") == "postgres_pg_dump":
            return self._validate_postgres_backup(backup_path)
        return self._validate_sqlite_backup(backup_path)

    def _table_counts(self, backup_path: Path) -> dict[str, int]:
        counts: dict[str, int] = {}
        with sqlite3.connect(_readonly_sqlite_uri(backup_path), uri=True) as connection:
            table_names = [
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
                ).fetchall()
            ]
            for table_name in table_names:
                if table_name.startswith("sqlite_"):
                    continue
                counts[table_name] = int(
                    connection.execute(f'SELECT count(*) FROM "{table_name}"').fetchone()[0]
                )
        return counts

    @staticmethod
    def _backup_relative_path(*, now, backup_id: str) -> Path:  # type: ignore[no-untyped-def]
        return (
            Path(now.strftime("%Y/%m"))
            / f"pur-leads-{now.strftime('%Y%m%dT%H%M%SZ')}-{backup_id[:8]}.sqlite3"
        )

    @staticmethod
    def _postgres_backup_relative_path(*, now, backup_id: str) -> Path:  # type: ignore[no-untyped-def]
        return (
            Path(now.strftime("%Y/%m"))
            / f"pur-leads-{now.strftime('%Y%m%dT%H%M%SZ')}-{backup_id[:8]}.dump"
        )


def backup_status_counts(session: Session) -> dict[str, int]:
    rows = session.execute(
        select(backup_runs_table.c.status, func.count())
        .group_by(backup_runs_table.c.status)
        .order_by(backup_runs_table.c.status)
    ).all()
    return {str(status): int(count) for status, count in rows if status is not None}


def restore_status_counts(session: Session) -> dict[str, int]:
    rows = session.execute(
        select(restore_runs_table.c.status, func.count())
        .group_by(restore_runs_table.c.status)
        .order_by(restore_runs_table.c.status)
    ).all()
    return {str(status): int(count) for status, count in rows if status is not None}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _readonly_sqlite_uri(path: Path) -> str:
    return f"{path.resolve().as_uri()}?mode=ro"


def _postgres_connection_args(url: URL) -> list[str]:
    args = ["--dbname", url.database or ""]
    if url.host:
        args.extend(["--host", url.host])
    if url.port:
        args.extend(["--port", str(url.port)])
    if url.username:
        args.extend(["--username", url.username])
    return args


def _postgres_command_env(url: URL) -> dict[str, str]:
    env = os.environ.copy()
    if url.password:
        env["PGPASSWORD"] = url.password
    return env


def _postgres_database_manifest(url: URL) -> dict[str, Any]:
    return {
        "driver": url.get_backend_name(),
        "host": url.host,
        "port": url.port,
        "database": url.database,
        "username": url.username,
    }
