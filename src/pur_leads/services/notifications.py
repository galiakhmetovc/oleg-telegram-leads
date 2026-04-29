"""Notification policy and event journal behavior."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.models.notifications import notification_events_table
from pur_leads.repositories.leads import LeadClusterRecord, LeadEventRecord
from pur_leads.services.settings import SettingsService


@dataclass(frozen=True)
class NotificationPolicyDecision:
    should_enqueue: bool
    notification_type: str
    notification_policy: str
    status: str
    reason: str | None
    dedupe_key: str


class NotificationPolicyService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def evaluate_lead_event(
        self,
        *,
        settings: SettingsService,
        cluster: LeadClusterRecord,
        event: LeadEventRecord,
        notify_retro_requested: bool = False,
    ) -> NotificationPolicyDecision:
        notification_type = _notification_type(event)
        dedupe_key = f"lead-notify:{cluster.id}"
        reason = self._suppression_reason(
            settings=settings,
            cluster=cluster,
            event=event,
            notify_retro_requested=notify_retro_requested,
        )
        if reason is not None:
            return NotificationPolicyDecision(
                should_enqueue=False,
                notification_type=notification_type,
                notification_policy="suppressed",
                status="suppressed",
                reason=reason,
                dedupe_key=dedupe_key,
            )
        return NotificationPolicyDecision(
            should_enqueue=True,
            notification_type=notification_type,
            notification_policy="immediate",
            status="queued",
            reason=None,
            dedupe_key=dedupe_key,
        )

    def record_lead_policy_event(
        self,
        *,
        decision: NotificationPolicyDecision,
        cluster: LeadClusterRecord,
        event: LeadEventRecord,
        target_ref: str | None,
        payload_json: Any,
    ) -> str:
        now = utc_now()
        event_id = new_id()
        self.session.execute(
            insert(notification_events_table).values(
                id=event_id,
                channel="telegram",
                notification_type=decision.notification_type,
                notification_policy=decision.notification_policy,
                status=decision.status,
                dedupe_key=decision.dedupe_key,
                lead_cluster_id=cluster.id,
                lead_event_id=event.id,
                scheduler_job_id=None,
                monitored_source_id=event.monitored_source_id,
                source_message_id=event.source_message_id,
                target_ref=target_ref,
                provider_message_id=None,
                suppressed_reason=decision.reason,
                error=None,
                payload_json=payload_json,
                created_at=now,
                queued_at=now if decision.status == "queued" else None,
                sent_at=None,
                updated_at=now,
            )
        )
        self.session.commit()
        return event_id

    def mark_queued_job(self, notification_event_id: str, scheduler_job_id: str) -> None:
        now = utc_now()
        self.session.execute(
            update(notification_events_table)
            .where(notification_events_table.c.id == notification_event_id)
            .values(scheduler_job_id=scheduler_job_id, updated_at=now)
        )
        self.session.commit()

    def mark_sent(self, notification_event_id: str, provider_result: Any) -> None:
        now = utc_now()
        self.session.execute(
            update(notification_events_table)
            .where(notification_events_table.c.id == notification_event_id)
            .values(
                status="sent",
                provider_message_id=_provider_message_id(provider_result),
                sent_at=now,
                updated_at=now,
            )
        )
        self.session.commit()

    def mark_failed(self, notification_event_id: str, error: str) -> None:
        now = utc_now()
        self.session.execute(
            update(notification_events_table)
            .where(notification_events_table.c.id == notification_event_id)
            .values(status="failed", error=error, updated_at=now)
        )
        self.session.commit()

    def _suppression_reason(
        self,
        *,
        settings: SettingsService,
        cluster: LeadClusterRecord,
        event: LeadEventRecord,
        notify_retro_requested: bool,
    ) -> str | None:
        if settings.get("telegram_lead_notifications_enabled") is False:
            return "notifications_disabled"
        chat_id = settings.get("telegram_lead_notification_chat_id")
        if not isinstance(chat_id, str) or not chat_id.strip():
            return "notification_chat_missing"
        if event.detection_mode == "live" and settings.get("notify_live_leads") is False:
            return "live_notifications_disabled"
        if (
            event.detection_mode == "retro_research"
            and not notify_retro_requested
            and settings.get("notify_retro_leads") is not True
        ):
            return "retro_web_only"
        if (
            event.detection_mode == "reclassification"
            and settings.get("notify_reclassification_leads") is not True
        ):
            return "reclassification_web_only"
        if self._has_active_immediate_cluster_notification(cluster.id):
            return "cluster_already_has_notification"
        if (
            cluster.last_notified_at is not None
            and settings.get("lead_cluster_notify_on_update") is not True
        ):
            return "cluster_update_suppressed"
        if event.decision == "maybe" and settings.get("notify_maybe") is not True:
            if not _is_high_value_exception(settings, event):
                return "maybe_web_only"
        if event.decision == "lead" and settings.get("notify_leads") is False:
            return "lead_notifications_disabled"
        min_confidence = _float_setting(settings, "lead_notify_min_confidence", 0.7)
        if event.confidence < min_confidence and not _is_high_value_exception(settings, event):
            return "confidence_below_threshold"
        return None

    def _has_active_immediate_cluster_notification(self, cluster_id: str) -> bool:
        row = (
            self.session.execute(
                select(notification_events_table.c.id).where(
                    notification_events_table.c.channel == "telegram",
                    notification_events_table.c.notification_policy == "immediate",
                    notification_events_table.c.lead_cluster_id == cluster_id,
                    notification_events_table.c.status.in_(["queued", "sent"]),
                )
            )
            .mappings()
            .first()
        )
        return row is not None


def _notification_type(event: LeadEventRecord) -> str:
    if event.detection_mode == "retro_research":
        return "retro_lead"
    if event.detection_mode == "reclassification":
        return "reclassification_lead"
    if event.decision == "maybe":
        return "maybe"
    return "lead"


def _is_high_value_exception(settings: SettingsService, event: LeadEventRecord) -> bool:
    if settings.get("notify_high_value_low_confidence") is not True:
        return False
    if settings.get("high_value_notify_enabled") is not True:
        return False
    value_score = event.commercial_value_score
    if value_score is None:
        return False
    negative_score = event.negative_score
    if negative_score is not None and negative_score > _float_setting(
        settings, "high_value_negative_score_max", 0.35
    ):
        return False
    return event.confidence >= _float_setting(
        settings, "lead_notify_high_value_min_confidence", 0.45
    ) and value_score >= _float_setting(settings, "high_value_notify_threshold", 0.75)


def _float_setting(settings: SettingsService, key: str, default: float) -> float:
    value = settings.get(key)
    if isinstance(value, int | float):
        return float(value)
    return default


def _provider_message_id(provider_result: Any) -> str | None:
    if isinstance(provider_result, dict):
        value = provider_result.get("message_id")
        return str(value) if value is not None else None
    value = getattr(provider_result, "message_id", None)
    return str(value) if value is not None else None
