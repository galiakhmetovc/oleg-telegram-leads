"""Telegram artifact text extraction over immutable raw exports."""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Protocol

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import select
from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.integrations.catalog.external_page import HttpExternalPageFetcher
from pur_leads.integrations.documents.pdf_parser import PdfArtifactParser
from pur_leads.models.telegram_sources import telegram_raw_export_runs_table
from pur_leads.services.telegram_run_metadata import merge_raw_export_run_metadata
from pur_leads.services.telegram_text_normalization import TelegramTextNormalizationService

STAGE_NAME = "telegram_artifact_text_extraction"
STAGE_VERSION = "1"

HTTP_URL_RE = re.compile(r"https?://[^\s<>()\"']+", re.IGNORECASE)
SUPPORTED_DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".xml",
    ".html",
    ".htm",
}
SUPPORTED_DOCUMENT_MIME_TYPES = {
    "application/pdf",
    "application/json",
    "application/xml",
    "application/csv",
    "text/csv",
}


class ExternalPageFetcher(Protocol):
    async def fetch_page(self, *, url: str, payload: dict[str, Any]) -> Any: ...


class DocumentParser(Protocol):
    async def parse_artifact(
        self,
        *,
        source_id: str,
        artifact_id: str | None,
        payload: dict[str, Any],
    ) -> Any: ...


@dataclass(frozen=True)
class TelegramArtifactTextExtractionResult:
    raw_export_run_id: str
    output_dir: Path
    texts_parquet_path: Path
    summary_path: Path
    metrics: dict[str, Any]


