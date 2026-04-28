"""Telegram source persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.models.scheduler import scheduler_jobs_table
from pur_leads.models.telegram_sources import monitored_sources_table
from pur_leads.models.telegram_sources import (
    source_access_checks_table,
    source_preview_messages_table,
)
from pur_leads.repositories.scheduler import SchedulerJobRecord


@dataclass(frozen=True)
class MonitoredSourceRecord:
    id: str
    source_kind: str
    telegram_id: str | None
    username: str | None
    title: str | None
    invite_link_hash: str | None
    input_ref: str
    source_purpose: str
    assigned_userbot_account_id: str | None
    priority: str
    status: str
    lead_detection_enabled: bool
    catalog_ingestion_enabled: bool
    phase_enabled: bool
    start_mode: str
    start_message_id: int | None
    start_recent_limit: int | None
    start_recent_days: int | None
    historical_backfill_policy: str
    checkpoint_message_id: int | None
    checkpoint_date: datetime | None
    last_preview_at: datetime | None
    preview_message_count: int | None
    next_poll_at: datetime | None
    poll_interval_seconds: int
    last_success_at: datetime | None
    last_error_at: datetime | None
    last_error: str | None
    added_by: str
    activated_by: str | None
    activated_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SourceAccessCheckSummary:
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


@dataclass(frozen=True)
class SourcePreviewMessageRecord:
    id: str
    monitored_source_id: str
    access_check_id: str | None
    telegram_message_id: int
    message_date: datetime
    sender_display: str | None
    text: str | None
    caption: str | None
    has_media: bool
    media_metadata_json: Any
    sort_order: int
    created_at: datetime


class TelegramSourceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, **values) -> MonitoredSourceRecord:  # type: ignore[no-untyped-def]
        source_id = new_id()
        self.session.execute(insert(monitored_sources_table).values(id=source_id, **values))
        return self.get(source_id)  # type: ignore[return-value]

    def get(self, source_id: str) -> MonitoredSourceRecord | None:
        row = (
            self.session.execute(
                select(monitored_sources_table).where(monitored_sources_table.c.id == source_id)
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        return MonitoredSourceRecord(**dict(row))

    def list(self) -> list[MonitoredSourceRecord]:
        rows = (
            self.session.execute(
                select(monitored_sources_table).order_by(
                    monitored_sources_table.c.created_at.desc()
                )
            )
            .mappings()
            .all()
        )
        return [MonitoredSourceRecord(**dict(row)) for row in rows]

    def update(self, source_id: str, **values) -> MonitoredSourceRecord:  # type: ignore[no-untyped-def]
        self.session.execute(
            update(monitored_sources_table)
            .where(monitored_sources_table.c.id == source_id)
            .values(**values)
        )
        record = self.get(source_id)
        if record is None:
            raise KeyError(source_id)
        return record

    def list_access_checks(
        self,
        source_id: str,
        *,
        limit: int = 20,
    ) -> list[SourceAccessCheckSummary]:
        rows = (
            self.session.execute(
                select(source_access_checks_table)
                .where(source_access_checks_table.c.monitored_source_id == source_id)
                .order_by(source_access_checks_table.c.checked_at.desc())
                .limit(limit)
            )
            .mappings()
            .all()
        )
        return [SourceAccessCheckSummary(**dict(row)) for row in rows]

    def list_preview_messages(self, source_id: str) -> list[SourcePreviewMessageRecord]:
        rows = (
            self.session.execute(
                select(source_preview_messages_table)
                .where(source_preview_messages_table.c.monitored_source_id == source_id)
                .order_by(source_preview_messages_table.c.sort_order)
            )
            .mappings()
            .all()
        )
        return [SourcePreviewMessageRecord(**dict(row)) for row in rows]

    def list_jobs(self, source_id: str, *, limit: int = 20) -> list[SchedulerJobRecord]:
        rows = (
            self.session.execute(
                select(scheduler_jobs_table)
                .where(scheduler_jobs_table.c.monitored_source_id == source_id)
                .order_by(scheduler_jobs_table.c.created_at.desc())
                .limit(limit)
            )
            .mappings()
            .all()
        )
        return [SchedulerJobRecord(**dict(row)) for row in rows]
