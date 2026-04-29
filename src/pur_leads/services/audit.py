"""Audit and operational event behavior."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from pur_leads.repositories.audit import AuditRepository

SECRET_KEY_PARTS = ("secret", "token", "api_key", "apikey", "password")
NON_SECRET_TOKEN_KEYS = {
    "cached_tokens",
    "completion_tokens",
    "prompt_tokens",
    "reasoning_tokens",
    "token_estimate",
    "token_usage",
    "token_usage_json",
    "total_tokens",
}
MASK = "***"


class AuditService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = AuditRepository(session)

    def record_change(
        self,
        *,
        actor: str,
        action: str,
        entity_type: str,
        entity_id: str | None = None,
        old_value_json: Any = None,
        new_value_json: Any = None,
    ) -> str:
        audit_id = self.repository.record_change(
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_value_json=mask_secret_values(old_value_json),
            new_value_json=mask_secret_values(new_value_json),
        )
        self.session.commit()
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
        event_id = self.repository.record_event(
            event_type=event_type,
            severity=severity,
            entity_type=entity_type,
            entity_id=entity_id,
            correlation_id=correlation_id,
            message=message,
            details_json=mask_secret_values(details_json),
        )
        self.session.commit()
        return event_id


def mask_secret_values(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            key: MASK if _is_secret_key(key) else mask_secret_values(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [mask_secret_values(item) for item in value]
    return value


def _is_secret_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    if normalized in NON_SECRET_TOKEN_KEYS or normalized.endswith("_token_count"):
        return False
    return any(part in normalized for part in SECRET_KEY_PARTS)
