"""Telegram source access and preview jobs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, insert
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.integrations.telegram.client import TelegramClientPort
from pur_leads.integrations.telegram.types import ResolvedTelegramSource, TelegramMessage
from pur_leads.models.telegram_sources import (
    source_access_checks_table,
    source_preview_messages_table,
)
from pur_leads.repositories.telegram_sources import MonitoredSourceRecord, TelegramSourceRepository
from pur_leads.services.audit import AuditService


ACCESS_FAILURE_STATUSES = {
    "needs_join",
    "needs_captcha",
    "private_or_no_access",
    "flood_wait",
    "banned",
    "read_error",
}


@dataclass(frozen=True)
class SourceAccessCheckRecord:
    id: str
    monitored_source_id: str
    userbot_account_id: str | None
    check_type: str
    status: str
    resolved_source_kind: str | None
    resolved_telegram_id: str | None
    resolved_title: str | None
    last_message_id: int | None
    can_read_messages: bool
    can_read_history: bool
    flood_wait_seconds: int | None
    error: str | None
    checked_at: datetime


class TelegramAccessWorker:
    def __init__(self, session: Session, client: TelegramClientPort) -> None:
        self.session = session
        self.client = client
        self.sources = TelegramSourceRepository(session)
        self.audit = AuditService(session)

    async def check_source_access(
        self,
        source_id: str,
        *,
        userbot_account_id: str | None = None,
        check_type: str = "onboarding",
    ) -> SourceAccessCheckRecord:
        source = self._require_source(source_id)
        resolved = await self.client.resolve_source(source.input_ref)
        result = await self.client.check_access(resolved)
        result_source = result.resolved_source or resolved
        now = utc_now()
        check = SourceAccessCheckRecord(
            id=new_id(),
            monitored_source_id=source.id,
            userbot_account_id=userbot_account_id,
            check_type=check_type,
            status=result.status,
            resolved_source_kind=result_source.source_kind,
            resolved_telegram_id=result_source.telegram_id,
            resolved_title=result_source.title,
            last_message_id=result.last_message_id,
            can_read_messages=result.can_read_messages,
            can_read_history=result.can_read_history,
            flood_wait_seconds=result.flood_wait_seconds,
            error=result.error,
            checked_at=now,
        )
        self.session.execute(insert(source_access_checks_table).values(**check.__dict__))

        if result.status == "succeeded" and result.can_read_messages:
            source_status = "preview_ready"
            update_values = {
                "source_kind": result_source.source_kind,
                "telegram_id": result_source.telegram_id,
                "username": result_source.username,
                "title": result_source.title,
                "status": source_status,
                "last_error": None,
                "last_error_at": None,
                "updated_at": now,
            }
        else:
            source_status = _source_status_for_access_result(result.status)
            update_values = {
                "source_kind": result_source.source_kind,
                "telegram_id": result_source.telegram_id,
                "username": result_source.username,
                "title": result_source.title,
                "status": source_status,
                "last_error": result.error,
                "last_error_at": now,
                "updated_at": now,
            }

        self.sources.update(source.id, **update_values)
        if source_status != "preview_ready":
            self.audit.record_event(
                event_type="access_check",
                severity="warning",
                message=f"Telegram access check requires operator action: {source_status}",
                entity_type="monitored_source",
                entity_id=source.id,
                details_json={
                    "input_ref": source.input_ref,
                    "status": result.status,
                    "error": result.error,
                    "flood_wait_seconds": result.flood_wait_seconds,
                },
            )
        self.session.commit()
        return check

    async def fetch_preview(
        self,
        source_id: str,
        *,
        access_check_id: str | None = None,
        limit: int = 20,
    ) -> list[TelegramMessage]:
        source = self._require_source(source_id)
        resolved = _resolved_source_from_record(source)
        messages = await self.client.fetch_preview_messages(resolved, limit=limit)
        now = utc_now()
        self.session.execute(
            delete(source_preview_messages_table).where(
                source_preview_messages_table.c.monitored_source_id == source.id
            )
        )
        for sort_order, message in enumerate(messages):
            self.session.execute(
                insert(source_preview_messages_table).values(
                    id=new_id(),
                    monitored_source_id=source.id,
                    access_check_id=access_check_id,
                    telegram_message_id=message.telegram_message_id,
                    message_date=message.message_date,
                    sender_display=message.sender_display,
                    text=message.text,
                    caption=message.caption,
                    has_media=message.has_media,
                    media_metadata_json=message.media_metadata_json,
                    sort_order=sort_order,
                    created_at=now,
                )
            )
        self.sources.update(
            source.id,
            last_preview_at=now,
            preview_message_count=len(messages),
            updated_at=now,
        )
        self.session.commit()
        return messages

    def _require_source(self, source_id: str) -> MonitoredSourceRecord:
        source = self.sources.get(source_id)
        if source is None:
            raise KeyError(source_id)
        return source


def _source_status_for_access_result(status: str) -> str:
    if status in ACCESS_FAILURE_STATUSES:
        return status
    return "read_error"


def _resolved_source_from_record(source: MonitoredSourceRecord) -> ResolvedTelegramSource:
    return ResolvedTelegramSource(
        input_ref=source.input_ref,
        source_kind=source.source_kind,
        telegram_id=source.telegram_id,
        username=source.username,
        title=source.title,
    )