class TelegramArtifactTextExtractionService:
    """Extract reusable text rows from Telegram-linked pages and downloaded documents."""

    def __init__(
        self,
        session: Session,
        *,
        processed_root: Path | str = "./data/processed",
        external_page_fetcher: ExternalPageFetcher | None = None,
        document_parser: DocumentParser | None = None,
        fetch_external_pages: bool = True,
        parse_documents: bool = True,
        external_fetch_concurrency: int = 4,
        document_parse_concurrency: int = 4,
        external_fetch_timeout_seconds: float = 600.0,
        document_parse_timeout_seconds: float = 600.0,
    ) -> None:
        self.session = session
        self.processed_root = Path(processed_root)
        self.external_page_fetcher = external_page_fetcher or HttpExternalPageFetcher()
        self.document_parser = document_parser or PdfArtifactParser()
        self.fetch_external_pages = fetch_external_pages
        self.parse_documents = parse_documents
        self.external_fetch_concurrency = max(1, int(external_fetch_concurrency))
        self.document_parse_concurrency = max(1, int(document_parse_concurrency))
        self.external_fetch_timeout_seconds = max(0.001, float(external_fetch_timeout_seconds))
        self.document_parse_timeout_seconds = max(0.001, float(document_parse_timeout_seconds))
        self._normalizer = TelegramTextNormalizationService(
            session,
            processed_root=processed_root,
        )

    def write_texts(self, raw_export_run_id: str) -> TelegramArtifactTextExtractionResult:
        run = self._require_run(raw_export_run_id)
        messages_path = _resolve_path(run["messages_parquet_path"])
        attachments_path = _resolve_path(run["attachments_parquet_path"])
        message_rows = pq.ParquetFile(messages_path).read().to_pylist()
        attachment_rows = (
            pq.ParquetFile(attachments_path).read().to_pylist()
            if attachments_path.exists()
            else []
        )

        output_dir = (
            self.processed_root
            / "telegram_artifact_texts"
            / f"source_id={run['monitored_source_id']}"
            / f"run_id={raw_export_run_id}"
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        texts_parquet_path = output_dir / "artifact_texts.parquet"
        summary_path = output_dir / "artifact_texts_summary.json"

        candidates = _candidate_counts(message_rows, attachment_rows)
        artifact_rows = asyncio.run(
            self._extract_rows(
                run=run,
                message_rows=message_rows,
                attachment_rows=attachment_rows,
            )
        )
        _write_artifact_texts_parquet(texts_parquet_path, artifact_rows)
        metrics = _metrics(artifact_rows, candidates=candidates)
        metrics.update(
            {
                "external_fetch_concurrency": self.external_fetch_concurrency,
                "document_parse_concurrency": self.document_parse_concurrency,
                "external_fetch_timeout_seconds": self.external_fetch_timeout_seconds,
                "document_parse_timeout_seconds": self.document_parse_timeout_seconds,
            }
        )
        summary = _summary_payload(
            run=run,
            raw_export_run_id=raw_export_run_id,
            messages_path=messages_path,
            attachments_path=attachments_path,
            texts_parquet_path=texts_parquet_path,
            summary_path=summary_path,
            rows=artifact_rows,
            metrics=metrics,
        )
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        merge_raw_export_run_metadata(
            self.session,
            raw_export_run_id,
            key="artifact_texts",
            value={
                "stage": STAGE_NAME,
                "stage_version": STAGE_VERSION,
                "generated_at": summary["generated_at"],
                "texts_parquet_path": str(texts_parquet_path),
                "summary_path": str(summary_path),
                "total_rows": metrics["total_rows"],
                "extracted_rows": metrics["extracted_rows"],
                "rows_with_text": metrics["rows_with_text"],
            },
        )
        self.session.commit()
        return TelegramArtifactTextExtractionResult(
            raw_export_run_id=raw_export_run_id,
            output_dir=output_dir,
            texts_parquet_path=texts_parquet_path,
            summary_path=summary_path,
            metrics=metrics,
        )

    async def _extract_rows(
        self,
        *,
        run: dict[str, Any],
        message_rows: list[dict[str, Any]],
        attachment_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if self.fetch_external_pages:
            page_candidates = _external_url_candidates(message_rows)
            rows.extend(
                await self._extract_candidate_batch(
                    candidates=page_candidates,
                    concurrency=self.external_fetch_concurrency,
                    extractor=lambda candidate: self._extract_external_page_rows(
                        run=run,
                        candidate=candidate,
                    ),
                )
            )
        if self.parse_documents:
            message_rows_by_id = {
                int(row["telegram_message_id"]): row for row in message_rows
            }
            document_candidates = _document_candidates(attachment_rows, message_rows_by_id)
            rows.extend(
                await self._extract_candidate_batch(
                    candidates=document_candidates,
                    concurrency=self.document_parse_concurrency,
                    extractor=lambda candidate: self._extract_document_rows(
                        run=run,
                        candidate=candidate,
                    ),
                )
            )
        return rows

    async def _extract_candidate_batch(
        self,
        *,
        candidates: list[dict[str, Any]],
        concurrency: int,
        extractor: Any,
    ) -> list[dict[str, Any]]:
        if not candidates:
            return []
        semaphore = asyncio.Semaphore(max(1, concurrency))

        async def guarded(candidate: dict[str, Any]) -> list[dict[str, Any]]:
            async with semaphore:
                return await extractor(candidate)

        nested = await asyncio.gather(*(guarded(candidate) for candidate in candidates))
        return [row for rows in nested for row in rows]

    async def _extract_external_page_rows(
        self,
        *,
        run: dict[str, Any],
        candidate: dict[str, Any],
    ) -> list[dict[str, Any]]:
        url = str(candidate["source_url"])
        artifact_id = _artifact_id("external_page", candidate["telegram_message_id"], url)
        try:
            page = await asyncio.wait_for(
                self.external_page_fetcher.fetch_page(
                    url=url,
                    payload={
                        "raw_export_run_id": run["id"],
                        "monitored_source_id": run["monitored_source_id"],
                        "telegram_message_id": candidate["telegram_message_id"],
                        "message_url": candidate["message_url"],
                    },
                ),
                timeout=self.external_fetch_timeout_seconds,
            )
        except Exception as exc:
            return [
                self._row(
                    run=run,
                    candidate=candidate,
                    artifact_id=artifact_id,
                    artifact_kind="external_page",
                    raw_text="",
                    extraction_status="failed",
                    extraction_error=str(exc) or exc.__class__.__name__,
                    source_url=url,
                    raw_artifact={
                        "source_url": url,
                        "error_type": exc.__class__.__name__,
                    },
                )
            ]

        raw_text = str(getattr(page, "text", "") or "")
        return [
            self._row(
                run=run,
                candidate=candidate,
                artifact_id=artifact_id,
                artifact_kind="external_page",
                raw_text=raw_text,
                extraction_status="extracted" if raw_text.strip() else "empty_text",
                extraction_error=None,
                source_url=url,
                final_url=str(getattr(page, "final_url", "") or url),
                title=getattr(page, "title", None),
                parser_name="readable-html",
                parser_version="1",
                raw_artifact={
                    "source_url": url,
                    "final_url": str(getattr(page, "final_url", "") or url),
                    "title": getattr(page, "title", None),
                    "status_code": getattr(page, "status_code", None),
                    "content_type": getattr(page, "content_type", None),
                },
            )
        ]

    async def _extract_document_rows(
        self,
        *,
        run: dict[str, Any],
        candidate: dict[str, Any],
    ) -> list[dict[str, Any]]:
        local_path = _resolve_optional_local_path(candidate.get("local_path"), run=run)
        artifact_id = _artifact_id(
            "document",
            candidate["telegram_message_id"],
            str(candidate.get("file_name") or candidate.get("source_url") or ""),
        )
        if local_path is None or not local_path.exists():
            return [
                self._row(
                    run=run,
                    candidate=candidate,
                    artifact_id=artifact_id,
                    artifact_kind="document",
                    raw_text="",
                    extraction_status="missing_file",
                    extraction_error="downloaded file is not available on disk",
                    file_name=candidate.get("file_name"),
                    mime_type=candidate.get("mime_type"),
                    file_size=candidate.get("file_size"),
                    source_url=candidate.get("source_url"),
                    raw_artifact=candidate.get("raw_artifact") or {},
                )
            ]

        try:
            parsed = await asyncio.wait_for(
                self.document_parser.parse_artifact(
                    source_id=str(run["monitored_source_id"]),
                    artifact_id=artifact_id,
                    payload={
                        "local_path": str(local_path),
                        "file_name": candidate.get("file_name"),
                        "mime_type": candidate.get("mime_type"),
                        "file_size": candidate.get("file_size"),
                        "raw_attachment_json": candidate.get("raw_artifact"),
                    },
                ),
                timeout=self.document_parse_timeout_seconds,
            )
        except Exception as exc:
            return [
                self._row(
                    run=run,
                    candidate=candidate,
                    artifact_id=artifact_id,
                    artifact_kind="document",
                    raw_text="",
                    extraction_status="failed",
                    extraction_error=str(exc) or exc.__class__.__name__,
                    file_name=candidate.get("file_name"),
                    mime_type=candidate.get("mime_type"),
                    file_size=candidate.get("file_size"),
                    source_url=candidate.get("source_url"),
                    raw_artifact={
                        "raw_attachment_json": candidate.get("raw_artifact") or {},
                        "error_type": exc.__class__.__name__,
                    },
                )
            ]

        rows: list[dict[str, Any]] = []
        chunks = list(getattr(parsed, "chunks", []) or [])
        if not chunks:
            rows.append(
                self._row(
                    run=run,
                    candidate=candidate,
                    artifact_id=artifact_id,
                    artifact_kind="document",
                    raw_text="",
                    extraction_status="empty_text",
                    extraction_error=None,
                    file_name=candidate.get("file_name"),
                    mime_type=candidate.get("mime_type"),
                    file_size=candidate.get("file_size"),
                    source_url=candidate.get("source_url"),
                    parser_name=getattr(parsed, "parser_name", None),
                    parser_version=getattr(parsed, "parser_version", None),
                    raw_artifact=candidate.get("raw_artifact") or {},
                )
            )
            return rows
        for chunk_index, chunk in enumerate(chunks):
            rows.append(
                self._row(
                    run=run,
                    candidate=candidate,
                    artifact_id=artifact_id,
                    artifact_kind="document",
                    chunk_index=chunk_index,
                    raw_text=str(chunk),
                    extraction_status="extracted",
                    extraction_error=None,
                    file_name=candidate.get("file_name"),
                    mime_type=candidate.get("mime_type"),
                    file_size=candidate.get("file_size"),
                    source_url=candidate.get("source_url"),
                    parser_name=getattr(parsed, "parser_name", None),
                    parser_version=getattr(parsed, "parser_version", None),
                    raw_artifact=candidate.get("raw_artifact") or {},
                )
            )
        return rows

    def _row(
        self,
        *,
        run: dict[str, Any],
        candidate: dict[str, Any],
        artifact_id: str,
        artifact_kind: str,
        raw_text: str,
        extraction_status: str,
        extraction_error: str | None,
        chunk_index: int = 0,
        source_url: Any = None,
        final_url: str | None = None,
        title: str | None = None,
        file_name: Any = None,
        mime_type: Any = None,
        file_size: Any = None,
        parser_name: str | None = None,
        parser_version: str | None = None,
        raw_artifact: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized = self._normalizer._normalize_text(raw_text)
        raw = raw_artifact or {}
        return {
            "export_run_id": run["id"],
            "monitored_source_id": run["monitored_source_id"],
            "telegram_message_id": int(candidate["telegram_message_id"]),
            "artifact_id": artifact_id,
            "artifact_kind": artifact_kind,
            "chunk_index": int(chunk_index),
            "source_url": str(source_url or ""),
            "final_url": final_url or "",
            "title": title or "",
            "file_name": str(file_name or ""),
            "mime_type": str(mime_type or ""),
            "file_size": _nullable_int(file_size),
            "date": str(candidate.get("date") or ""),
            "message_url": str(candidate.get("message_url") or ""),
            "raw_text": normalized.raw_text,
            "clean_text": normalized.clean_text,
            "normalization_lang": normalized.lang,
            "tokens_json": _json_string(normalized.tokens),
            "lemmas_json": _json_string(normalized.lemmas),
            "pos_tags_json": _json_string(normalized.pos_tags),
            "token_map_json": _json_string(normalized.token_map),
            "token_count": len(normalized.tokens),
            "has_text": bool(normalized.raw_text.strip()),
            "normalization_status": normalized.status,
            "normalization_error": normalized.error,
            "extraction_status": extraction_status,
            "extraction_error": extraction_error,
            "parser_name": parser_name or "",
            "parser_version": parser_version or "",
            "raw_artifact_json": _json_string(raw),
        }

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
            raise ValueError("artifact text extraction requires a succeeded raw export run")
        return dict(row)


def _external_url_candidates(message_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[int, str]] = set()
    candidates: list[dict[str, Any]] = []
    for row in message_rows:
        message_id = int(row["telegram_message_id"])
        for url in _urls_from_message_row(row):
            normalized_url = _normalize_url(url)
            key = (message_id, normalized_url)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                {
                    "telegram_message_id": message_id,
                    "date": row.get("date"),
                    "message_url": row.get("message_url"),
                    "source_url": normalized_url,
                    "raw_artifact": {"source_url": normalized_url},
                }
            )
    return candidates


def _document_candidates(
    attachment_rows: list[dict[str, Any]],
    message_rows_by_id: dict[int, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in attachment_rows:
        if not _is_supported_document(row):
            continue
        message_row = (message_rows_by_id or {}).get(int(row["telegram_message_id"]), {})
        raw = _json_dict(row.get("raw_attachment_json"))
        download = raw.get("raw_export_download") if isinstance(raw.get("raw_export_download"), dict) else {}
        media_ref = raw.get("telegram_media_ref") if isinstance(raw.get("telegram_media_ref"), dict) else {}
        candidates.append(
            {
                "telegram_message_id": int(row["telegram_message_id"]),
                "date": row.get("date") or message_row.get("date") or "",
                "message_url": row.get("message_url") or media_ref.get("message_url"),
                "source_url": _media_source_url(row, raw),
                "file_name": row.get("file_name"),
                "mime_type": row.get("mime_type"),
                "file_size": row.get("file_size"),
                "local_path": download.get("local_path"),
                "raw_artifact": raw,
            }
        )
    return candidates


def _urls_from_message_row(row: dict[str, Any]) -> list[str]:
    text_parts = [
        str(row.get("text_plain") or ""),
        str(row.get("caption") or ""),
    ]
    raw = _json_dict(row.get("raw_message_json"))
    text_parts.extend(_iter_string_values(raw))
    return [
        match.group(0)
        for value in text_parts
        for match in HTTP_URL_RE.finditer(value)
        if not _is_telegram_url(match.group(0))
    ]


def _iter_string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        items: list[str] = []
        for child in value.values():
            items.extend(_iter_string_values(child))
        return items
    if isinstance(value, list):
        items = []
        for child in value:
            items.extend(_iter_string_values(child))
        return items
    return []


def _normalize_url(url: str) -> str:
    return url.rstrip(".,;:!?)]}\"'")


def _is_telegram_url(url: str) -> bool:
    lowered = url.lower()
    return lowered.startswith("https://t.me/") or lowered.startswith("http://t.me/")


def _is_supported_document(row: dict[str, Any]) -> bool:
    media_type = str(row.get("media_type") or "").casefold()
    if media_type and media_type not in {"document", "file", "media"}:
        return False
    mime_type = str(row.get("mime_type") or "").split(";", 1)[0].strip().casefold()
    if mime_type.startswith("text/") or mime_type in SUPPORTED_DOCUMENT_MIME_TYPES:
        return True
    suffix = Path(str(row.get("file_name") or "")).suffix.casefold()
    return suffix in SUPPORTED_DOCUMENT_EXTENSIONS


def _media_source_url(row: dict[str, Any], raw: dict[str, Any]) -> str:
    media_ref = raw.get("telegram_media_ref") if isinstance(raw.get("telegram_media_ref"), dict) else {}
    return str(row.get("message_url") or media_ref.get("message_url") or "")


def _candidate_counts(
    message_rows: list[dict[str, Any]],
    attachment_rows: list[dict[str, Any]],
) -> dict[str, int]:
    return {
        "candidate_external_urls": len(_external_url_candidates(message_rows)),
        "candidate_documents": len(_document_candidates(attachment_rows)),
    }


def _metrics(rows: list[dict[str, Any]], *, candidates: dict[str, int]) -> dict[str, Any]:
    statuses = Counter(str(row["extraction_status"]) for row in rows)
    kinds = Counter(str(row["artifact_kind"]) for row in rows)
    return {
        **candidates,
        "total_rows": len(rows),
        "extracted_rows": statuses.get("extracted", 0),
        "rows_with_text": sum(1 for row in rows if row["has_text"]),
        "tokenizer_error_rows": sum(1 for row in rows if row["normalization_status"] == "tokenizer_error"),
        "total_tokens": sum(int(row["token_count"] or 0) for row in rows),
        "status_distribution": dict(sorted(statuses.items())),
        "artifact_kind_distribution": dict(sorted(kinds.items())),
    }


def _summary_payload(
    *,
    run: dict[str, Any],
    raw_export_run_id: str,
    messages_path: Path,
    attachments_path: Path,
    texts_parquet_path: Path,
    summary_path: Path,
    rows: list[dict[str, Any]],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "stage": STAGE_NAME,
        "stage_version": STAGE_VERSION,
        "generated_at": utc_now().isoformat(),
        "input": {
            "raw_export_run_id": raw_export_run_id,
            "monitored_source_id": run["monitored_source_id"],
            "source_ref": run["source_ref"],
            "source_kind": run["source_kind"],
            "username": run["username"],
            "messages_parquet_path": str(messages_path),
            "attachments_parquet_path": str(attachments_path),
        },
        "outputs": {
            "texts_parquet_path": str(texts_parquet_path),
            "summary_path": str(summary_path),
        },
        "metrics": metrics,
        "sample_rows": [
            {
                "telegram_message_id": row["telegram_message_id"],
                "artifact_kind": row["artifact_kind"],
                "source_url": row["source_url"],
                "file_name": row["file_name"],
                "extraction_status": row["extraction_status"],
                "clean_text": _truncate(str(row["clean_text"] or ""), 500),
                "message_url": row["message_url"],
            }
            for row in rows[:50]
        ],
    }


def _write_artifact_texts_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    schema = pa.schema(
        [
            ("export_run_id", pa.string()),
            ("monitored_source_id", pa.string()),
            ("telegram_message_id", pa.int64()),
            ("artifact_id", pa.string()),
            ("artifact_kind", pa.string()),
            ("chunk_index", pa.int64()),
            ("source_url", pa.string()),
            ("final_url", pa.string()),
            ("title", pa.string()),
            ("file_name", pa.string()),
            ("mime_type", pa.string()),
            ("file_size", pa.int64()),
            ("date", pa.string()),
            ("message_url", pa.string()),
            ("raw_text", pa.string()),
            ("clean_text", pa.string()),
            ("normalization_lang", pa.string()),
            ("tokens_json", pa.string()),
            ("lemmas_json", pa.string()),
            ("pos_tags_json", pa.string()),
            ("token_map_json", pa.string()),
            ("token_count", pa.int64()),
            ("has_text", pa.bool_()),
            ("normalization_status", pa.string()),
            ("normalization_error", pa.string()),
            ("extraction_status", pa.string()),
            ("extraction_error", pa.string()),
            ("parser_name", pa.string()),
            ("parser_version", pa.string()),
            ("raw_artifact_json", pa.string()),
        ]
    )
    table = (
        pa.Table.from_pylist(rows, schema=schema)
        if rows
        else pa.Table.from_pylist([], schema=schema)
    )
    pq.write_table(table, path, compression="zstd")


def _resolve_optional_local_path(value: Any, *, run: dict[str, Any]) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    if path.is_absolute() or path.exists():
        return path
    output_dir = _resolve_path(run.get("output_dir") or ".")
    sibling = output_dir / path
    if sibling.exists():
        return sibling
    return path


def _artifact_id(kind: str, telegram_message_id: Any, value: str) -> str:
    digest = sha256(f"{kind}:{telegram_message_id}:{value}".encode("utf-8")).hexdigest()[:24]
    return f"{kind}:{digest}"


def _json_dict(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_string(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _nullable_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 3] + "..."


def _resolve_path(value: Path | str | Any) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else Path(".") / path
