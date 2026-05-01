"""Telegram source polling and message persistence."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.integrations.telegram.client import TelegramClientPort
from pur_leads.integrations.telegram.types import ResolvedTelegramSource, TelegramMessage
from pur_leads.models.scheduler import scheduler_jobs_table
from pur_leads.models.telegram_sources import source_messages_table
from pur_leads.repositories.telegram_sources import MonitoredSourceRecord, TelegramSourceRepository
from pur_leads.services.catalog_sources import CatalogSourceService
from pur_leads.services.scheduler import SchedulerService
from pur_leads.services.settings import SettingsService
from pur_leads.services.telegram_raw_export import (
    TelegramRawExportMessage,
    TelegramRawExportResult,
    TelegramRawExportService,
    TelegramRawExportWriter,
)


@dataclass(frozen=True)
class PollResult:
    status: str
    fetched_count: int
    inserted_count: int
    duplicate_count: int
    checkpoint_before: int | None
    checkpoint_after: int | None
    reason: str | None = None


@dataclass(frozen=True)
class RawExportResult:
    status: str
    fetched_count: int
    inserted_count: int
    duplicate_count: int
    checkpoint_before: int | None
    checkpoint_after: int | None
    raw_export_run_id: str | None
    output_dir: str | None
    reason: str | None = None


@dataclass(frozen=True)
class ExistingSourceMessage:
    id: str
    raw_source_id: str | None


@dataclass(frozen=True)
class ExportRangeCursor:
    mode: str
    after_message_id: int | None
    from_message_id: int | None
    after_date: datetime | None
    limit: int | None
    batch_size: int
    skip_reason: str | None = None


class TelegramPollingWorker:
    def __init__(
        self,
        session: Session,
        client: TelegramClientPort,
        *,
        raw_export_root: Path | str = "./data/raw",
    ) -> None:
        self.session = session
        self.client = client
        self.sources = TelegramSourceRepository(session)
        self.catalog_sources = CatalogSourceService(session)
        self.raw_exports = TelegramRawExportService(session, raw_root=raw_export_root)
        self.scheduler = SchedulerService(session)
        self.settings = SettingsService(session)

    async def poll_monitored_source(
        self,
        source_id: str,
        *,
        scheduler_job_id: str | None = None,
        limit: int = 100,
        require_active: bool = True,
        enqueue_classification: bool = True,
    ) -> PollResult:
        source = self._require_source(source_id)
        checkpoint_before = source.checkpoint_message_id
        if require_active and source.status != "active":
            return PollResult(
                status="skipped",
                fetched_count=0,
                inserted_count=0,
                duplicate_count=0,
                checkpoint_before=checkpoint_before,
                checkpoint_after=checkpoint_before,
                reason="source_not_active",
            )

        resolved = _resolved_source_from_record(source)
        now = utc_now()
        messages = await self.client.fetch_message_batch(
            resolved,
            after_message_id=checkpoint_before,
            after_date=_start_after_date(source, now),
            limit=limit,
        )
        raw_export = (
            self.raw_exports.write_export(
                source=source,
                resolved_source=resolved,
                messages=messages,
            )
            if messages
            else None
        )
        raw_messages_by_id = (
            {message.telegram_message_id: message for message in raw_export.messages}
            if raw_export is not None
            else {}
        )
        existing_messages = self._existing_messages(source.id)
        seen_message_ids: set[int] = set()
        inserted_count = 0
        duplicate_count = 0

        for message in messages:
            message_id = message.telegram_message_id
            existing_message = existing_messages.get(message_id)
            if existing_message is not None or message_id in seen_message_ids:
                duplicate_count += 1
                if (
                    source.catalog_ingestion_enabled
                    and existing_message is not None
                    and existing_message.raw_source_id is None
                ):
                    self._mirror_catalog_source(source, existing_message.id, message)
                continue

            source_message_id = new_id()
            self.session.execute(
                insert(source_messages_table).values(
                    id=source_message_id,
                    monitored_source_id=source.id,
                    raw_source_id=None,
                    telegram_message_id=message_id,
                    sender_id=message.sender_id,
                    message_date=message.message_date,
                    text=message.text,
                    caption=message.caption,
                    normalized_text=_normalize_text(message),
                    has_media=message.has_media,
                    media_metadata_json=message.media_metadata_json,
                    reply_to_message_id=message.reply_to_message_id,
                    thread_id=message.thread_id,
                    forward_metadata_json=message.forward_metadata_json,
                    raw_metadata_json=_canonical_raw_metadata(
                        message,
                        raw_export=raw_export,
                        raw_message=raw_messages_by_id.get(message_id),
                    ),
                    fetched_at=now,
                    classification_status="unclassified",
                    archive_pointer_id=raw_export.run_id if raw_export is not None else None,
                    is_archived_stub=False,
                    text_archived=False,
                    caption_archived=False,
                    metadata_archived=False,
                    created_at=now,
                    updated_at=now,
                )
            )
            inserted_count += 1
            seen_message_ids.add(message_id)
            existing_messages[message_id] = ExistingSourceMessage(
                id=source_message_id,
                raw_source_id=None,
            )
            if source.catalog_ingestion_enabled:
                self._mirror_catalog_source(source, source_message_id, message)

        checkpoint_after = _checkpoint_after(checkpoint_before, messages)
        next_poll_at = now + timedelta(seconds=max(source.poll_interval_seconds, 1))
        if inserted_count > 0 and source.lead_detection_enabled and enqueue_classification:
            self._enqueue_classification(source)
        self.sources.update(
            source.id,
            checkpoint_message_id=checkpoint_after,
            checkpoint_date=now,
            next_poll_at=next_poll_at,
            last_success_at=now,
            last_error=None,
            last_error_at=None,
            updated_at=now,
        )
        result = PollResult(
            status="succeeded",
            fetched_count=len(messages),
            inserted_count=inserted_count,
            duplicate_count=duplicate_count,
            checkpoint_before=checkpoint_before,
            checkpoint_after=checkpoint_after,
        )
        if scheduler_job_id is not None:
            self._record_scheduler_checkpoint(scheduler_job_id, result)

        self.session.commit()
        return result

    async def export_monitored_source_raw(
        self,
        source_id: str,
        *,
        scheduler_job_id: str | None = None,
        range_config: dict[str, Any] | None = None,
        media_config: dict[str, Any] | None = None,
        canonicalize: bool = True,
    ) -> RawExportResult:
        source = self._require_source(source_id)
        checkpoint_before = source.checkpoint_message_id
        now = utc_now()
        cursor = _export_range_cursor(source, range_config or {}, now)
        if cursor.skip_reason is not None:
            result = RawExportResult(
                status="skipped",
                fetched_count=0,
                inserted_count=0,
                duplicate_count=0,
                checkpoint_before=checkpoint_before,
                checkpoint_after=checkpoint_before,
                raw_export_run_id=None,
                output_dir=None,
                reason=cursor.skip_reason,
            )
            if scheduler_job_id is not None:
                self._record_raw_export_checkpoint(scheduler_job_id, result)
            self.session.commit()
            return result

        resolved = _resolved_source_from_record(source)
        media_policy = _media_policy(media_config or {})
        writer = self.raw_exports.open_export(
            source=source,
            resolved_source=resolved,
            metadata_json={
                "range": _range_metadata(cursor),
                "media": media_policy,
                "canonicalize": canonicalize,
            },
        )
        existing_messages = self._existing_messages(source.id) if canonicalize else {}
        seen_message_ids: set[int] = set()
        fetched_count = 0
        inserted_count = 0
        duplicate_count = 0
        checkpoint_after = checkpoint_before
        try:
            async for batch in self.client.iter_message_batches(
                resolved,
                after_message_id=cursor.after_message_id,
                from_message_id=cursor.from_message_id,
                after_date=cursor.after_date,
                limit=cursor.limit,
                batch_size=cursor.batch_size,
            ):
                export_batch = await self._apply_media_policy(
                    resolved,
                    writer,
                    batch,
                    media_policy=media_policy,
                )
                raw_messages = writer.append_messages(export_batch)
                raw_messages_by_id = {
                    message.telegram_message_id: message for message in raw_messages
                }
                fetched_count += len(export_batch)
                checkpoint_after = _checkpoint_after(checkpoint_after, export_batch)
                if canonicalize:
                    inserted, duplicates = self._persist_raw_export_batch(
                        source=source,
                        export_writer=writer,
                        messages=export_batch,
                        raw_messages_by_id=raw_messages_by_id,
                        existing_messages=existing_messages,
                        seen_message_ids=seen_message_ids,
                        fetched_at=now,
                    )
                    inserted_count += inserted
                    duplicate_count += duplicates
            raw_export = writer.finish()
        except Exception as exc:
            writer.fail(str(exc) or exc.__class__.__name__)
            raise

        if fetched_count > 0:
            self.sources.update(
                source.id,
                checkpoint_message_id=checkpoint_after,
                checkpoint_date=now,
                last_success_at=now,
                last_error=None,
                last_error_at=None,
                updated_at=now,
            )
        result = RawExportResult(
            status="succeeded",
            fetched_count=fetched_count,
            inserted_count=inserted_count,
            duplicate_count=duplicate_count,
            checkpoint_before=checkpoint_before,
            checkpoint_after=checkpoint_after,
            raw_export_run_id=raw_export.run_id,
            output_dir=str(raw_export.output_dir),
        )
        if scheduler_job_id is not None:
            self._record_raw_export_checkpoint(scheduler_job_id, result)
        self.session.commit()
        return result

    def _enqueue_classification(self, source: MonitoredSourceRecord) -> None:
        self.scheduler.enqueue(
            job_type="classify_message_batch",
            scope_type="telegram_source",
            scope_id=source.id,
            monitored_source_id=source.id,
            idempotency_key=f"source:{source.id}:classify:active",
            payload_json={"limit": 100, "trigger": "poll_monitored_source"},
        )

    def _existing_messages(self, source_id: str) -> dict[int, ExistingSourceMessage]:
        rows = self.session.execute(
            select(
                source_messages_table.c.telegram_message_id,
                source_messages_table.c.id,
                source_messages_table.c.raw_source_id,
            ).where(source_messages_table.c.monitored_source_id == source_id)
        ).all()
        return {
            row.telegram_message_id: ExistingSourceMessage(
                id=row.id,
                raw_source_id=row.raw_source_id,
            )
            for row in rows
        }

    def _persist_raw_export_batch(
        self,
        *,
        source: MonitoredSourceRecord,
        export_writer: TelegramRawExportWriter,
        messages: list[TelegramMessage],
        raw_messages_by_id: dict[int, TelegramRawExportMessage],
        existing_messages: dict[int, ExistingSourceMessage],
        seen_message_ids: set[int],
        fetched_at: datetime,
    ) -> tuple[int, int]:
        inserted_count = 0
        duplicate_count = 0
        for message in messages:
            message_id = message.telegram_message_id
            existing_message = existing_messages.get(message_id)
            if existing_message is not None or message_id in seen_message_ids:
                duplicate_count += 1
                continue

            source_message_id = new_id()
            self.session.execute(
                insert(source_messages_table).values(
                    id=source_message_id,
                    monitored_source_id=source.id,
                    raw_source_id=None,
                    telegram_message_id=message_id,
                    sender_id=message.sender_id,
                    message_date=message.message_date,
                    text=message.text,
                    caption=message.caption,
                    normalized_text=_normalize_text(message),
                    has_media=message.has_media,
                    media_metadata_json=message.media_metadata_json,
                    reply_to_message_id=message.reply_to_message_id,
                    thread_id=message.thread_id,
                    forward_metadata_json=message.forward_metadata_json,
                    raw_metadata_json=_canonical_raw_metadata(
                        message,
                        raw_export=export_writer,
                        raw_message=raw_messages_by_id.get(message_id),
                    ),
                    fetched_at=fetched_at,
                    classification_status="unclassified",
                    archive_pointer_id=export_writer.run_id,
                    is_archived_stub=False,
                    text_archived=False,
                    caption_archived=False,
                    metadata_archived=False,
                    created_at=fetched_at,
                    updated_at=fetched_at,
                )
            )
            inserted_count += 1
            seen_message_ids.add(message_id)
            existing_messages[message_id] = ExistingSourceMessage(
                id=source_message_id,
                raw_source_id=None,
            )
        return inserted_count, duplicate_count

    async def _apply_media_policy(
        self,
        source: ResolvedTelegramSource,
        writer: TelegramRawExportWriter,
        messages: list[TelegramMessage],
        *,
        media_policy: dict[str, Any],
    ) -> list[TelegramMessage]:
        if media_policy["enabled"] is not True:
            return messages
        updated: list[TelegramMessage] = []
        for message in messages:
            if not message.has_media:
                updated.append(message)
                continue
            downloaded = await self.client.download_message_media(
                source,
                message_id=message.telegram_message_id,
                destination_dir=writer.output_dir / "media" / str(message.telegram_message_id),
                allowed_media_types=media_policy["types"],
                max_file_size_bytes=media_policy["max_file_size_bytes"],
            )
            metadata = dict(message.media_metadata_json or {})
            metadata["raw_export_download"] = asdict(downloaded)
            updated.append(replace(message, media_metadata_json=metadata))
        return updated

    def _mirror_catalog_source(
        self,
        source: MonitoredSourceRecord,
        source_message_id: str,
        message: TelegramMessage,
    ) -> None:
        raw_text = _catalog_raw_text(message)
        raw_source = self.catalog_sources.upsert_source(
            source_type="telegram_message",
            origin=_catalog_origin(source),
            external_id=str(message.telegram_message_id),
            raw_text=raw_text,
            url=_message_url(source, message.telegram_message_id),
            title=_catalog_title(source, message.telegram_message_id),
            author=message.sender_display or message.sender_id,
            published_at=message.message_date,
            fetched_at=utc_now(),
            metadata_json={
                "monitored_source_id": source.id,
                "source_purpose": source.source_purpose,
                "telegram_message_id": message.telegram_message_id,
                "reply_to_message_id": message.reply_to_message_id,
                "thread_id": message.thread_id,
                "has_media": message.has_media,
                "media_metadata": message.media_metadata_json,
                "forward_metadata": message.forward_metadata_json,
                "raw_metadata": message.raw_metadata_json,
            },
        )
        self.session.execute(
            update(source_messages_table)
            .where(source_messages_table.c.id == source_message_id)
            .values(raw_source_id=raw_source.id, updated_at=utc_now())
        )
        if raw_text:
            chunks = self.catalog_sources.replace_parsed_chunks(
                raw_source.id,
                chunks=[raw_text],
                parser_name="telegram-message-text",
                parser_version="1",
            )
            if self.settings.get("catalog_extract_telegram_message_text_enabled") is True:
                for chunk in chunks:
                    self.scheduler.enqueue(
                        job_type="extract_catalog_facts",
                        scope_type="parser",
                        priority="low",
                        scope_id=chunk.id,
                        monitored_source_id=source.id,
                        source_message_id=source_message_id,
                        idempotency_key=f"extract-catalog-facts:{chunk.id}",
                        payload_json={
                            "source_id": chunk.source_id,
                            "chunk_id": chunk.id,
                            "extractor_version": "telegram-message-runtime",
                            "source_message_id": source_message_id,
                            "monitored_source_id": source.id,
                        },
                    )
            self._enqueue_external_page_fetches(
                source=source,
                source_message_id=source_message_id,
                raw_source_id=raw_source.id,
                text=raw_text,
            )
        if _is_downloadable_document(message.media_metadata_json):
            self.scheduler.enqueue(
                job_type="download_artifact",
                scope_type="telegram_source",
                priority="high",
                scope_id=source.id,
                userbot_account_id=source.assigned_userbot_account_id,
                monitored_source_id=source.id,
                source_message_id=source_message_id,
                idempotency_key=f"telegram-document:{source_message_id}",
                payload_json={
                    "source_id": raw_source.id,
                    "source_message_id": source_message_id,
                    "telegram_message_id": message.telegram_message_id,
                    "media_metadata": message.media_metadata_json,
                },
            )

    def _enqueue_external_page_fetches(
        self,
        *,
        source: MonitoredSourceRecord,
        source_message_id: str,
        raw_source_id: str,
        text: str,
    ) -> None:
        if self.settings.get("external_page_ingestion_enabled") is False:
            return
        allowed_domains = _allowed_external_domains(
            self.settings.get("external_page_allowed_domains")
        )
        for url in _external_page_urls(text, allowed_domains=allowed_domains):
            digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
            self.scheduler.enqueue(
                job_type="fetch_external_page",
                scope_type="parser",
                scope_id=raw_source_id,
                monitored_source_id=source.id,
                source_message_id=source_message_id,
                idempotency_key=f"external-page:{digest}",
                payload_json={
                    "url": url,
                    "parent_source_id": raw_source_id,
                    "source_message_id": source_message_id,
                    "monitored_source_id": source.id,
                },
            )

    def _record_scheduler_checkpoint(self, job_id: str, result: PollResult) -> None:
        self.session.execute(
            update(scheduler_jobs_table)
            .where(scheduler_jobs_table.c.id == job_id)
            .values(
                checkpoint_before_json={"message_id": result.checkpoint_before},
                checkpoint_after_json={"message_id": result.checkpoint_after},
                result_summary_json={
                    "status": result.status,
                    "fetched_count": result.fetched_count,
                    "inserted_count": result.inserted_count,
                    "duplicate_count": result.duplicate_count,
                },
                updated_at=utc_now(),
            )
        )

    def _record_raw_export_checkpoint(self, job_id: str, result: RawExportResult) -> None:
        self.session.execute(
            update(scheduler_jobs_table)
            .where(scheduler_jobs_table.c.id == job_id)
            .values(
                checkpoint_before_json={"message_id": result.checkpoint_before},
                checkpoint_after_json={"message_id": result.checkpoint_after},
                result_summary_json=asdict(result),
                updated_at=utc_now(),
            )
        )

    def _require_source(self, source_id: str) -> MonitoredSourceRecord:
        source = self.sources.get(source_id)
        if source is None:
            raise KeyError(source_id)
        return source


def _checkpoint_after(
    checkpoint_before: int | None,
    messages: list[TelegramMessage],
) -> int | None:
    message_ids = [message.telegram_message_id for message in messages]
    if checkpoint_before is not None:
        message_ids.append(checkpoint_before)
    if not message_ids:
        return None
    return max(message_ids)


def _start_after_date(source: MonitoredSourceRecord, now: datetime) -> datetime | None:
    if source.checkpoint_message_id is not None:
        return None
    if source.start_mode != "recent_days" or source.start_recent_days is None:
        return None
    if source.start_recent_days <= 0:
        return None
    return now - timedelta(days=source.start_recent_days)


def _export_range_cursor(
    source: MonitoredSourceRecord,
    config: dict[str, Any],
    now: datetime,
) -> ExportRangeCursor:
    mode = str(config.get("mode") or "source_start")
    batch_size = max(1, min(int(config.get("batch_size") or 1000), 5000))
    limit = config.get("max_messages")
    max_messages = int(limit) if limit is not None else None
    if mode == "source_start":
        return _source_start_export_range(source, now, batch_size, max_messages)
    if mode == "from_beginning":
        return ExportRangeCursor(mode, None, None, None, max_messages, batch_size)
    if mode == "recent_days":
        recent_days = int(config.get("recent_days") or 0)
        return ExportRangeCursor(
            mode,
            None,
            None,
            now - timedelta(days=recent_days),
            max_messages,
            batch_size,
        )
    if mode == "since_date":
        return ExportRangeCursor(
            mode,
            None,
            None,
            _parse_export_since_date(config.get("since_date")),
            max_messages,
            batch_size,
        )
    if mode == "from_message":
        return ExportRangeCursor(
            mode,
            None,
            int(config["message_id"]),
            None,
            max_messages,
            batch_size,
        )
    if mode == "after_message":
        return ExportRangeCursor(
            mode,
            int(config["message_id"]),
            None,
            None,
            max_messages,
            batch_size,
        )
    if mode == "since_checkpoint":
        if source.checkpoint_message_id is None:
            return ExportRangeCursor(
                mode,
                None,
                None,
                None,
                max_messages,
                batch_size,
                skip_reason="checkpoint_missing",
            )
        return ExportRangeCursor(
            mode,
            source.checkpoint_message_id,
            None,
            None,
            max_messages,
            batch_size,
        )
    if mode == "from_now":
        return ExportRangeCursor(
            mode,
            None,
            None,
            None,
            max_messages,
            batch_size,
            skip_reason="from_now_has_no_historical_export",
        )
    raise ValueError(f"Unsupported raw export range mode: {mode}")


def _source_start_export_range(
    source: MonitoredSourceRecord,
    now: datetime,
    batch_size: int,
    max_messages: int | None,
) -> ExportRangeCursor:
    if source.start_mode == "from_beginning":
        return ExportRangeCursor("source_start", None, None, None, max_messages, batch_size)
    if source.start_mode == "from_message" and source.start_message_id is not None:
        return ExportRangeCursor(
            "source_start",
            None,
            source.start_message_id,
            None,
            max_messages,
            batch_size,
        )
    if source.start_mode == "recent_days" and source.start_recent_days is not None:
        return ExportRangeCursor(
            "source_start",
            None,
            None,
            now - timedelta(days=source.start_recent_days),
            max_messages,
            batch_size,
        )
    return ExportRangeCursor(
        "source_start",
        None,
        None,
        None,
        max_messages,
        batch_size,
        skip_reason="source_start_from_now_has_no_historical_export",
    )


def _parse_export_since_date(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _range_metadata(cursor: ExportRangeCursor) -> dict[str, Any]:
    return {
        "mode": cursor.mode,
        "after_message_id": cursor.after_message_id,
        "from_message_id": cursor.from_message_id,
        "after_date": cursor.after_date.isoformat() if cursor.after_date is not None else None,
        "limit": cursor.limit,
        "batch_size": cursor.batch_size,
        "skip_reason": cursor.skip_reason,
    }


def _media_policy(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "enabled": bool(config.get("enabled", False)),
        "types": [str(item) for item in config.get("types") or ["document"]],
        "max_file_size_bytes": config.get("max_file_size_bytes"),
    }


def _normalize_text(message: TelegramMessage) -> str | None:
    combined = "\n".join(part for part in (message.text, message.caption) if part)
    normalized = " ".join(combined.lower().split())
    return normalized or None


def _catalog_raw_text(message: TelegramMessage) -> str | None:
    value = "\n".join(part for part in (message.text, message.caption) if part)
    return value or None


def _canonical_raw_metadata(
    message: TelegramMessage,
    *,
    raw_export: TelegramRawExportResult | TelegramRawExportWriter | None,
    raw_message: TelegramRawExportMessage | None,
) -> dict[str, Any]:
    metadata = dict(message.raw_metadata_json or {})
    metadata.setdefault("sender_display", message.sender_display)
    if raw_export is not None and raw_message is not None:
        metadata["raw_export"] = {
            "run_id": raw_export.run_id,
            "row_index": raw_message.row_index,
            "result_json_path": str(raw_export.result_json_path),
            "messages_jsonl_path": str(raw_export.messages_jsonl_path),
            "messages_parquet_path": str(raw_export.messages_parquet_path),
        }
        metadata["raw_message_json"] = raw_message.raw_message
    return metadata


def _catalog_origin(source: MonitoredSourceRecord) -> str:
    return f"telegram:{source.username or source.telegram_id or source.input_ref}"


def _message_url(source: MonitoredSourceRecord, message_id: int) -> str | None:
    if source.username:
        return f"https://t.me/{source.username}/{message_id}"
    return None


def _catalog_title(source: MonitoredSourceRecord, message_id: int) -> str:
    title = source.title or source.username or source.input_ref
    return f"{title} #{message_id}"


def _is_downloadable_document(media_metadata: Any) -> bool:
    if not isinstance(media_metadata, dict):
        return False
    document = media_metadata.get("document")
    return isinstance(document, dict) and document.get("downloadable") is True


_URL_RE = re.compile(r"https?://[^\s<>()\"']+")


def _external_page_urls(text: str, *, allowed_domains: set[str]) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for match in _URL_RE.finditer(text):
        normalized = _normalize_external_url(match.group(0).rstrip(".,;:!?)]}"))
        if normalized is None:
            continue
        host = urlsplit(normalized).netloc.lower()
        if host not in allowed_domains:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        urls.append(normalized)
    return urls


def _normalize_external_url(url: str) -> str | None:
    parsed = urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/") or "/",
            parsed.query,
            "",
        )
    )


def _allowed_external_domains(value: Any) -> set[str]:
    if not isinstance(value, list):
        return {"telegra.ph"}
    domains = {item.strip().lower() for item in value if isinstance(item, str) and item.strip()}
    return domains or {"telegra.ph"}


def _resolved_source_from_record(source: MonitoredSourceRecord) -> ResolvedTelegramSource:
    return ResolvedTelegramSource(
        input_ref=source.input_ref,
        source_kind=source.source_kind,
        telegram_id=source.telegram_id,
        username=source.username,
        title=source.title,
    )
