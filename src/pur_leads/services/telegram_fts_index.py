"""SQLite FTS5 index for normalized Telegram text."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import sqlite3
from typing import Any

import pyarrow.parquet as pq
from sqlalchemy import select
from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.models.telegram_sources import telegram_raw_export_runs_table
from pur_leads.services.telegram_run_metadata import merge_raw_export_run_metadata

STAGE_NAME = "telegram_fts_index"
STAGE_VERSION = "1"

TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+", re.UNICODE)
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
RUSSIAN_STOP_WORDS = {
    "а",
    "в",
    "и",
    "или",
    "как",
    "кто",
    "на",
    "не",
    "по",
    "с",
    "у",
    "что",
    "это",
}
RUSSIAN_ENDINGS = (
    "иями",
    "ями",
    "ами",
    "ого",
    "его",
    "ому",
    "ему",
    "ыми",
    "ими",
    "ых",
    "их",
    "ая",
    "яя",
    "ое",
    "ее",
    "ые",
    "ие",
    "ый",
    "ий",
    "ой",
    "ую",
    "юю",
    "ам",
    "ям",
    "ах",
    "ях",
    "ом",
    "ем",
    "а",
    "я",
    "ы",
    "и",
    "у",
    "ю",
    "е",
    "о",
)


@dataclass(frozen=True)
class TelegramFtsIndexResult:
    raw_export_run_id: str
    search_db_path: Path
    summary_path: Path
    metrics: dict[str, Any]


class TelegramFtsIndexService:
    """Build and query a local SQLite FTS5 index from Stage 2 text parquet."""

    def __init__(self, session: Session, *, search_root: Path | str = "./data/search") -> None:
        self.session = session
        self.search_root = Path(search_root)

    def write_index(
        self,
        raw_export_run_id: str,
        *,
        texts_parquet_path: Path | str | None = None,
        rebuild: bool = True,
    ) -> TelegramFtsIndexResult:
        run = self._require_run(raw_export_run_id)
        texts_path = (
            _resolve_path(texts_parquet_path)
            if texts_parquet_path is not None
            else _texts_path_from_metadata(run)
        )
        artifact_texts_path = _artifact_texts_path_from_metadata(run)
        output_dir = (
            self.search_root
            / "telegram_texts"
            / f"source_id={run['monitored_source_id']}"
            / f"run_id={raw_export_run_id}"
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        search_db_path = output_dir / "search.sqlite3"
        summary_path = output_dir / "fts_index_summary.json"
        if rebuild and search_db_path.exists():
            search_db_path.unlink()

        sample_documents: list[dict[str, Any]] = []
        total_text_rows = 0
        total_artifact_text_rows = 0
        indexed_message_documents = 0
        indexed_artifact_documents = 0
        skipped_empty_text_rows = 0
        skipped_empty_artifact_text_rows = 0
        next_row_id = 1
        with _sqlite_fts_connection(search_db_path) as connection:
            for batch in pq.ParquetFile(texts_path).iter_batches(batch_size=5000):
                rows = batch.to_pylist()
                total_text_rows += len(rows)
                documents = _documents_from_rows(
                    rows,
                    raw_export_run_id=raw_export_run_id,
                    monitored_source_id=str(run["monitored_source_id"]),
                    start_row_id=next_row_id,
                )
                skipped_empty_text_rows += len(rows) - len(documents)
                indexed_message_documents += len(documents)
                next_row_id += len(documents)
                _extend_sample_documents(sample_documents, documents)
                _insert_sqlite_documents(connection, documents)
            if artifact_texts_path is not None and artifact_texts_path.exists():
                for batch in pq.ParquetFile(artifact_texts_path).iter_batches(batch_size=5000):
                    artifact_rows = batch.to_pylist()
                    total_artifact_text_rows += len(artifact_rows)
                    documents = _artifact_documents_from_rows(
                        artifact_rows,
                        raw_export_run_id=raw_export_run_id,
                        monitored_source_id=str(run["monitored_source_id"]),
                        start_row_id=next_row_id,
                    )
                    skipped_empty_artifact_text_rows += len(artifact_rows) - len(documents)
                    indexed_artifact_documents += len(documents)
                    next_row_id += len(documents)
                    _extend_sample_documents(sample_documents, documents)
                    _insert_sqlite_documents(connection, documents)
            connection.commit()
        metrics = {
            "total_text_rows": total_text_rows,
            "total_artifact_text_rows": total_artifact_text_rows,
            "indexed_documents": indexed_message_documents + indexed_artifact_documents,
            "indexed_message_documents": indexed_message_documents,
            "indexed_artifact_documents": indexed_artifact_documents,
            "skipped_empty_text_rows": skipped_empty_text_rows,
            "skipped_empty_artifact_text_rows": skipped_empty_artifact_text_rows,
            "index_type": "sqlite_fts5",
            "ranking": "bm25_plus_rarity",
        }
        summary = {
            "stage": STAGE_NAME,
            "stage_version": STAGE_VERSION,
            "generated_at": utc_now().isoformat(),
            "input": {
                "raw_export_run_id": raw_export_run_id,
                "monitored_source_id": run["monitored_source_id"],
                "source_ref": run["source_ref"],
                "source_kind": run["source_kind"],
                "username": run["username"],
                "texts_parquet_path": str(texts_path),
                "artifact_texts_parquet_path": (
                    str(artifact_texts_path) if artifact_texts_path is not None else None
                ),
            },
            "outputs": {
                "search_db_path": str(search_db_path),
                "summary_path": str(summary_path),
            },
            "metrics": metrics,
            "sample_documents": [
                {
                    "telegram_message_id": item["telegram_message_id"],
                    "entity_type": item["entity_type"],
                    "artifact_kind": item["artifact_kind"],
                    "clean_text": _truncate(item["clean_text"], 500),
                    "message_url": item["message_url"],
                }
                for item in sample_documents
            ],
        }
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        merge_raw_export_run_metadata(
            self.session,
            raw_export_run_id,
            key="fts_index",
            value={
                "stage": STAGE_NAME,
                "stage_version": STAGE_VERSION,
                "generated_at": summary["generated_at"],
                "texts_parquet_path": str(texts_path),
                "artifact_texts_parquet_path": (
                    str(artifact_texts_path) if artifact_texts_path is not None else None
                ),
                "search_db_path": str(search_db_path),
                "indexed_documents": indexed_message_documents + indexed_artifact_documents,
                "indexed_message_documents": indexed_message_documents,
                "indexed_artifact_documents": indexed_artifact_documents,
                "summary_path": str(summary_path),
            },
        )
        self.session.commit()
        return TelegramFtsIndexResult(
            raw_export_run_id=raw_export_run_id,
            search_db_path=search_db_path,
            summary_path=summary_path,
            metrics=metrics,
        )

    def query(
        self,
        *,
        search_db_path: Path | str,
        query_text: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        query_terms = _query_terms(query_text)
        if not query_terms:
            return []
        fts_query = " OR ".join(f"{term}*" for term in query_terms)
        with sqlite3.connect(search_db_path) as connection:
            connection.row_factory = sqlite3.Row
            matches = connection.execute(
                """
                SELECT
                    m.row_id,
                    m.raw_export_run_id,
                    m.monitored_source_id,
                    m.entity_type,
                    m.telegram_message_id,
                    m.row_index,
                    m.artifact_id,
                    m.artifact_kind,
                    m.chunk_index,
                    m.source_url,
                    m.final_url,
                    m.title,
                    m.file_name,
                    m.reply_to_message_id,
                    m.thread_id,
                    m.thread_key,
                    m.date,
                    m.message_url,
                    m.clean_text,
                    m.lemmas_text,
                    m.token_count,
                    bm25(messages_fts) AS bm25_score
                FROM messages_fts
                JOIN messages m ON m.row_id = messages_fts.rowid
                WHERE messages_fts MATCH ?
                LIMIT ?
                """,
                (fts_query, max(1, limit * 5)),
            ).fetchall()
            idf = _idf_by_term(connection, query_terms)
        ranked = []
        for row in matches:
            haystack = f"{row['clean_text']} {row['lemmas_text']}".lower()
            rarity_score = sum(weight for term, weight in idf.items() if term in haystack)
            fts_score = -float(row["bm25_score"] or 0.0)
            ranked.append(
                {
                    "raw_export_run_id": row["raw_export_run_id"],
                    "monitored_source_id": row["monitored_source_id"],
                    "entity_type": row["entity_type"],
                    "telegram_message_id": row["telegram_message_id"],
                    "row_index": row["row_index"],
                    "artifact_id": row["artifact_id"],
                    "artifact_kind": row["artifact_kind"],
                    "chunk_index": row["chunk_index"],
                    "source_url": row["source_url"],
                    "final_url": row["final_url"],
                    "title": row["title"],
                    "file_name": row["file_name"],
                    "reply_to_message_id": row["reply_to_message_id"],
                    "thread_id": row["thread_id"],
                    "thread_key": row["thread_key"],
                    "date": row["date"],
                    "message_url": row["message_url"],
                    "clean_text": row["clean_text"],
                    "token_count": row["token_count"],
                    "fts_score": fts_score,
                    "rarity_score": rarity_score,
                    "score": fts_score + rarity_score,
                }
            )
        ranked.sort(key=lambda item: item["score"], reverse=True)
        return ranked[: max(1, limit)]

    def _require_run(self, raw_export_run_id: str) -> dict[str, Any]:
        row = (
            self.session.execute(
                select(telegram_raw_export_runs_table).where(
                    telegram_raw_export_runs_table.c.id == raw_export_run_id
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise KeyError(raw_export_run_id)
        if row["status"] != "succeeded":
            raise ValueError("FTS indexing requires a succeeded raw export run")
        return dict(row)


def _documents_from_rows(
    rows: list[dict[str, Any]],
    *,
    raw_export_run_id: str,
    monitored_source_id: str,
    start_row_id: int = 1,
) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for row in rows:
        if not row.get("has_text"):
            continue
        clean_text = str(row.get("clean_text") or "").strip()
        if not clean_text:
            continue
        thread_fields = _thread_fields(row)
        documents.append(
            {
                "row_id": start_row_id + len(documents),
                "raw_export_run_id": raw_export_run_id,
                "monitored_source_id": monitored_source_id,
                "entity_type": "telegram_message",
                "telegram_message_id": int(row["telegram_message_id"]),
                "row_index": int(row["row_index"]),
                "artifact_id": "",
                "artifact_kind": "",
                "chunk_index": 0,
                "source_url": "",
                "final_url": "",
                "title": "",
                "file_name": "",
                "reply_to_message_id": thread_fields["reply_to_message_id"],
                "thread_id": thread_fields["thread_id"],
                "thread_key": thread_fields["thread_key"],
                "date": str(row.get("date") or ""),
                "message_url": str(row.get("message_url") or ""),
                "clean_text": clean_text,
                "lemmas_text": " ".join(_json_list(row.get("lemmas_json"))),
                "token_count": int(row.get("token_count") or 0),
            }
        )
    return documents


def _artifact_documents_from_rows(
    rows: list[dict[str, Any]],
    *,
    raw_export_run_id: str,
    monitored_source_id: str,
    start_row_id: int,
) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for row in rows:
        if not row.get("has_text"):
            continue
        clean_text = str(row.get("clean_text") or "").strip()
        if not clean_text:
            continue
        message_id = int(row["telegram_message_id"])
        row_id = start_row_id + len(documents)
        artifact_id = str(row.get("artifact_id") or f"artifact:{message_id}:{row_id}")
        documents.append(
            {
                "row_id": row_id,
                "raw_export_run_id": raw_export_run_id,
                "monitored_source_id": monitored_source_id,
                "entity_type": "telegram_artifact",
                "telegram_message_id": message_id,
                "row_index": 0,
                "artifact_id": artifact_id,
                "artifact_kind": str(row.get("artifact_kind") or ""),
                "chunk_index": int(row.get("chunk_index") or 0),
                "source_url": str(row.get("source_url") or ""),
                "final_url": str(row.get("final_url") or ""),
                "title": str(row.get("title") or ""),
                "file_name": str(row.get("file_name") or ""),
                "reply_to_message_id": None,
                "thread_id": "",
                "thread_key": str(message_id),
                "date": str(row.get("date") or ""),
                "message_url": str(row.get("message_url") or ""),
                "clean_text": clean_text,
                "lemmas_text": " ".join(_json_list(row.get("lemmas_json"))),
                "token_count": int(row.get("token_count") or 0),
            }
        )
    return documents


def _write_sqlite_fts(path: Path, documents: list[dict[str, Any]]) -> None:
    with _sqlite_fts_connection(path) as connection:
        _insert_sqlite_documents(connection, documents)
        connection.commit()


def _sqlite_fts_connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute(
        """
        CREATE TABLE messages (
            row_id INTEGER PRIMARY KEY,
            raw_export_run_id TEXT NOT NULL,
            monitored_source_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            telegram_message_id INTEGER NOT NULL,
            row_index INTEGER NOT NULL,
            artifact_id TEXT NOT NULL,
            artifact_kind TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            source_url TEXT NOT NULL,
            final_url TEXT NOT NULL,
            title TEXT NOT NULL,
            file_name TEXT NOT NULL,
            reply_to_message_id INTEGER,
            thread_id TEXT NOT NULL,
            thread_key TEXT NOT NULL,
            date TEXT NOT NULL,
            message_url TEXT NOT NULL,
            clean_text TEXT NOT NULL,
            lemmas_text TEXT NOT NULL,
            token_count INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE VIRTUAL TABLE messages_fts USING fts5(
            clean_text,
            lemmas_text,
            tokenize = 'unicode61'
        )
        """
    )
    return connection


def _insert_sqlite_documents(
    connection: sqlite3.Connection,
    documents: list[dict[str, Any]],
) -> None:
    if not documents:
        return
    connection.executemany(
        """
        INSERT INTO messages (
            row_id,
            raw_export_run_id,
            monitored_source_id,
            entity_type,
            telegram_message_id,
            row_index,
            artifact_id,
            artifact_kind,
            chunk_index,
            source_url,
            final_url,
            title,
            file_name,
            reply_to_message_id,
            thread_id,
            thread_key,
            date,
            message_url,
            clean_text,
            lemmas_text,
            token_count
        )
        VALUES (
            :row_id,
            :raw_export_run_id,
            :monitored_source_id,
            :entity_type,
            :telegram_message_id,
            :row_index,
            :artifact_id,
            :artifact_kind,
            :chunk_index,
            :source_url,
            :final_url,
            :title,
            :file_name,
            :reply_to_message_id,
            :thread_id,
            :thread_key,
            :date,
            :message_url,
            :clean_text,
            :lemmas_text,
            :token_count
        )
        """,
        documents,
    )
    connection.executemany(
        """
        INSERT INTO messages_fts(rowid, clean_text, lemmas_text)
        VALUES (:row_id, :clean_text, :lemmas_text)
        """,
        documents,
    )


def _extend_sample_documents(
    sample_documents: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    *,
    limit: int = 20,
) -> None:
    if len(sample_documents) >= limit:
        return
    sample_documents.extend(documents[: max(0, limit - len(sample_documents))])


def _query_terms(query_text: str) -> list[str]:
    terms: list[str] = []
    for token in TOKEN_RE.findall(query_text.lower()):
        if token in RUSSIAN_STOP_WORDS:
            continue
        if CYRILLIC_RE.search(token):
            terms.append(_russian_stem(token))
        else:
            terms.append(token)
    return sorted(set(term for term in terms if len(term) >= 2))


def _russian_stem(token: str) -> str:
    if len(token) <= 5:
        return token
    for ending in RUSSIAN_ENDINGS:
        if token.endswith(ending) and len(token) - len(ending) >= 4:
            return token[: -len(ending)]
    return token


def _idf_by_term(connection: sqlite3.Connection, terms: list[str]) -> dict[str, float]:
    total = max(1, int(connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0]))
    counts: Counter[str] = Counter()
    for term in terms:
        counts[term] = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM messages
                WHERE lower(clean_text || ' ' || lemmas_text) LIKE ?
                """,
                (f"%{term.lower()}%",),
            ).fetchone()[0]
        )
    return {term: math.log((total + 1) / (counts.get(term, 0) + 1)) + 1.0 for term in terms}


