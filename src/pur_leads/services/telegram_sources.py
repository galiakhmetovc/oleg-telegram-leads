"""Telegram source management behavior."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.repositories.telegram_sources import MonitoredSourceRecord, TelegramSourceRepository
from pur_leads.services.audit import AuditService


class CheckpointResetRequiresConfirmation(ValueError):
    """Raised when a checkpoint reset is requested without explicit confirmation."""


@dataclass(frozen=True)
class ParsedSourceInput:
    input_ref: str
    username: str | None
    source_kind: str
    invite_link_hash: str | None = None


class TelegramSourceService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = TelegramSourceRepository(session)
        self.audit = AuditService(session)

    def create_draft(
        self,
        input_ref: str,
        *,
        added_by: str,
        purpose: str = "lead_monitoring",
    ) -> MonitoredSourceRecord:
        parsed = parse_source_input(input_ref, purpose)
        now = utc_now()
        lead_enabled, catalog_enabled = _purpose_flags(purpose)
        source = self.repository.create(
            source_kind=parsed.source_kind,
            telegram_id=None,
            username=parsed.username,
            title=None,
            invite_link_hash=parsed.invite_link_hash,
            input_ref=parsed.input_ref,
            source_purpose=purpose,
            assigned_userbot_account_id=None,
            priority="normal",
            status="draft",
            lead_detection_enabled=lead_enabled,
            catalog_ingestion_enabled=catalog_enabled,
            phase_enabled=True,
            start_mode="from_now",
            start_message_id=None,
            start_recent_limit=None,
            start_recent_days=None,
            historical_backfill_policy="retro_web_only",
            checkpoint_message_id=None,
            checkpoint_date=None,
            last_preview_at=None,
            preview_message_count=None,
            next_poll_at=None,
            poll_interval_seconds=60,
            last_success_at=None,
            last_error_at=None,
            last_error=None,
            added_by=added_by,
            activated_by=None,
            activated_at=None,
            created_at=now,
            updated_at=now,
        )
        self.audit.record_change(
            actor=added_by,
            action="monitored_source.create",
            entity_type="monitored_source",
            entity_id=source.id,
            old_value_json=None,
            new_value_json={
                "input_ref": source.input_ref,
                "purpose": source.source_purpose,
                "status": source.status,
            },
        )
        return source

    def set_status(self, source_id: str, status: str, *, actor: str) -> MonitoredSourceRecord:
        before = self._require(source_id)
        updated = self.repository.update(source_id, status=status, updated_at=utc_now())
        self.audit.record_change(
            actor=actor,
            action="monitored_source.status_update",
            entity_type="monitored_source",
            entity_id=source_id,
            old_value_json={"status": before.status},
            new_value_json={"status": status},
        )
        return updated

    def activate(self, source_id: str, *, actor: str) -> MonitoredSourceRecord:
        before = self._require(source_id)
        now = utc_now()
        updated = self.repository.update(
            source_id,
            status="active",
            activated_by=actor,
            activated_at=now,
            updated_at=now,
        )
        self.audit.record_change(
            actor=actor,
            action="monitored_source.activate",
            entity_type="monitored_source",
            entity_id=source_id,
            old_value_json={"status": before.status},
            new_value_json={"status": "active"},
        )
        return updated

    def reset_checkpoint(
        self,
        source_id: str,
        *,
        message_id: int,
        actor: str,
        confirm: bool,
    ) -> MonitoredSourceRecord:
        if not confirm:
            raise CheckpointResetRequiresConfirmation("checkpoint reset requires confirmation")

        before = self._require(source_id)
        now = utc_now()
        updated = self.repository.update(
            source_id,
            checkpoint_message_id=message_id,
            checkpoint_date=now,
            updated_at=now,
        )
        self.audit.record_change(
            actor=actor,
            action="monitored_source.reset_checkpoint",
            entity_type="monitored_source",
            entity_id=source_id,
            old_value_json={"checkpoint_message_id": before.checkpoint_message_id},
            new_value_json={"checkpoint_message_id": message_id},
        )
        return updated

    def _require(self, source_id: str) -> MonitoredSourceRecord:
        source = self.repository.get(source_id)
        if source is None:
            raise KeyError(source_id)
        return source


def parse_source_input(input_ref: str, purpose: str) -> ParsedSourceInput:
    normalized = input_ref.strip()
    if normalized.startswith("@"):
        username = normalized[1:]
        return ParsedSourceInput(
            input_ref=normalized,
            username=username,
            source_kind="telegram_supergroup",
        )

    parsed = urlparse(normalized)
    if parsed.netloc in {"t.me", "telegram.me"}:
        username_from_path: str | None = parsed.path.strip("/").split("/", 1)[0] or None
        source_kind = (
            "telegram_channel" if purpose == "catalog_ingestion" else "telegram_supergroup"
        )
        return ParsedSourceInput(
            input_ref=normalized,
            username=username_from_path,
            source_kind=source_kind,
        )

    if "joinchat" in normalized or normalized.startswith("https://t.me/+"):
        return ParsedSourceInput(
            input_ref=normalized,
            username=None,
            source_kind="telegram_private_group",
            invite_link_hash=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        )

    return ParsedSourceInput(input_ref=normalized, username=None, source_kind="telegram_supergroup")


def _purpose_flags(purpose: str) -> tuple[bool, bool]:
    if purpose == "lead_monitoring":
        return True, False
    if purpose == "catalog_ingestion":
        return False, True
    if purpose == "both":
        return True, True
    raise ValueError(f"Unsupported source purpose: {purpose}")
