"""Telegram source polling and message persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

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
class ExistingSourceMessage:
    id: str
    raw_source_id: str | None


class TelegramPollingWorker:
    def __init__(self, session: Session, client: TelegramClientPort) -> None:
        self.session = session
        self.client = client
        self.sources = TelegramSourceRepository(session)
        self.catalog_sources = CatalogSourceService(session)
        self.scheduler = SchedulerService(session)

    async def poll_monitored_source(
        self,
        source_id: str,
        *,
        scheduler_job_id: str | None = None,
        limit: int = 100,
    ) -> PollResult:
        source = self._require_source(source_id)
        checkpoint_before = source.checkpoint_message_id
        if source.status != "active":
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
        messages = await self.client.fetch_message_batch(
            resolved,
            after_message_id=checkpoint_before,
            limit=limit,
        )
        now = utc_now()
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
                    raw_metadata_json=message.raw_metadata_json,
                    fetched_at=now,
                    classification_status="unclassified",
                    archive_pointer_id=None,
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
        if inserted_count > 0 and source.lead_detection_enabled:
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
            self.catalog_sources.replace_parsed_chunks(
                raw_source.id,
                chunks=[raw_text],
                parser_name="telegram-message-text",
                parser_version="1",
            )
        if _is_downloadable_document(message.media_metadata_json):
            self.scheduler.enqueue(
                job_type="download_artifact",
                scope_type="telegram_source",
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


def _normalize_text(message: TelegramMessage) -> str | None:
    combined = "\n".join(part for part in (message.text, message.caption) if part)
    normalized = " ".join(combined.lower().split())
    return normalized or None


def _catalog_raw_text(message: TelegramMessage) -> str | None:
    value = "\n".join(part for part in (message.text, message.caption) if part)
    return value or None


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


def _resolved_source_from_record(source: MonitoredSourceRecord) -> ResolvedTelegramSource:
    return ResolvedTelegramSource(
        input_ref=source.input_ref,
        source_kind=source.source_kind,
        telegram_id=source.telegram_id,
        username=source.username,
        title=source.title,
    )
