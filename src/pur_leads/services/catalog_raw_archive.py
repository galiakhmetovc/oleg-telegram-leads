"""Stage 0 materialization for catalog raw ingest data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.models.catalog import artifacts_table, parsed_chunks_table, sources_table
from pur_leads.models.telegram_sources import monitored_sources_table, source_messages_table

CATALOG_SOURCE_PURPOSES = ("catalog_ingestion", "both")
ARCHIVE_VERSION = "catalog_raw_stage0_v1"


@dataclass(frozen=True)
class CatalogRawArchiveResult:
    run_id: str
    output_dir: Path
    files: dict[str, Path]
    row_counts: dict[str, int]
    monitored_source_ids: list[str]
    raw_source_ids: list[str]
    created_at: datetime

    def as_jsonable(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "output_dir": str(self.output_dir),
            "files": {name: str(path) for name, path in self.files.items()},
            "row_counts": self.row_counts,
            "monitored_source_ids": self.monitored_source_ids,
            "raw_source_ids": self.raw_source_ids,
            "created_at": self.created_at.isoformat(),
        }


class CatalogRawArchiveService:
    """Write the current raw catalog ingest state to parquet before NLP/LLM stages."""

    def __init__(self, session: Session, *, archive_root: Path | str = "./data/archive") -> None:
        self.session = session
        self.archive_root = Path(archive_root)

    def write_stage0_archive(
        self,
        *,
        monitored_source_id: str | None = None,
        run_id: str | None = None,
    ) -> CatalogRawArchiveResult:
        archive_run_id = run_id or new_id()
        created_at = utc_now()
        monitored_source_ids = self._monitored_source_ids(monitored_source_id)
        raw_source_ids = self._raw_source_ids(monitored_source_ids)
        output_dir = (
            self.archive_root
            / "catalog_raw"
            / f"dt={created_at.date().isoformat()}"
            / f"run_id={archive_run_id}"
        )
        output_dir.mkdir(parents=True, exist_ok=False)

        datasets = {
            "monitored_sources": self._rows(
                monitored_sources_table,
                monitored_sources_table.c.id.in_(monitored_source_ids),
                order_by=[monitored_sources_table.c.id],
            ),
            "source_messages": self._rows(
                source_messages_table,
                source_messages_table.c.monitored_source_id.in_(monitored_source_ids),
                order_by=[
                    source_messages_table.c.message_date,
                    source_messages_table.c.telegram_message_id,
                ],
            ),
            "sources": self._rows(
                sources_table,
                sources_table.c.id.in_(raw_source_ids),
                order_by=[sources_table.c.origin, sources_table.c.external_id],
            ),
            "artifacts": self._rows(
                artifacts_table,
                artifacts_table.c.source_id.in_(raw_source_ids),
                order_by=[artifacts_table.c.source_id, artifacts_table.c.file_name],
            ),
            "parsed_chunks": self._rows(
                parsed_chunks_table,
                parsed_chunks_table.c.source_id.in_(raw_source_ids),
                order_by=[
                    parsed_chunks_table.c.source_id,
                    parsed_chunks_table.c.artifact_id,
                    parsed_chunks_table.c.chunk_index,
                ],
            ),
        }

        files: dict[str, Path] = {}
        row_counts: dict[str, int] = {}
        for dataset, rows in datasets.items():
            table = _table_for_dataset(dataset)
            file_path = output_dir / f"{dataset}.parquet"
            _write_parquet(rows, table, file_path)
            files[dataset] = file_path
            row_counts[dataset] = len(rows)

        manifest = {
            "archive_version": ARCHIVE_VERSION,
            "run_id": archive_run_id,
            "created_at": created_at.isoformat(),
            "scope": {"monitored_source_id": monitored_source_id},
            "monitored_source_ids": monitored_source_ids,
            "raw_source_ids": raw_source_ids,
            "row_counts": row_counts,
            "files": [
                {
                    "dataset": dataset,
                    "path": path.name,
                    "rows": row_counts[dataset],
                    "size_bytes": path.stat().st_size,
                    "compression": "zstd",
                }
                for dataset, path in files.items()
            ],
        }
        (output_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        if monitored_source_ids:
            self.session.execute(
                update(source_messages_table)
                .where(source_messages_table.c.monitored_source_id.in_(monitored_source_ids))
                .values(archive_pointer_id=archive_run_id, updated_at=created_at)
            )
            self.session.commit()

        return CatalogRawArchiveResult(
            run_id=archive_run_id,
            output_dir=output_dir,
            files=files,
            row_counts=row_counts,
            monitored_source_ids=monitored_source_ids,
            raw_source_ids=raw_source_ids,
            created_at=created_at,
        )

    def _monitored_source_ids(self, monitored_source_id: str | None) -> list[str]:
        query = select(monitored_sources_table.c.id)
        if monitored_source_id is not None:
            query = query.where(monitored_sources_table.c.id == monitored_source_id)
        else:
            query = query.where(
                monitored_sources_table.c.source_purpose.in_(CATALOG_SOURCE_PURPOSES)
            )
        return [str(row) for row in self.session.execute(query.order_by(monitored_sources_table.c.id)).scalars()]

    def _raw_source_ids(self, monitored_source_ids: list[str]) -> list[str]:
        if not monitored_source_ids:
            return []
        rows = (
            self.session.execute(
                select(source_messages_table.c.raw_source_id)
                .where(source_messages_table.c.monitored_source_id.in_(monitored_source_ids))
                .where(source_messages_table.c.raw_source_id.is_not(None))
                .distinct()
                .order_by(source_messages_table.c.raw_source_id)
            )
            .scalars()
            .all()
        )
        return [str(row) for row in rows if row is not None]

    def _rows(self, table: Any, condition: Any, *, order_by: list[Any]) -> list[dict[str, Any]]:
        rows = (
            self.session.execute(select(table).where(condition).order_by(*order_by))
            .mappings()
            .all()
        )
        return [_archive_row(dict(row), table) for row in rows]


def _write_parquet(rows: list[dict[str, Any]], table: Any, file_path: Path) -> None:
    column_names = [column.name for column in table.c]
    if rows:
        arrow_table = pa.Table.from_pylist(rows)
    else:
        arrow_table = pa.table({name: pa.array([], type=pa.string()) for name in column_names})
    arrow_table = arrow_table.select([name for name in column_names if name in arrow_table.column_names])
    pq.write_table(arrow_table, file_path, compression="zstd")


def _archive_row(row: dict[str, Any], table: Any) -> dict[str, Any]:
    json_columns = {
        column.name for column in table.c if column.name.endswith("_json") or column.name == "extra"
    }
    archived: dict[str, Any] = {}
    for key, value in row.items():
        if key in json_columns:
            archived[key] = _json_string(value)
        elif isinstance(value, datetime | date):
            archived[key] = value.isoformat()
        else:
            archived[key] = value
    return archived


def _json_string(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=_json_default)


def _json_default(value: Any) -> str:
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)


def _table_for_dataset(dataset: str) -> Any:
    return {
        "monitored_sources": monitored_sources_table,
        "source_messages": source_messages_table,
        "sources": sources_table,
        "artifacts": artifacts_table,
        "parsed_chunks": parsed_chunks_table,
    }[dataset]
