"""Inventory generated pipeline artifacts from run metadata."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

import pyarrow.parquet as pq
from sqlalchemy import select
from sqlalchemy.orm import Session

from pur_leads.models.telegram_sources import telegram_raw_export_runs_table

RAW_EXPORT_PATH_FIELDS = (
    "output_dir",
    "result_json_path",
    "messages_jsonl_path",
    "attachments_jsonl_path",
    "messages_parquet_path",
    "attachments_parquet_path",
    "manifest_path",
)
PREVIEWABLE_KINDS = {"json", "jsonl", "txt", "csv", "md", "log"}
TABLE_PREVIEW_ROWS = 20
TABLE_PREVIEW_COLUMNS = 30
SQLITE_PREVIEW_TABLES = 50
JSONL_PREVIEW_RECORDS = 20
DISCOVERY_MAX_FILES_PER_ROOT = 2_000
DISCOVERY_MAX_TOTAL_FILES = 10_000


@dataclass(frozen=True)
class ArtifactRecord:
    id: str
    raw_export_run_id: str
    monitored_source_id: str
    source_ref: str
    source_kind: str
    username: str | None
    title: str | None
    run_status: str
    run_created_at: datetime
    stage: str
    key: str
    path: str
    kind: str
    exists: bool
    is_dir: bool
    size_bytes: int | None
    modified_at: datetime | None
    metadata_json: dict[str, Any]

    def as_jsonable(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "raw_export_run_id": self.raw_export_run_id,
            "monitored_source_id": self.monitored_source_id,
            "source_ref": self.source_ref,
            "source_kind": self.source_kind,
            "username": self.username,
            "title": self.title,
            "run_status": self.run_status,
            "run_created_at": self.run_created_at.isoformat(),
            "stage": self.stage,
            "key": self.key,
            "path": self.path,
            "kind": self.kind,
            "exists": self.exists,
            "is_dir": self.is_dir,
            "size_bytes": self.size_bytes,
            "modified_at": self.modified_at.isoformat() if self.modified_at else None,
            "metadata_json": self.metadata_json,
        }


class ArtifactInventoryService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_artifacts(
        self,
        *,
        stage: str | None = None,
        kind: str | None = None,
        exists: bool | None = None,
        query: str | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        artifacts = self._artifacts()
        if stage:
            artifacts = [item for item in artifacts if item.stage == stage]
        if kind:
            artifacts = [item for item in artifacts if item.kind == kind]
        if exists is not None:
            artifacts = [item for item in artifacts if item.exists is exists]
        if query:
            normalized = query.casefold()
            artifacts = [
                item
                for item in artifacts
                if normalized in item.path.casefold()
                or normalized in item.key.casefold()
                or normalized in item.stage.casefold()
                or normalized in (item.title or "").casefold()
                or normalized in (item.username or "").casefold()
            ]
        artifacts = artifacts[: max(1, min(limit, 2000))]
        return {
            "summary": _summary(artifacts),
            "stages": sorted({item.stage for item in artifacts}),
            "kinds": sorted({item.kind for item in artifacts}),
            "items": [item.as_jsonable() for item in artifacts],
        }

    def get_artifact(self, artifact_id: str, *, max_preview_chars: int = 500_000) -> dict[str, Any]:
        for artifact in self._artifacts():
            if artifact.id != artifact_id:
                continue
            return {
                "artifact": artifact.as_jsonable(),
                "preview": _preview(Path(artifact.path), artifact.kind, max_preview_chars),
            }
        raise KeyError(artifact_id)

    def _artifacts(self) -> list[ArtifactRecord]:
        rows = (
            self.session.execute(
                select(telegram_raw_export_runs_table).order_by(
                    telegram_raw_export_runs_table.c.created_at.desc()
                )
            )
            .mappings()
            .all()
        )
        artifacts: list[ArtifactRecord] = []
        seen: set[str] = set()
        discovered_count = 0
        for row in rows:
            run = dict(row)
            for key in RAW_EXPORT_PATH_FIELDS:
                _append_artifact(
                    artifacts,
                    seen,
                    run=run,
                    stage="raw_export",
                    key=key,
                    path_value=run.get(key),
                    metadata={"source": "telegram_raw_export_runs"},
                )
            metadata = run.get("metadata_json")
            if isinstance(metadata, dict):
                for stage, value in metadata.items():
                    _collect_metadata_paths(
                        artifacts,
                        seen,
                        run=run,
                        stage=str(stage),
                        value=value,
                        key_prefix="",
                    )
            registered_paths = {item.path for item in artifacts if item.raw_export_run_id == str(run["id"])}
            discovery_roots = [
                (item.stage, Path(item.path))
                for item in artifacts
                if item.raw_export_run_id == str(run["id"]) and item.exists and item.is_dir
            ]
            for stage, root in discovery_roots:
                discovered_count += _append_discovered_files(
                    artifacts,
                    seen,
                    registered_paths,
                    run=run,
                    stage=stage,
                    root=root,
                    max_total=max(0, DISCOVERY_MAX_TOTAL_FILES - discovered_count),
                )
                if discovered_count >= DISCOVERY_MAX_TOTAL_FILES:
                    break
        return artifacts


def _collect_metadata_paths(
    artifacts: list[ArtifactRecord],
    seen: set[str],
    *,
    run: dict[str, Any],
    stage: str,
    value: Any,
    key_prefix: str,
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_key = f"{key_prefix}.{key}" if key_prefix else str(key)
            _collect_metadata_paths(
                artifacts,
                seen,
                run=run,
                stage=stage,
                value=child,
                key_prefix=child_key,
            )
        return
    if isinstance(value, list):
        if _looks_like_path_key(key_prefix):
            for index, item in enumerate(value):
                _append_artifact(
                    artifacts,
                    seen,
                    run=run,
                    stage=stage,
                    key=f"{key_prefix}[{index}]",
                    path_value=item,
                    metadata={"source": "metadata_json"},
                )
        return
    if _looks_like_path_key(key_prefix):
        _append_artifact(
            artifacts,
            seen,
            run=run,
            stage=stage,
            key=key_prefix,
            path_value=value,
            metadata={"source": "metadata_json"},
        )


def _append_artifact(
    artifacts: list[ArtifactRecord],
    seen: set[str],
    *,
    run: dict[str, Any],
    stage: str,
    key: str,
    path_value: Any,
    metadata: dict[str, Any],
) -> ArtifactRecord | None:
    if not isinstance(path_value, str) or not path_value.strip():
        return None
    path = _resolve_path(path_value)
    unique_key = f"{run['id']}|{stage}|{key}|{path}"
    if unique_key in seen:
        return None
    seen.add(unique_key)
    exists = path.exists()
    is_dir = path.is_dir() if exists else False
    stat = path.stat() if exists else None
    kind = _artifact_kind(path, is_dir=is_dir)
    artifact = ArtifactRecord(
        id=hashlib.sha256(unique_key.encode("utf-8")).hexdigest()[:24],
        raw_export_run_id=str(run["id"]),
        monitored_source_id=str(run["monitored_source_id"]),
        source_ref=str(run["source_ref"]),
        source_kind=str(run["source_kind"]),
        username=run.get("username"),
        title=run.get("title"),
        run_status=str(run["status"]),
        run_created_at=run["created_at"],
        stage=stage,
        key=key,
        path=str(path),
        kind=kind,
        exists=exists,
        is_dir=is_dir,
        size_bytes=None if is_dir or stat is None else int(stat.st_size),
        modified_at=(
            datetime.fromtimestamp(stat.st_mtime).astimezone() if stat is not None else None
        ),
        metadata_json=metadata,
    )
    artifacts.append(artifact)
    return artifact


def _append_discovered_files(
    artifacts: list[ArtifactRecord],
    seen: set[str],
    registered_paths: set[str],
    *,
    run: dict[str, Any],
    stage: str,
    root: Path,
    max_total: int,
) -> int:
    if max_total <= 0:
        return 0
    appended = 0
    for path in sorted(root.rglob("*")):
        if appended >= min(DISCOVERY_MAX_FILES_PER_ROOT, max_total):
            break
        if not path.is_file():
            continue
        resolved = str(path)
        if resolved in registered_paths:
            continue
        artifact = _append_artifact(
            artifacts,
            seen,
            run=run,
            stage=stage,
            key=str(path.relative_to(root)),
            path_value=resolved,
            metadata={"source": "filesystem_discovery"},
        )
        if artifact is None:
            continue
        registered_paths.add(artifact.path)
        appended += 1
    return appended


def _preview(path: Path, kind: str, max_preview_chars: int) -> dict[str, Any]:
    if not path.exists():
        return {"available": False, "reason": "missing", "text": "", "truncated": False}
    if path.is_dir():
        children = sorted(child.name for child in path.iterdir())[:200]
        return {
            "available": True,
            "kind": "directory",
            "text": "\n".join(children),
            "truncated": len(children) == 200,
        }
    if kind == "parquet":
        return _preview_parquet(path)
    if kind == "sqlite":
        return _preview_sqlite(path)
    if kind not in PREVIEWABLE_KINDS:
        return {
            "available": False,
            "reason": f"{kind} preview is not supported",
            "text": "",
            "truncated": False,
        }
    max_chars = max(1_000, min(max_preview_chars, 2_000_000))
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        text = handle.read(max_chars + 1)
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]
    if kind == "json" and not truncated:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            pass
        else:
            text = json.dumps(parsed, ensure_ascii=False, indent=2, sort_keys=True)
    preview = {"available": True, "kind": kind, "text": text, "truncated": truncated}
    if kind == "jsonl":
        records = _parse_jsonl_records(text)
        preview["records"] = records
        preview["records_previewed"] = len(records)
    return preview


def _preview_parquet(path: Path) -> dict[str, Any]:
    parquet_file = pq.ParquetFile(path)
    schema = parquet_file.schema_arrow
    selected_names = schema.names[:TABLE_PREVIEW_COLUMNS]
    rows: list[dict[str, Any]] = []
    for batch in parquet_file.iter_batches(
        batch_size=TABLE_PREVIEW_ROWS,
        columns=selected_names,
        use_threads=False,
    ):
        rows = [_json_safe(row) for row in batch.to_pylist()]
        break
    columns = [
        {"name": field.name, "type": str(field.type)}
        for field in schema
    ]
    text_lines = [
        f"rows: {parquet_file.metadata.num_rows}",
        f"row_groups: {parquet_file.metadata.num_row_groups}",
        "schema:",
        *[f"{column['name']}: {column['type']}" for column in columns],
    ]
    if rows:
        text_lines.extend(["", "sample:", json.dumps(rows, ensure_ascii=False, indent=2)])
    return {
        "available": True,
        "kind": "parquet",
        "text": "\n".join(text_lines),
        "truncated": parquet_file.metadata.num_rows > len(rows),
        "row_count": parquet_file.metadata.num_rows,
        "row_group_count": parquet_file.metadata.num_row_groups,
        "columns": columns,
        "rows": rows,
    }


def _preview_sqlite(path: Path) -> dict[str, Any]:
    tables: list[dict[str, Any]] = []
    sample: dict[str, Any] | None = None
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        table_names = [
            str(row["name"])
            for row in connection.execute(
                """
                select name
                from sqlite_master
                where type = 'table' and name not like 'sqlite_%'
                order by name
                limit ?
                """,
                (SQLITE_PREVIEW_TABLES,),
            ).fetchall()
        ]
        for table_name in table_names:
            quoted = _quote_sqlite_identifier(table_name)
            try:
                row_count = connection.execute(f"select count(*) from {quoted}").fetchone()[0]
            except sqlite3.DatabaseError:
                row_count = None
            tables.append({"name": table_name, "row_count": row_count})
        if table_names:
            table_name = table_names[0]
            quoted = _quote_sqlite_identifier(table_name)
            cursor = connection.execute(f"select * from {quoted} limit ?", (TABLE_PREVIEW_ROWS,))
            rows = [_json_safe(dict(row)) for row in cursor.fetchall()]
            sample = {
                "table": table_name,
                "columns": [description[0] for description in cursor.description or []],
                "rows": rows,
            }
    text_lines = [f"{table['name']}: {table['row_count']} rows" for table in tables]
    if sample:
        text_lines.extend(["", f"sample: {sample['table']}", json.dumps(sample["rows"], ensure_ascii=False, indent=2)])
    return {
        "available": True,
        "kind": "sqlite",
        "text": "\n".join(text_lines),
        "truncated": len(tables) == SQLITE_PREVIEW_TABLES,
        "tables": tables,
        "sample": sample,
    }


def _quote_sqlite_identifier(value: str) -> str:
    return f'"{value.replace(chr(34), chr(34) * 2)}"'


def _parse_jsonl_records(text: str) -> list[Any]:
    records: list[Any] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        records.append(_json_safe(parsed))
        if len(records) >= JSONL_PREVIEW_RECORDS:
            break
    return records


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_json_safe(child) for child in value]
    if isinstance(value, tuple):
        return [_json_safe(child) for child in value]
    if isinstance(value, bytes):
        return f"<bytes {len(value)}>"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _summary(artifacts: list[ArtifactRecord]) -> dict[str, Any]:
    return {
        "run_count": len({item.raw_export_run_id for item in artifacts}),
        "artifact_count": len(artifacts),
        "existing_count": sum(1 for item in artifacts if item.exists),
        "missing_count": sum(1 for item in artifacts if not item.exists),
        "total_file_size_bytes": sum(item.size_bytes or 0 for item in artifacts),
        "by_stage": _count_by(artifacts, "stage"),
        "by_kind": _count_by(artifacts, "kind"),
    }


def _count_by(artifacts: list[ArtifactRecord], field: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in artifacts:
        key = str(getattr(item, field))
        result[key] = result.get(key, 0) + 1
    return result


def _looks_like_path_key(key: str) -> bool:
    lowered = key.casefold()
    return lowered.endswith("_path") or lowered.endswith("_paths") or lowered.endswith(".path")


def _artifact_kind(path: Path, *, is_dir: bool) -> str:
    if is_dir:
        return "directory"
    suffix = path.suffix.casefold().lstrip(".")
    if suffix in {"json", "jsonl", "parquet", "sqlite", "sqlite3", "db", "csv", "txt", "md", "log"}:
        return "sqlite" if suffix in {"sqlite3", "db"} else suffix
    return suffix or "file"


def _resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else Path(".") / path
