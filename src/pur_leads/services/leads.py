"""Lead event and match recording behavior."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.models.catalog import classifier_snapshot_entries_table
from pur_leads.models.telegram_sources import source_messages_table
from pur_leads.repositories.leads import LeadEventRecord, LeadRepository


@dataclass(frozen=True)
class LeadMatchInput:
    match_type: str
    matched_text: str | None
    score: float
    classifier_snapshot_entry_id: str | None = None
    catalog_item_id: str | None = None
    catalog_term_id: str | None = None
    catalog_offer_id: str | None = None
    category_id: str | None = None


@dataclass(frozen=True)
class LeadDetectionResult:
    decision: str
    detection_mode: str
    confidence: float
    commercial_value_score: float | None = None
    negative_score: float | None = None
    high_value_signals_json: Any = None
    negative_signals_json: Any = None
    notify_reason: str | None = None
    reason: str | None = None
    matches: list[LeadMatchInput] = field(default_factory=list)


class LeadService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = LeadRepository(session)

    def record_detection(
        self,
        *,
        source_message_id: str,
        classifier_version_id: str,
        result: LeadDetectionResult,
    ) -> LeadEventRecord:
        existing = self.repository.find_event_identity(
            source_message_id=source_message_id,
            classifier_version_id=classifier_version_id,
            detection_mode=result.detection_mode,
        )
        if existing is not None:
            return existing

        message = self._message(source_message_id)
        now = utc_now()
        event = self.repository.create_event(
            source_message_id=source_message_id,
            monitored_source_id=message["monitored_source_id"],
            raw_source_id=message["raw_source_id"],
            chat_id=message["monitored_source_id"],
            telegram_message_id=message["telegram_message_id"],
            message_url=None,
            sender_id=message["sender_id"],
            sender_name=None,
            message_text=_message_text(message),
            lead_cluster_id=None,
            detected_at=now,
            classifier_version_id=classifier_version_id,
            decision=result.decision,
            detection_mode=result.detection_mode,
            confidence=result.confidence,
            commercial_value_score=result.commercial_value_score,
            negative_score=result.negative_score,
            high_value_signals_json=result.high_value_signals_json,
            negative_signals_json=result.negative_signals_json,
            notify_reason=result.notify_reason,
            reason=result.reason,
            event_status="active",
            event_review_status="unreviewed",
            duplicate_of_lead_event_id=None,
            is_retro=result.detection_mode == "retro_research",
            original_detected_at=now if result.detection_mode == "retro_research" else None,
            created_at=now,
        )
        for match in result.matches:
            snapshot = self._snapshot_entry(match.classifier_snapshot_entry_id)
            self.repository.create_match(
                lead_event_id=event.id,
                source_message_id=source_message_id,
                classifier_snapshot_entry_id=match.classifier_snapshot_entry_id,
                catalog_item_id=match.catalog_item_id,
                catalog_term_id=match.catalog_term_id,
                catalog_offer_id=match.catalog_offer_id,
                category_id=match.category_id,
                match_type=match.match_type,
                matched_text=match.matched_text,
                score=match.score,
                item_status_at_detection=(
                    snapshot["status_at_build"]
                    if snapshot and snapshot["entry_type"] == "item"
                    else None
                ),
                term_status_at_detection=(
                    snapshot["status_at_build"]
                    if snapshot and snapshot["entry_type"] == "term"
                    else None
                ),
                offer_status_at_detection=(
                    snapshot["status_at_build"]
                    if snapshot and snapshot["entry_type"] == "offer"
                    else None
                ),
                matched_weight=snapshot["weight"] if snapshot else None,
                matched_status_snapshot=(
                    {
                        "entry_type": snapshot["entry_type"],
                        "status_at_build": snapshot["status_at_build"],
                    }
                    if snapshot
                    else None
                ),
                created_at=now,
            )
        self.session.commit()
        return event

    def _message(self, source_message_id: str) -> dict[str, Any]:
        row = (
            self.session.execute(
                select(source_messages_table).where(source_messages_table.c.id == source_message_id)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise KeyError(source_message_id)
        return dict(row)

    def _snapshot_entry(self, entry_id: str | None) -> dict[str, Any] | None:
        if entry_id is None:
            return None
        row = (
            self.session.execute(
                select(classifier_snapshot_entries_table).where(
                    classifier_snapshot_entries_table.c.id == entry_id
                )
            )
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None


def _message_text(message: dict[str, Any]) -> str | None:
    parts = [part for part in (message.get("text"), message.get("caption")) if part]
    return "\n".join(parts) if parts else None
