"""Lead inbox persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.models.leads import lead_events_table, lead_matches_table


@dataclass(frozen=True)
class LeadEventRecord:
    id: str
    source_message_id: str
    monitored_source_id: str
    raw_source_id: str | None
    chat_id: str | None
    telegram_message_id: int
    message_url: str | None
    sender_id: str | None
    sender_name: str | None
    message_text: str | None
    lead_cluster_id: str | None
    detected_at: datetime
    classifier_version_id: str
    decision: str
    detection_mode: str
    confidence: float
    commercial_value_score: float | None
    negative_score: float | None
    high_value_signals_json: Any
    negative_signals_json: Any
    notify_reason: str | None
    reason: str | None
    event_status: str
    event_review_status: str
    duplicate_of_lead_event_id: str | None
    is_retro: bool
    original_detected_at: datetime | None
    created_at: datetime


class LeadRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_event_identity(
        self,
        *,
        source_message_id: str,
        classifier_version_id: str,
        detection_mode: str,
    ) -> LeadEventRecord | None:
        row = (
            self.session.execute(
                select(lead_events_table).where(
                    lead_events_table.c.source_message_id == source_message_id,
                    lead_events_table.c.classifier_version_id == classifier_version_id,
                    lead_events_table.c.detection_mode == detection_mode,
                )
            )
            .mappings()
            .first()
        )
        return LeadEventRecord(**dict(row)) if row is not None else None

    def create_event(self, **values) -> LeadEventRecord:  # type: ignore[no-untyped-def]
        event_id = new_id()
        self.session.execute(insert(lead_events_table).values(id=event_id, **values))
        row = (
            self.session.execute(
                select(lead_events_table).where(lead_events_table.c.id == event_id)
            )
            .mappings()
            .one()
        )
        return LeadEventRecord(**dict(row))

    def create_match(self, **values) -> str:  # type: ignore[no-untyped-def]
        match_id = new_id()
        self.session.execute(insert(lead_matches_table).values(id=match_id, **values))
        return match_id
