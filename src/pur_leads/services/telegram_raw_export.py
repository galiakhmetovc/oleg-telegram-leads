"""Telegram raw acquisition export writer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
from pathlib import Path
from typing import Any, Iterable

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import insert, update
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.integrations.telegram.types import ResolvedTelegramSource, TelegramMessage
from pur_leads.models.telegram_sources import telegram_raw_export_runs_table
from pur_leads.repositories.telegram_sources import MonitoredSourceRecord

EXPORT_FORMAT = "tdesktop_compatible_json_v1"


@dataclass(frozen=True)
class TelegramRawExportMessage:
    telegram_message_id: int
    row_index: int
    raw_message: dict[str, Any]


@dataclass(frozen=True)
class TelegramRawExportResult:
    run_id: str
    output_dir: Path
    result_json_path: Path
    messages_jsonl_path: Path
    attachments_jsonl_path: Path
    messages_parquet_path: Path
    attachments_parquet_path: Path
    manifest_path: Path
    message_count: int
    attachment_count: int
    messages: list[TelegramRawExportMessage]


class TelegramRawExportWriter:
    """Incremental raw export writer for one Telegram source acquisition run."""

    def __init__(
        self,
        *,
        session: Session,
        source: MonitoredSourceRecord,
        resolved_source: ResolvedTelegramSource,
        run_id: str,
        started_at: datetime,
        output_dir: Path,
        result_json_path: Path,
        messages_jsonl_path: Path,
        attachments_jsonl_path: Path,
        messages_parquet_path: Path,
        attachments_parquet_path: Path,
        manifest_path: Path,
    ) -> None:
        self.session = session
        self.source = source
        self.resolved_source = resolved_source
        self.run_id = run_id
        self.started_at = started_at
        self.output_dir = output_dir
        self.result_json_path = result_json_path
        self.messages_jsonl_path = messages_jsonl_path
        self.attachments_jsonl_path = attachments_jsonl_path
        self.messages_parquet_path = messages_parquet_path
        self.attachments_parquet_path = attachments_parquet_path
        self.manifest_path = manifest_path
        self.messages: list[TelegramRawExportMessage] = []
        self.attachments: list[dict[str, Any]] = []

    def append_messages(self, messages: list[TelegramMessage]) -> list[TelegramRawExportMessage]:
        raw_messages = [
            TelegramRawExportMessage(
                telegram_message_id=message.telegram_message_id,
                row_index=len(self.messages) + index,
                raw_message=_tdesktop_message_json(
                    message,
                    source=self.source,
                    resolved_source=self.resolved_source,
                ),
            )
            for index, message in enumerate(messages)
        ]
        self.messages.extend(raw_messages)
        self.attachments.extend(
            attachment
            for message in raw_messages
            for attachment in _attachment_rows(self.run_id, self.source.id, message)
        )
        return raw_messages

    def finish(self) -> TelegramRawExportResult:
        try:
            _write_json(self.result_json_path, self._result_payload())
            _write_jsonl(
                self.messages_jsonl_path,
                [message.raw_message for message in self.messages],
            )
            _write_jsonl(self.attachments_jsonl_path, self.attachments)
            _write_messages_parquet(
                self.messages_parquet_path,
                export_run_id=self.run_id,
                monitored_source_id=self.source.id,
                messages=self.messages,
            )
            _write_attachments_parquet(self.attachments_parquet_path, self.attachments)
            _write_json(self.manifest_path, self._manifest_payload())
        except Exception as exc:
            self.fail(str(exc) or exc.__class__.__name__)
            raise

        finished_at = utc_now()
        self.session.execute(
            update(telegram_raw_export_runs_table)
            .where(telegram_raw_export_runs_table.c.id == self.run_id)
            .values(
                status="succeeded",
                message_count=len(self.messages),
                attachment_count=len(self.attachments),
                finished_at=finished_at,
            )
        )
        self.session.commit()
        return TelegramRawExportResult(
            run_id=self.run_id,
            output_dir=self.output_dir,
            result_json_path=self.result_json_path,
            messages_jsonl_path=self.messages_jsonl_path,
            attachments_jsonl_path=self.attachments_jsonl_path,
            messages_parquet_path=self.messages_parquet_path,
            attachments_parquet_path=self.attachments_parquet_path,
            manifest_path=self.manifest_path,
            message_count=len(self.messages),
            attachment_count=len(self.attachments),
            messages=self.messages,
        )

    def fail(self, error: str) -> None:
        self.session.execute(
            update(telegram_raw_export_runs_table)
            .where(telegram_raw_export_runs_table.c.id == self.run_id)
            .values(status="failed", error=error, finished_at=utc_now())
        )
        self.session.commit()

    def _result_payload(self) -> dict[str, Any]:
        return {
            "about": "Telegram raw export generated by PUR Leads userbot ingest",
            "export_format": EXPORT_FORMAT,
            "run_id": self.run_id,
            "name": self.resolved_source.title
            or self.source.title
            or self.resolved_source.username
            or self.source.input_ref,
            "type": self.resolved_source.source_kind or self.source.source_kind,
            "id": self.resolved_source.telegram_id or self.source.telegram_id,
            "username": self.resolved_source.username or self.source.username,
            "source_ref": self.source.input_ref,
            "exported_at": self.started_at.isoformat(),
            "messages": [message.raw_message for message in self.messages],
        }

    def _manifest_payload(self) -> dict[str, Any]:
        return {
            "export_format": EXPORT_FORMAT,
            "run_id": self.run_id,
            "created_at": self.started_at.isoformat(),
            "source": {
                "monitored_source_id": self.source.id,
                "input_ref": self.source.input_ref,
                "telegram_id": self.resolved_source.telegram_id or self.source.telegram_id,
                "username": self.resolved_source.username or self.source.username,
                "title": self.resolved_source.title or self.source.title,
                "source_kind": self.resolved_source.source_kind or self.source.source_kind,
            },
            "files": {
                "result_json": self.result_json_path.name,
                "messages_jsonl": self.messages_jsonl_path.name,
                "attachments_jsonl": self.attachments_jsonl_path.name,
                "messages_parquet": self.messages_parquet_path.name,
                "attachments_parquet": self.attachments_parquet_path.name,
            },
            "message_count": len(self.messages),
            "attachment_count": len(self.attachments),
        }


class TelegramRawExportService:
    """Persist fetched Telegram batches as immutable raw JSON and parquet."""

    def __init__(self, session: Session, *, raw_root: Path | str = "./data/raw") -> None:
        self.session = session
        self.raw_root = Path(raw_root)

    def write_export(
        self,
        *,
        source: MonitoredSourceRecord,
        resolved_source: ResolvedTelegramSource,
        messages: list[TelegramMessage],
        run_id: str | None = None,
    ) -> TelegramRawExportResult:
        writer = self.open_export(
            source=source,
            resolved_source=resolved_source,
            run_id=run_id,
            metadata_json={
                "checkpoint_message_ids": [message.telegram_message_id for message in messages],
            },
        )
        writer.append_messages(messages)
        return writer.finish()

    def open_export(
        self,
        *,
        source: MonitoredSourceRecord,
        resolved_source: ResolvedTelegramSource,
        run_id: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> TelegramRawExportWriter:
        export_run_id = run_id or new_id()
        started_at = utc_now()
        output_dir = (
            self.raw_root
            / "telegram"
            / f"source_id={source.id}"
            / f"dt={started_at.date().isoformat()}"
            / f"run_id={export_run_id}"
        )
        output_dir.mkdir(parents=True, exist_ok=False)
        result_json_path = output_dir / "result.json"
        messages_jsonl_path = output_dir / "messages.jsonl"
        attachments_jsonl_path = output_dir / "attachments.jsonl"
        messages_parquet_path = output_dir / "messages_raw.parquet"
        attachments_parquet_path = output_dir / "attachments_raw.parquet"
        manifest_path = output_dir / "manifest.json"

        self.session.execute(
            insert(telegram_raw_export_runs_table).values(
                id=export_run_id,
                monitored_source_id=source.id,
                source_ref=source.input_ref,
                source_kind=resolved_source.source_kind or source.source_kind,
                telegram_id=resolved_source.telegram_id or source.telegram_id,
                username=resolved_source.username or source.username,
                title=resolved_source.title or source.title,
                export_format=EXPORT_FORMAT,
                output_dir=str(output_dir),
                result_json_path=str(result_json_path),
                messages_jsonl_path=str(messages_jsonl_path),
                attachments_jsonl_path=str(attachments_jsonl_path),
                messages_parquet_path=str(messages_parquet_path),
                attachments_parquet_path=str(attachments_parquet_path),
                manifest_path=str(manifest_path),
                message_count=0,
                attachment_count=0,
                status="running",
                error=None,
                started_at=started_at,
                finished_at=None,
                metadata_json=metadata_json or {},
                created_at=started_at,
            )
        )
        self.session.commit()
        return TelegramRawExportWriter(
            session=self.session,
            source=source,
            resolved_source=resolved_source,
            run_id=export_run_id,
            started_at=started_at,
            output_dir=output_dir,
            result_json_path=result_json_path,
            messages_jsonl_path=messages_jsonl_path,
            attachments_jsonl_path=attachments_jsonl_path,
            messages_parquet_path=messages_parquet_path,
            attachments_parquet_path=attachments_parquet_path,
            manifest_path=manifest_path,
        )


def _tdesktop_message_json(
    message: TelegramMessage,
    *,
    source: MonitoredSourceRecord,
    resolved_source: ResolvedTelegramSource,
) -> dict[str, Any]:
    text = message.text or ""
    caption = message.caption or None
    message_url = _message_url(source, resolved_source, message.telegram_message_id)
    media = _media_with_reference(
        message.media_metadata_json,
        source=source,
        resolved_source=resolved_source,
        telegram_message_id=message.telegram_message_id,
        message_url=message_url,
    )
    document = media.get("document") if isinstance(media.get("document"), dict) else {}
    return {
        "id": message.telegram_message_id,
        "type": "message",
        "date": message.message_date.isoformat(),
        "date_unixtime": str(int(message.message_date.timestamp())),
        "message_url": message_url,
        "from": message.sender_display,
        "from_id": message.sender_id,
        "text": text,
        "text_entities": _plain_entities(text),
        "caption": caption,
        "caption_entities": _plain_entities(caption or ""),
        "reply_to_message_id": message.reply_to_message_id,
        "thread_id": message.thread_id,
        "media_type": _media_type(media),
        "mime_type": document.get("mime_type") or media.get("mime_type"),
        "file": document.get("file_name") or media.get("file_name"),
        "file_size": document.get("file_size") or media.get("file_size"),
        "forwarded_from": message.forward_metadata_json,
        "raw_media_json": media or None,
        "raw_telethon_json": message.raw_metadata_json,
    }


def _media_with_reference(
    media_metadata: dict[str, Any] | None,
    *,
    source: MonitoredSourceRecord,
    resolved_source: ResolvedTelegramSource,
    telegram_message_id: int,
    message_url: str | None,
) -> dict[str, Any]:
    media = dict(media_metadata or {})
    if not media:
        return media
    media["telegram_media_ref"] = {
        "kind": "telegram_message_media",
        "monitored_source_id": source.id,
        "source_ref": source.input_ref,
        "source_username": resolved_source.username or source.username,
        "source_telegram_id": resolved_source.telegram_id or source.telegram_id,
        "telegram_message_id": telegram_message_id,
        "message_url": message_url,
    }
    return media


def _message_url(
    source: MonitoredSourceRecord,
    resolved_source: ResolvedTelegramSource,
    message_id: int,
) -> str | None:
    username = resolved_source.username or source.username
    if not username:
        return None
    return f"https://t.me/{username}/{message_id}"


def _plain_entities(text: str) -> list[dict[str, str]]:
    return [{"type": "plain", "text": text}] if text else []


def _media_type(media: dict[str, Any]) -> str | None:
    if not media:
        return None
    document = media.get("document")
    if isinstance(document, dict):
        mime_type = str(document.get("mime_type") or "")
        if mime_type.startswith("image/"):
            return "photo"
        if mime_type.startswith("video/"):
            return "video_file"
        return "document"
    value = media.get("media_type") or media.get("type") or media.get("kind")
    return str(value) if value is not None else "media"


def _attachment_rows(
    run_id: str,
    monitored_source_id: str,
    message: TelegramRawExportMessage,
) -> list[dict[str, Any]]:
    raw_media = message.raw_message.get("raw_media_json")
    if not isinstance(raw_media, dict) or not raw_media:
        return []
    document = raw_media.get("document") if isinstance(raw_media.get("document"), dict) else {}
    return [
        {
            "export_run_id": run_id,
            "monitored_source_id": monitored_source_id,
            "telegram_message_id": message.telegram_message_id,
            "attachment_index": 0,
            "media_type": message.raw_message.get("media_type"),
            "file_name": document.get("file_name") or raw_media.get("file_name"),
            "mime_type": document.get("mime_type") or raw_media.get("mime_type"),
            "file_size": document.get("file_size") or raw_media.get("file_size"),
            "downloadable": bool(document.get("downloadable") or raw_media.get("downloadable")),
            "message_url": message.raw_message.get("message_url"),
            "media_ref_json": _json_string(raw_media.get("telegram_media_ref")),
            "raw_attachment_json": _json_string(raw_media),
        }
    ]


def _write_messages_parquet(
    path: Path,
    *,
    export_run_id: str,
    monitored_source_id: str,
    messages: list[TelegramRawExportMessage],
) -> None:
    rows = (
        {
            "export_run_id": export_run_id,
            "monitored_source_id": monitored_source_id,
            "telegram_message_id": message.telegram_message_id,
            "row_index": message.row_index,
            "date": message.raw_message.get("date"),
            "date_unixtime": message.raw_message.get("date_unixtime"),
            "sender_id": message.raw_message.get("from_id"),
            "sender_display": message.raw_message.get("from"),
            "text_plain": message.raw_message.get("text") or "",
            "caption": message.raw_message.get("caption"),
            "text_entities_json": _json_string(message.raw_message.get("text_entities")),
            "caption_entities_json": _json_string(message.raw_message.get("caption_entities")),
            "reply_to_message_id": message.raw_message.get("reply_to_message_id"),
            "thread_id": message.raw_message.get("thread_id"),
            "media_type": message.raw_message.get("media_type"),
            "mime_type": message.raw_message.get("mime_type"),
            "file_name": message.raw_message.get("file"),
            "message_url": message.raw_message.get("message_url"),
            "raw_message_json": _json_string(message.raw_message),
        }
        for message in messages
    )
    _write_parquet(
        rows,
        path,
        schema=pa.schema(
            [
                ("export_run_id", pa.string()),
                ("monitored_source_id", pa.string()),
                ("telegram_message_id", pa.int64()),
                ("row_index", pa.int64()),
                ("date", pa.string()),
                ("date_unixtime", pa.string()),
                ("sender_id", pa.string()),
                ("sender_display", pa.string()),
                ("text_plain", pa.string()),
                ("caption", pa.string()),
                ("text_entities_json", pa.string()),
                ("caption_entities_json", pa.string()),
                ("reply_to_message_id", pa.int64()),
                ("thread_id", pa.string()),
                ("media_type", pa.string()),
                ("mime_type", pa.string()),
                ("file_name", pa.string()),
                ("message_url", pa.string()),
                ("raw_message_json", pa.string()),
            ]
        ),
    )


def _write_attachments_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    _write_parquet(
        rows,
        path,
        schema=pa.schema(
            [
                ("export_run_id", pa.string()),
                ("monitored_source_id", pa.string()),
                ("telegram_message_id", pa.int64()),
                ("attachment_index", pa.int64()),
                ("media_type", pa.string()),
                ("file_name", pa.string()),
                ("mime_type", pa.string()),
                ("file_size", pa.int64()),
                ("downloadable", pa.bool_()),
                ("message_url", pa.string()),
                ("media_ref_json", pa.string()),
                ("raw_attachment_json", pa.string()),
            ]
        ),
    )


def _write_parquet(
    rows: Iterable[dict[str, Any]],
    path: Path,
    *,
    schema: pa.Schema,
    batch_size: int = 5000,
) -> None:
    writer: pq.ParquetWriter | None = None
    batch: list[dict[str, Any]] = []
    wrote_rows = False
    try:
        for row in rows:
            batch.append(row)
            if len(batch) < batch_size:
                continue
            table = pa.Table.from_pylist(batch, schema=schema)
            writer = writer or pq.ParquetWriter(path, schema=schema, compression="zstd")
            writer.write_table(table)
            wrote_rows = True
            batch = []
        if batch:
            table = pa.Table.from_pylist(batch, schema=schema)
            writer = writer or pq.ParquetWriter(path, schema=schema, compression="zstd")
            writer.write_table(table)
            wrote_rows = True
        if not wrote_rows:
            table = pa.Table.from_pylist([], schema=schema)
            pq.write_table(table, path, compression="zstd")
    finally:
        if writer is not None:
            writer.close()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default),
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=_json_default))
            file.write("\n")


def _json_string(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=_json_default)


def _json_default(value: Any) -> str:
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)