def _texts_path_from_metadata(run: dict[str, Any]) -> Path:
    metadata = dict(run["metadata_json"] or {})
    text_normalization = metadata.get("text_normalization")
    if not isinstance(text_normalization, dict):
        raise ValueError("FTS indexing requires Stage 2 text_normalization metadata")
    path_value = text_normalization.get("texts_parquet_path")
    if not path_value:
        raise ValueError("FTS indexing requires text_normalization.texts_parquet_path")
    return _resolve_path(path_value)


def _artifact_texts_path_from_metadata(run: dict[str, Any]) -> Path | None:
    metadata = dict(run["metadata_json"] or {})
    artifact_texts = metadata.get("artifact_texts")
    if not isinstance(artifact_texts, dict):
        return None
    path_value = artifact_texts.get("texts_parquet_path")
    return _resolve_path(path_value) if path_value else None


def _thread_fields(row: dict[str, Any]) -> dict[str, Any]:
    raw = _json_dict(row.get("raw_message_json"))
    message_id = int(row["telegram_message_id"])
    reply_to = raw.get("reply_to_message_id")
    thread_id = str(raw.get("thread_id") or "")
    thread_key = thread_id or (str(reply_to) if reply_to is not None else str(message_id))
    return {
        "reply_to_message_id": int(reply_to) if reply_to is not None else None,
        "thread_id": thread_id,
        "thread_key": thread_key,
    }


def _json_dict(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: Any) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 3] + "..."


def _resolve_path(value: Path | str | Any) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else Path(".") / path
