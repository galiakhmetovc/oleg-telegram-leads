"""Import Telegram Desktop JSON exports into the canonical raw export pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

from sqlalchemy import insert, update
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.integrations.telegram.types import ResolvedTelegramSource
from pur_leads.models.telegram_sources import source_messages_table, telegram_raw_export_runs_table
from pur_leads.repositories.telegram_sources import MonitoredSourceRecord
from pur_leads.services.telegram_raw_export import (
    TelegramRawExportMessage,
    TelegramRawExportResult,
    TelegramRawExportService,
    _attachment_rows,
    _write_attachments_parquet,
    _write_json,
    _write_jsonl,
    _write_messages_parquet,
)
from pur_leads.services.telegram_sources import TelegramSourceService

DESKTOP_IMPORT_EXPORT_FORMAT = "telegram_desktop_json_v1"
SOURCE_MESSAGE_BATCH_SIZE = 1000


@dataclass(frozen=True)
class TelegramDesktopArchiveImportResult:
    raw_export: TelegramRawExportResult
    source: MonitoredSourceRecord
    created_source_messages: int
    skipped_source_messages: int
    service_message_count: int

    @property
    def message_count(self) -> int:
        return self.raw_export.message_count

    @property
    def attachment_count(self) -> int:
        return self.raw_export.attachment_count

    def as_jsonable(self) -> dict[str, Any]:
        return {
            "raw_export_run_id": self.raw_export.run_id,
            "monitored_source_id": self.source.id,
            "source_ref": self.source.input_ref,
            "message_count": self.message_count,
            "attachment_count": self.attachment_count,
            "created_source_messages": self.created_source_messages,
            "skipped_source_messages": self.skipped_source_messages,
            "service_message_count": self.service_message_count,
            "output_dir": str(self.raw_export.output_dir),
            "result_json_path": str(self.raw_export.result_json_path),
            "messages_parquet_path": str(self.raw_export.messages_parquet_path),
            "attachments_parquet_path": str(self.raw_export.attachments_parquet_path),
        }


class TelegramDesktopArchiveImportService:
    def __init__(self, session: Session, *, raw_root: Path | str = "./data/raw") -> None:
        self.session = session
        self.raw_root = Path(raw_root)

    def import_archive(
        self,
        archive_path: Path | str,
        *,
        input_ref: str | None = None,
        purpose: str = "lead_monitoring",
        added_by: str = "system",
        sync_source_messages: bool = False,
        source: MonitoredSourceRecord | None = None,
        import_metadata: dict[str, Any] | None = None,
    ) -> TelegramDesktopArchiveImportResult:
        archive_path = Path(archive_path)
        payload, result_member = _read_archive_result(archive_path)
        source = source or self._create_source(
            payload,
            input_ref=input_ref,
            purpose=purpose,
            added_by=added_by,
        )
        source_kind = _source_kind(payload, fallback=source.source_kind)
        resolved = ResolvedTelegramSource(
            input_ref=source.input_ref,
            source_kind=source_kind,
            telegram_id=str(payload.get("id"))
            if payload.get("id") is not None
            else source.telegram_id,
            username=source.username,
            title=_optional_string(payload.get("name")) or source.title,
        )
        metadata_json = {
            "desktop_import": {
                "archive_name": archive_path.name,
                "result_member": result_member,
                "source_type": payload.get("type"),
                "source_id": payload.get("id"),
                "sync_source_messages": sync_source_messages,
            }
        }
        if import_metadata:
            metadata_json.update(import_metadata)
        writer = TelegramRawExportService(self.session, raw_root=self.raw_root).open_export(
            source=source,
            resolved_source=resolved,
            metadata_json=metadata_json,
        )
        self.session.execute(
            update(telegram_raw_export_runs_table)
            .where(telegram_raw_export_runs_table.c.id == writer.run_id)
            .values(export_format=DESKTOP_IMPORT_EXPORT_FORMAT)
        )
        self.session.commit()

        try:
            raw_messages = _raw_export_messages(
                payload,
                source=source,
                resolved_source=resolved,
            )
            attachments = [
                attachment
                for message in raw_messages
                for attachment in _attachment_rows(writer.run_id, source.id, message)
            ]
            _copy_result_json(archive_path, result_member, writer.result_json_path)
            _write_jsonl(
                writer.messages_jsonl_path, [message.raw_message for message in raw_messages]
            )
            _write_jsonl(writer.attachments_jsonl_path, attachments)
            _write_messages_parquet(
                writer.messages_parquet_path,
                export_run_id=writer.run_id,
                monitored_source_id=source.id,
                messages=raw_messages,
            )
            _write_attachments_parquet(writer.attachments_parquet_path, attachments)
            _write_json(
                writer.manifest_path,
                {
                    "export_format": DESKTOP_IMPORT_EXPORT_FORMAT,
                    "run_id": writer.run_id,
                    "created_at": writer.started_at.isoformat(),
                    "source": {
                        "monitored_source_id": source.id,
                        "input_ref": source.input_ref,
                        "telegram_id": resolved.telegram_id,
                        "username": resolved.username,
                        "title": resolved.title,
                        "source_kind": resolved.source_kind,
                    },
                    "archive": {
                        "path": str(archive_path),
                        "result_member": result_member,
                    },
                    "files": {
                        "result_json": writer.result_json_path.name,
                        "messages_jsonl": writer.messages_jsonl_path.name,
                        "attachments_jsonl": writer.attachments_jsonl_path.name,
                        "messages_parquet": writer.messages_parquet_path.name,
                        "attachments_parquet": writer.attachments_parquet_path.name,
                    },
                    "message_count": len(raw_messages),
                    "attachment_count": len(attachments),
                    "metadata": metadata_json,
                },
            )
            created_source_messages = (
                self._sync_source_messages(
                    source=source,
                    raw_export_run_id=writer.run_id,
                    messages=raw_messages,
                )
                if sync_source_messages
                else 0
            )
            finished_at = utc_now()
            self.session.execute(
                update(telegram_raw_export_runs_table)
                .where(telegram_raw_export_runs_table.c.id == writer.run_id)
                .values(
                    status="succeeded",
                    message_count=len(raw_messages),
                    attachment_count=len(attachments),
                    finished_at=finished_at,
                )
            )
            self.session.commit()
            raw_export = TelegramRawExportResult(
                run_id=writer.run_id,
                output_dir=writer.output_dir,
                result_json_path=writer.result_json_path,
                messages_jsonl_path=writer.messages_jsonl_path,
                attachments_jsonl_path=writer.attachments_jsonl_path,
                messages_parquet_path=writer.messages_parquet_path,
                attachments_parquet_path=writer.attachments_parquet_path,
                manifest_path=writer.manifest_path,
                message_count=len(raw_messages),
                attachment_count=len(attachments),
                messages=raw_messages,
            )
        except Exception as exc:
            writer.fail(str(exc) or exc.__class__.__name__)
            raise

        self.session.commit()
        return TelegramDesktopArchiveImportResult(
            raw_export=raw_export,
            source=source,
            created_source_messages=created_source_messages,
            skipped_source_messages=len(raw_messages) - created_source_messages,
            service_message_count=sum(
                1 for message in raw_messages if message.raw_message["type"] != "message"
            ),
        )

    def _create_source(
        self,
        payload: dict[str, Any],
        *,
        input_ref: str | None,
        purpose: str,
        added_by: str,
    ) -> MonitoredSourceRecord:
        source_ref = input_ref or f"telegram-desktop://{payload.get('id') or new_id()}"
        service = TelegramSourceService(self.session)
        source = service.create_draft(
            source_ref,
            added_by=added_by,
            purpose=purpose,
            start_mode="from_beginning",
        )
        updated = service.repository.update(
            source.id,
            telegram_id=str(payload.get("id"))
            if payload.get("id") is not None
            else source.telegram_id,
            title=_optional_string(payload.get("name")) or source.title,
            source_kind=_source_kind(payload, fallback=source.source_kind),
            status="active",
            activated_by=added_by,
            activated_at=utc_now(),
            updated_at=utc_now(),
        )
        return updated

    def _sync_source_messages(
        self,
        *,
        source: MonitoredSourceRecord,
        raw_export_run_id: str,
        messages: list[TelegramRawExportMessage],
    ) -> int:
        now = utc_now()
        rows: list[dict[str, Any]] = []
        created = 0
        for message in messages:
            raw = message.raw_message
            if raw.get("type") != "message":
                continue
            rows.append(
                {
                    "id": new_id(),
                    "monitored_source_id": source.id,
                    "raw_source_id": None,
                    "telegram_message_id": message.telegram_message_id,
                    "sender_id": raw.get("from_id"),
                    "message_date": _message_datetime(raw),
                    "text": raw.get("text") or None,
                    "caption": raw.get("caption"),
                    "normalized_text": _normalize_text(raw.get("text"), raw.get("caption")),
                    "has_media": bool(raw.get("raw_media_json")),
                    "media_metadata_json": raw.get("raw_media_json"),
                    "reply_to_message_id": raw.get("reply_to_message_id"),
                    "thread_id": raw.get("thread_id"),
                    "forward_metadata_json": raw.get("forwarded_from"),
                    "raw_metadata_json": raw,
                    "fetched_at": now,
                    "classification_status": "unclassified",
                    "archive_pointer_id": raw_export_run_id,
                    "is_archived_stub": False,
                    "text_archived": False,
                    "caption_archived": False,
                    "metadata_archived": False,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            if len(rows) >= SOURCE_MESSAGE_BATCH_SIZE:
                self.session.execute(insert(source_messages_table), rows)
                created += len(rows)
                rows = []
        if rows:
            self.session.execute(insert(source_messages_table), rows)
            created += len(rows)
        return created


def _read_archive_result(archive_path: Path) -> tuple[dict[str, Any], str]:
    with zipfile.ZipFile(archive_path) as archive:
        result_members = [
            name
            for name in archive.namelist()
            if name == "result.json" or name.endswith("/result.json")
        ]
        if not result_members:
            raise ValueError("Telegram Desktop archive does not contain result.json")
        result_member = sorted(result_members, key=len)[0]
        with archive.open(result_member) as file:
            payload = json.load(file)
    if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
        raise ValueError("Telegram Desktop result.json must contain a messages array")
    return payload, result_member


def _copy_result_json(archive_path: Path, result_member: str, target: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        with archive.open(result_member) as source_file, target.open("wb") as target_file:
            shutil.copyfileobj(source_file, target_file)


def _raw_export_messages(
    payload: dict[str, Any],
    *,
    source: MonitoredSourceRecord,
    resolved_source: ResolvedTelegramSource,
) -> list[TelegramRawExportMessage]:
    result: list[TelegramRawExportMessage] = []
    for row_index, raw in enumerate(payload["messages"]):
        if not isinstance(raw, dict):
            continue
        message_id = _message_id(raw)
        if message_id is None:
            continue
        normalized = _normalize_desktop_message(
            raw,
            source=source,
            resolved_source=resolved_source,
            telegram_message_id=message_id,
        )
        result.append(
            TelegramRawExportMessage(
                telegram_message_id=message_id,
                row_index=row_index,
                raw_message=normalized,
            )
        )
    return result


def _normalize_desktop_message(
    raw: dict[str, Any],
    *,
    source: MonitoredSourceRecord,
    resolved_source: ResolvedTelegramSource,
    telegram_message_id: int,
) -> dict[str, Any]:
    text = _text_plain(raw.get("text"))
    caption = _text_plain(raw.get("caption")) or None
    message_url = _message_url(source, resolved_source, telegram_message_id)
    raw_media = _raw_media(raw, message_url=message_url)
    return {
        "id": telegram_message_id,
        "type": str(raw.get("type") or "message"),
        "date": str(raw.get("date") or ""),
        "date_unixtime": str(raw.get("date_unixtime") or ""),
        "message_url": message_url,
        "from": raw.get("from") or raw.get("actor"),
        "from_id": raw.get("from_id") or raw.get("actor_id"),
        "text": text,
        "text_entities": raw.get("text_entities")
        if isinstance(raw.get("text_entities"), list)
        else [],
        "caption": caption,
        "caption_entities": raw.get("caption_entities")
        if isinstance(raw.get("caption_entities"), list)
        else [],
        "reply_to_message_id": raw.get("reply_to_message_id"),
        "thread_id": raw.get("thread_id"),
        "media_type": raw_media.get("media_type") if raw_media else None,
        "mime_type": raw_media.get("mime_type") if raw_media else None,
        "file": raw_media.get("file_name") if raw_media else None,
        "file_size": raw_media.get("file_size") if raw_media else None,
        "forwarded_from": raw.get("forwarded_from"),
        "raw_media_json": raw_media or None,
        "raw_telethon_json": None,
        "raw_tdesktop_json": raw,
    }


def _raw_media(raw: dict[str, Any], *, message_url: str | None) -> dict[str, Any]:
    media_type: str | None = None
    file_name: str | None = None
    file_size: int | None = None
    mime_type: str | None = _optional_string(raw.get("mime_type"))
    if "photo" in raw:
        media_type = "photo"
        file_name = _file_name(raw.get("photo"), default="photo.jpg")
        file_size = _optional_int(raw.get("photo_file_size") or raw.get("file_size"))
        mime_type = mime_type or "image/jpeg"
        downloadable = _downloadable_media_path(raw.get("photo"))
    elif "file" in raw:
        media_type = str(raw.get("media_type") or "document")
        file_name = _file_name(raw.get("file"))
        file_size = _optional_int(raw.get("file_size"))
        downloadable = _downloadable_media_path(raw.get("file"))
    elif raw.get("media_type"):
        media_type = str(raw.get("media_type"))
        file_size = _optional_int(raw.get("file_size"))
        downloadable = False
    if media_type is None:
        return {}
    return {
        "type": "TelegramDesktopMedia",
        "media_type": media_type,
        "file_name": file_name,
        "mime_type": mime_type,
        "file_size": file_size,
        "downloadable": downloadable,
        "raw_export_download": {
            "status": "not_extracted",
            "local_path": None,
        },
        "telegram_media_ref": {
            "kind": "telegram_desktop_export_media",
            "message_url": message_url,
        },
        "raw_tdesktop_media_json": {
            key: raw[key]
            for key in (
                "media_type",
                "mime_type",
                "file",
                "file_size",
                "photo",
                "photo_file_size",
                "width",
                "height",
                "duration_seconds",
            )
            if key in raw
        },
    }


def _message_id(raw: dict[str, Any]) -> int | None:
    try:
        return int(raw["id"])
    except (KeyError, TypeError, ValueError):
        return None


def _message_url(
    source: MonitoredSourceRecord,
    resolved_source: ResolvedTelegramSource,
    message_id: int,
) -> str | None:
    username = resolved_source.username or source.username
    return f"https://t.me/{username}/{message_id}" if username else None


def _source_kind(payload: dict[str, Any], *, fallback: str) -> str:
    raw_type = str(payload.get("type") or "").casefold()
    if "channel" in raw_type and "supergroup" not in raw_type:
        return "telegram_channel"
    if "group" in raw_type:
        return "telegram_supergroup"
    return fallback


def _text_plain(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or ""))
        return "".join(parts)
    return str(value)


def _file_name(value: Any, *, default: str | None = None) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return default
    if value.startswith("(File not included."):
        return default
    return Path(value).name


def _downloadable_media_path(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and not value.startswith("(File not included.")
    )


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _message_datetime(raw: dict[str, Any]) -> datetime:
    try:
        return datetime.fromtimestamp(int(str(raw.get("date_unixtime"))), UTC)
    except (TypeError, ValueError, OSError):
        value = str(raw.get("date") or "")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return utc_now()
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _normalize_text(*values: Any) -> str:
    return " ".join(
        text.casefold().strip() for text in (_text_plain(value) for value in values) if text.strip()
    )
