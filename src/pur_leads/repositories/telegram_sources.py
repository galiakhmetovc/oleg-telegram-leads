"""Telegram source persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.models.telegram_sources import monitored_sources_table


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
