"""Telegram source polling and message persistence."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.integrations.telegram.client import TelegramClientPort
from pur_leads.integrations.telegram.types import ResolvedTelegramSource, TelegramMessage
from pur_leads.models.scheduler import scheduler_jobs_table
from pur_leads.models.telegram_sources import source_messages_table
from pur_leads.repositories.telegram_sources import MonitoredSourceRecord, TelegramSourceRepository


@dataclass(frozen=True)
class PollResult:
    status: str
    fetched_count: int
    inserted_count: int
    duplicate_count: int
    checkpoint_before: int | None
    checkpoint_after: int | None
    reason: str | None = None


class TelegramPollingWorker:
    def __init__(self, session: Session, client: TelegramClientPort) -> None:
        self.session = session
        self.client = client
        self.sources = TelegramSourceRepository(session)

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
        existing_message_ids = self._existing_message_ids(source.id)
        seen_message_ids: set[int] = set()
        inserted_count = 0
        duplicate_count = 0

        for message in messages:
            message_id = message.telegram_message_id
            if message_id in existing_message_ids or message_id in seen_message_ids:
                duplicate_count += 1
                continue

            self.session.execute(
                insert(source_messages_table).values(
                    id=new_id(),
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
                    classification_status="pending",
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

        checkpoint_after = _checkpoint_after(checkpoint_before, messages)
        self.sources.update(
            source.id,
            checkpoint_message_id=checkpoint_after,
            checkpoint_date=now,
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

    def _existing_message_ids(self, source_id: str) -> set[int]:
        rows = self.session.execute(
            select(source_messages_table.c.telegram_message_id).where(
                source_messages_table.c.monitored_source_id == source_id
            )
        ).all()
        return {row[0] for row in rows}

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


def _resolved_source_from_record(source: MonitoredSourceRecord) -> ResolvedTelegramSource:
    return ResolvedTelegramSource(
        input_ref=source.input_ref,
        source_kind=source.source_kind,
        telegram_id=source.telegram_id,
        username=source.username,
        title=source.title,
    )
