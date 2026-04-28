"""Lead event and match recording behavior."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.models.catalog import classifier_snapshot_entries_table
from pur_leads.models.leads import lead_matches_table
from pur_leads.models.telegram_sources import source_messages_table
from pur_leads.repositories.leads import (
    FeedbackEventRecord,
    LeadClusterRecord,
    LeadEventRecord,
    LeadRepository,
)


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

    def assign_event_to_cluster(
        self,
        event_id: str,
        *,
        window_minutes: int,
    ) -> LeadClusterRecord:
        event = self.repository.get_event(event_id)
        if event is None:
            raise KeyError(event_id)
        if event.lead_cluster_id is not None:
            cluster = self.repository.get_cluster(event.lead_cluster_id)
            if cluster is None:
                raise KeyError(event.lead_cluster_id)
            return cluster

        message = self._message(event.source_message_id)
        message_at = message["message_date"]
        category_id = self._event_category_id(event.id)
        existing_cluster = self.repository.find_compatible_cluster(
            monitored_source_id=event.monitored_source_id,
            sender_id=event.sender_id,
            category_id=category_id,
            window_start=message_at - timedelta(minutes=window_minutes),
            message_at=message_at,
        )
        if existing_cluster is not None:
            return self._merge_event_into_cluster(
                cluster=existing_cluster,
                event=event,
                message_at=message_at,
                window_minutes=window_minutes,
            )
        return self._create_cluster_for_event(
            event=event,
            message_at=message_at,
            category_id=category_id,
        )

    def record_feedback(
        self,
        *,
        target_type: str,
        target_id: str,
        action: str,
        created_by: str,
        reason_code: str | None = None,
        feedback_scope: str | None = None,
        learning_effect: str | None = None,
        application_status: str = "recorded",
        applied_entity_type: str | None = None,
        applied_entity_id: str | None = None,
        comment: str | None = None,
        metadata_json: Any | None = None,
    ) -> FeedbackEventRecord:
        feedback = self._create_feedback_event(
            target_type=target_type,
            target_id=target_id,
            action=action,
            created_by=created_by,
            reason_code=reason_code,
            feedback_scope=feedback_scope,
            learning_effect=learning_effect,
            application_status=application_status,
            applied_entity_type=applied_entity_type,
            applied_entity_id=applied_entity_id,
            comment=comment,
            metadata_json=metadata_json,
        )
        self.session.commit()
        return feedback

    def apply_cluster_action(
        self,
        cluster_id: str,
        *,
        action: str,
        actor: str,
        reason_code: str | None = None,
        comment: str | None = None,
        snoozed_until: datetime | None = None,
        duplicate_of_cluster_id: str | None = None,
        lead_event_id: str | None = None,
    ) -> FeedbackEventRecord:
        cluster = self.repository.get_cluster(cluster_id)
        if cluster is None:
            raise KeyError(cluster_id)
        if action not in _CLUSTER_FEEDBACK_ACTIONS:
            raise ValueError(f"Unsupported cluster action: {action}")
        if action == "not_lead" and not reason_code:
            raise ValueError("reason_code is required for not_lead feedback")

        now = utc_now()
        metadata: dict[str, Any] = {}
        if action == "lead_confirmed":
            self.repository.update_cluster(
                cluster.id,
                cluster_status="in_work",
                review_status="confirmed",
                updated_at=now,
            )
        elif action == "not_lead":
            self.repository.update_cluster(
                cluster.id,
                cluster_status="not_lead",
                review_status="rejected",
                updated_at=now,
            )
        elif action == "maybe":
            self.repository.update_cluster(
                cluster.id,
                cluster_status="maybe",
                review_status="needs_more_info",
                updated_at=now,
            )
        elif action == "snooze":
            if snoozed_until is None:
                raise ValueError("snoozed_until is required for snooze")
            metadata["snoozed_until"] = snoozed_until.isoformat()
            self.repository.update_cluster(
                cluster.id,
                cluster_status="snoozed",
                snoozed_until=snoozed_until,
                updated_at=now,
            )
        elif action == "duplicate":
            if duplicate_of_cluster_id is None:
                raise ValueError("duplicate_of_cluster_id is required for duplicate")
            if self.repository.get_cluster(duplicate_of_cluster_id) is None:
                raise KeyError(duplicate_of_cluster_id)
            metadata["duplicate_of_cluster_id"] = duplicate_of_cluster_id
            self.repository.update_cluster(
                cluster.id,
                cluster_status="duplicate",
                review_status="rejected",
                duplicate_of_cluster_id=duplicate_of_cluster_id,
                updated_at=now,
            )
            self.repository.create_cluster_action(
                action_type="mark_duplicate",
                from_cluster_id=cluster.id,
                to_cluster_id=duplicate_of_cluster_id,
                source_message_id=cluster.primary_source_message_id,
                lead_event_id=cluster.primary_lead_event_id,
                actor=actor,
                reason=reason_code,
                details_json=metadata,
                created_at=now,
            )
        elif action == "mark_context_only":
            if lead_event_id is None:
                raise ValueError("lead_event_id is required for mark_context_only")
            event = self.repository.get_event(lead_event_id)
            if event is None:
                raise KeyError(lead_event_id)
            if event.lead_cluster_id != cluster.id:
                raise ValueError("lead_event_id does not belong to cluster")
            self.repository.update_event(
                event.id,
                event_status="context_only",
                event_review_status="confirmed",
            )
            self.repository.update_cluster_member_by_event(
                cluster_id=cluster.id,
                lead_event_id=event.id,
                member_role="context",
                merge_reason=reason_code or "context_only",
            )
            self.repository.create_cluster_action(
                action_type="mark_context_only",
                from_cluster_id=None,
                to_cluster_id=cluster.id,
                source_message_id=event.source_message_id,
                lead_event_id=event.id,
                actor=actor,
                reason=reason_code,
                details_json={"reason_code": reason_code},
                created_at=now,
            )

        feedback = self._create_feedback_event(
            target_type="lead_cluster",
            target_id=cluster.id,
            action=action,
            created_by=actor,
            reason_code=reason_code,
            feedback_scope=None,
            learning_effect=None,
            application_status="applied",
            applied_entity_type="lead_cluster",
            applied_entity_id=cluster.id,
            comment=comment,
            metadata_json=metadata,
        )
        self.session.commit()
        return feedback

    def _create_cluster_for_event(
        self,
        *,
        event: LeadEventRecord,
        message_at: datetime,
        category_id: str | None,
    ) -> LeadClusterRecord:
        now = utc_now()
        cluster = self.repository.create_cluster(
            monitored_source_id=event.monitored_source_id,
            chat_id=event.chat_id,
            primary_sender_id=event.sender_id,
            primary_sender_name=event.sender_name,
            primary_lead_event_id=event.id,
            primary_source_message_id=event.source_message_id,
            category_id=category_id,
            summary=event.reason or event.message_text,
            cluster_status=_cluster_status_for_decision(event.decision),
            review_status="unreviewed",
            work_outcome="none",
            first_message_at=message_at,
            last_message_at=message_at,
            message_count=1,
            lead_event_count=1,
            confidence_max=event.confidence,
            commercial_value_score_max=event.commercial_value_score,
            negative_score_min=event.negative_score,
            dedupe_key=_dedupe_key(event.monitored_source_id, event.sender_id, category_id),
            merge_strategy="none",
            merge_reason=None,
            last_notified_at=None,
            notify_update_count=0,
            snoozed_until=None,
            duplicate_of_cluster_id=None,
            primary_task_id=None,
            converted_entity_type=None,
            converted_entity_id=None,
            crm_candidate_count=0,
            crm_conversion_action_id=None,
            created_at=now,
            updated_at=now,
        )
        self.repository.update_event(event.id, lead_cluster_id=cluster.id)
        self.repository.create_cluster_member(
            lead_cluster_id=cluster.id,
            source_message_id=event.source_message_id,
            lead_event_id=event.id,
            member_role="primary",
            added_by="system",
            merge_score=1.0,
            merge_reason="cluster_primary_event",
            created_at=now,
        )
        self.session.commit()
        return cluster

    def _merge_event_into_cluster(
        self,
        *,
        cluster: LeadClusterRecord,
        event: LeadEventRecord,
        message_at: datetime,
        window_minutes: int,
    ) -> LeadClusterRecord:
        now = utc_now()
        reason = "same_source_sender_category_window"
        self.repository.update_event(event.id, lead_cluster_id=cluster.id)
        self.repository.create_cluster_member(
            lead_cluster_id=cluster.id,
            source_message_id=event.source_message_id,
            lead_event_id=event.id,
            member_role="trigger",
            added_by="system",
            merge_score=1.0,
            merge_reason=reason,
            created_at=now,
        )
        updated_cluster = self.repository.update_cluster(
            cluster.id,
            first_message_at=_min_datetime(cluster.first_message_at, message_at),
            last_message_at=_max_datetime(cluster.last_message_at, message_at),
            message_count=cluster.message_count + 1,
            lead_event_count=cluster.lead_event_count + 1,
            confidence_max=_max_optional(cluster.confidence_max, event.confidence),
            commercial_value_score_max=_max_optional(
                cluster.commercial_value_score_max, event.commercial_value_score
            ),
            negative_score_min=_min_optional(cluster.negative_score_min, event.negative_score),
            merge_strategy="auto",
            merge_reason=reason,
            updated_at=now,
        )
        self.repository.create_cluster_action(
            action_type="auto_merge",
            from_cluster_id=None,
            to_cluster_id=cluster.id,
            source_message_id=event.source_message_id,
            lead_event_id=event.id,
            actor="system",
            reason=reason,
            details_json={
                "window_minutes": window_minutes,
                "merge_score": 1.0,
                "strategy": "same monitored source, sender, category, and time window",
            },
            created_at=now,
        )
        self.session.commit()
        return updated_cluster

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

    def _create_feedback_event(
        self,
        *,
        target_type: str,
        target_id: str,
        action: str,
        created_by: str,
        reason_code: str | None,
        feedback_scope: str | None,
        learning_effect: str | None,
        application_status: str,
        applied_entity_type: str | None,
        applied_entity_id: str | None,
        comment: str | None,
        metadata_json: Any | None,
    ) -> FeedbackEventRecord:
        if action == "not_lead" and not reason_code:
            raise ValueError("reason_code is required for not_lead feedback")
        now = utc_now()
        return self.repository.create_feedback_event(
            target_type=target_type,
            target_id=target_id,
            action=action,
            reason_code=reason_code,
            feedback_scope=feedback_scope or _default_feedback_scope(action),
            learning_effect=learning_effect or _default_learning_effect(action),
            application_status=application_status,
            applied_entity_type=applied_entity_type,
            applied_entity_id=applied_entity_id,
            applied_at=now if application_status == "applied" else None,
            comment=comment,
            created_by=created_by,
            created_at=now,
            metadata_json=metadata_json or {},
        )

    def _event_category_id(self, event_id: str) -> str | None:
        row = (
            self.session.execute(
                select(lead_matches_table.c.category_id)
                .where(
                    lead_matches_table.c.lead_event_id == event_id,
                    lead_matches_table.c.category_id.is_not(None),
                )
                .order_by(lead_matches_table.c.score.desc())
            )
            .mappings()
            .first()
        )
        return row["category_id"] if row is not None else None


def _message_text(message: dict[str, Any]) -> str | None:
    parts = [part for part in (message.get("text"), message.get("caption")) if part]
    return "\n".join(parts) if parts else None


_CLUSTER_FEEDBACK_ACTIONS = {
    "lead_confirmed",
    "not_lead",
    "maybe",
    "snooze",
    "duplicate",
    "mark_context_only",
}

_COMMERCIAL_OUTCOME_ACTIONS = {
    "commercial_no_answer",
    "commercial_too_expensive",
    "commercial_bought_elsewhere",
    "commercial_postponed",
    "commercial_not_region",
}


def _default_feedback_scope(action: str) -> str:
    if action in _COMMERCIAL_OUTCOME_ACTIONS:
        return "crm_outcome"
    if action in {"duplicate", "mark_context_only"}:
        return "clustering"
    if action in {"maybe", "snooze"}:
        return "none"
    return "classifier"


def _default_learning_effect(action: str) -> str:
    if action in _COMMERCIAL_OUTCOME_ACTIONS or action in {"maybe", "snooze"}:
        return "no_classifier_learning"
    if action in {"duplicate", "mark_context_only"}:
        return "cluster_training"
    if action == "lead_confirmed":
        return "positive_example"
    if action == "not_lead":
        return "negative_example"
    return "no_classifier_learning"


def _cluster_status_for_decision(decision: str) -> str:
    if decision == "maybe":
        return "maybe"
    if decision == "not_lead":
        return "not_lead"
    return "new"


def _dedupe_key(monitored_source_id: str, sender_id: str | None, category_id: str | None) -> str:
    return ":".join(
        [
            monitored_source_id,
            sender_id or "unknown_sender",
            category_id or "unknown_category",
        ]
    )


def _max_optional(left: float | None, right: float | None) -> float | None:
    values = [value for value in (left, right) if value is not None]
    return max(values) if values else None


def _min_optional(left: float | None, right: float | None) -> float | None:
    values = [value for value in (left, right) if value is not None]
    return min(values) if values else None


def _max_datetime(left: datetime | None, right: datetime | None) -> datetime | None:
    values = [value for value in (left, right) if value is not None]
    return max(values) if values else None


def _min_datetime(left: datetime | None, right: datetime | None) -> datetime | None:
    values = [value for value in (left, right) if value is not None]
    return min(values) if values else None
