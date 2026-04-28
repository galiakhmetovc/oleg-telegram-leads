"""Audit persistence."""

from __future__ import annotations

from typing import Any

from sqlalchemy import insert
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.models.audit import audit_log_table, operational_events_table


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record_change(
        self,
        *,
        actor: str,
        action: str,
        entity_type: str,
        entity_id: str | None,
        old_value_json: Any,
        new_value_json: Any,
    ) -> str:
        audit_id = new_id()
        self.session.execute(
            insert(audit_log_table).values(
                id=audit_id,
                actor=actor,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                old_value_json=old_value_json,
                new_value_json=new_value_json,
                created_at=utc_now(),
            )
        )
        return audit_id

    def record_event(
        self,
        *,
        event_type: str,
        severity: str,
        message: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
        correlation_id: str | None = None,
        details_json: Any = None,
    ) -> str:
        event_id = new_id()
        self.session.execute(
            insert(operational_events_table).values(
                id=event_id,
                event_type=event_type,
                severity=severity,
                entity_type=entity_type,
                entity_id=entity_id,
                correlation_id=correlation_id,
                message=message,
                details_json=details_json,
                created_at=utc_now(),
            )
        )
        return event_id
