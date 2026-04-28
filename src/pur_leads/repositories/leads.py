"""Lead inbox persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.models.leads import (
    feedback_events_table,
    lead_cluster_actions_table,
    lead_cluster_members_table,
    lead_clusters_table,
    lead_events_table,
    lead_matches_table,
)


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


@dataclass(frozen=True)
class LeadClusterRecord:
    id: str
    monitored_source_id: str | None
    chat_id: str | None
    primary_sender_id: str | None
    primary_sender_name: str | None
    primary_lead_event_id: str | None
    primary_source_message_id: str | None
    category_id: str | None
    summary: str | None
    cluster_status: str
    review_status: str
    work_outcome: str
    first_message_at: datetime | None
    last_message_at: datetime | None
    message_count: int
    lead_event_count: int
    confidence_max: float | None
    commercial_value_score_max: float | None
    negative_score_min: float | None
    dedupe_key: str | None
    merge_strategy: str
    merge_reason: str | None
    last_notified_at: datetime | None
    notify_update_count: int
    snoozed_until: datetime | None
    duplicate_of_cluster_id: str | None
    primary_task_id: str | None
    converted_entity_type: str | None
    converted_entity_id: str | None
    crm_candidate_count: int
    crm_conversion_action_id: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class FeedbackEventRecord:
    id: str
    target_type: str
    target_id: str
    action: str
    reason_code: str | None
    feedback_scope: str
    learning_effect: str
    application_status: str
    applied_entity_type: str | None
    applied_entity_id: str | None
    applied_at: datetime | None
    comment: str | None
    created_by: str
    created_at: datetime
    metadata_json: Any


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

    def get_event(self, event_id: str) -> LeadEventRecord | None:
        row = (
            self.session.execute(
                select(lead_events_table).where(lead_events_table.c.id == event_id)
            )
            .mappings()
            .first()
        )
        return LeadEventRecord(**dict(row)) if row is not None else None

    def update_event(self, event_id: str, **values) -> LeadEventRecord:  # type: ignore[no-untyped-def]
        self.session.execute(
            update(lead_events_table).where(lead_events_table.c.id == event_id).values(**values)
        )
        event = self.get_event(event_id)
        if event is None:
            raise KeyError(event_id)
        return event

    def create_match(self, **values) -> str:  # type: ignore[no-untyped-def]
        match_id = new_id()
        self.session.execute(insert(lead_matches_table).values(id=match_id, **values))
        return match_id

    def create_cluster(self, **values) -> LeadClusterRecord:  # type: ignore[no-untyped-def]
        cluster_id = new_id()
        self.session.execute(insert(lead_clusters_table).values(id=cluster_id, **values))
        return self.get_cluster(cluster_id)  # type: ignore[return-value]

    def get_cluster(self, cluster_id: str) -> LeadClusterRecord | None:
        row = (
            self.session.execute(
                select(lead_clusters_table).where(lead_clusters_table.c.id == cluster_id)
            )
            .mappings()
            .first()
        )
        return LeadClusterRecord(**dict(row)) if row is not None else None

    def update_cluster(self, cluster_id: str, **values) -> LeadClusterRecord:  # type: ignore[no-untyped-def]
        self.session.execute(
            update(lead_clusters_table)
            .where(lead_clusters_table.c.id == cluster_id)
            .values(**values)
        )
        cluster = self.get_cluster(cluster_id)
        if cluster is None:
            raise KeyError(cluster_id)
        return cluster

    def create_cluster_member(self, **values) -> str:  # type: ignore[no-untyped-def]
        member_id = new_id()
        self.session.execute(insert(lead_cluster_members_table).values(id=member_id, **values))
        return member_id

    def create_cluster_action(self, **values) -> str:  # type: ignore[no-untyped-def]
        action_id = new_id()
        self.session.execute(insert(lead_cluster_actions_table).values(id=action_id, **values))
        return action_id

    def create_feedback_event(self, **values) -> FeedbackEventRecord:  # type: ignore[no-untyped-def]
        feedback_id = new_id()
        self.session.execute(insert(feedback_events_table).values(id=feedback_id, **values))
        row = (
            self.session.execute(
                select(feedback_events_table).where(feedback_events_table.c.id == feedback_id)
            )
            .mappings()
            .one()
        )
        return FeedbackEventRecord(**dict(row))

    def update_cluster_member_by_event(
        self,
        *,
        cluster_id: str,
        lead_event_id: str,
        **values,
    ) -> None:  # type: ignore[no-untyped-def]
        self.session.execute(
            update(lead_cluster_members_table)
            .where(
                lead_cluster_members_table.c.lead_cluster_id == cluster_id,
                lead_cluster_members_table.c.lead_event_id == lead_event_id,
            )
            .values(**values)
        )

    def find_compatible_cluster(
        self,
        *,
        monitored_source_id: str,
        sender_id: str | None,
        category_id: str | None,
        window_start: datetime,
        message_at: datetime,
    ) -> LeadClusterRecord | None:
        category_condition = (
            lead_clusters_table.c.category_id.is_(None)
            if category_id is None
            else lead_clusters_table.c.category_id == category_id
        )
        sender_condition = (
            lead_clusters_table.c.primary_sender_id.is_(None)
            if sender_id is None
            else lead_clusters_table.c.primary_sender_id == sender_id
        )
        row = (
            self.session.execute(
                select(lead_clusters_table)
                .where(
                    lead_clusters_table.c.monitored_source_id == monitored_source_id,
                    sender_condition,
                    category_condition,
                    lead_clusters_table.c.last_message_at >= window_start,
                    lead_clusters_table.c.last_message_at <= message_at,
                    lead_clusters_table.c.cluster_status.in_(
                        ["new", "in_work", "maybe", "snoozed"]
                    ),
                )
                .order_by(lead_clusters_table.c.last_message_at.desc())
            )
            .mappings()
            .first()
        )
        return LeadClusterRecord(**dict(row)) if row is not None else None
