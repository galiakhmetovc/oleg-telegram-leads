"""Telegram source management behavior."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.repositories.scheduler import SchedulerJobRecord
from pur_leads.repositories.telegram_sources import (
    MonitoredSourceRecord,
    SourceAccessCheckSummary,
    SourcePreviewMessageRecord,
    TelegramSourceRepository,
)
from pur_leads.services.audit import AuditService
from pur_leads.services.scheduler import SchedulerService
from pur_leads.services.userbots import UserbotAccountService


class CheckpointResetRequiresConfirmation(ValueError):
    """Raised when a checkpoint reset is requested without explicit confirmation."""


class ActivationRequiresPreview(ValueError):
    """Raised when web activation is requested before preview is ready."""


@dataclass(frozen=True)
class ParsedSourceInput:
    input_ref: str
    username: str | None
    source_kind: str
    invite_link_hash: str | None = None
    start_message_id: int | None = None


@dataclass(frozen=True)
class SourceDetail:
    source: MonitoredSourceRecord
    access_checks: list[SourceAccessCheckSummary]
    preview_messages: list[SourcePreviewMessageRecord]
    jobs: list[SchedulerJobRecord]


class TelegramSourceService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = TelegramSourceRepository(session)
        self.audit = AuditService(session)
        self.scheduler = SchedulerService(session)

    def list_sources(self) -> list[MonitoredSourceRecord]:
        return self.repository.list_sources()

    def get_source_detail(self, source_id: str) -> SourceDetail:
        source = self._require(source_id)
        return SourceDetail(
            source=source,
            access_checks=self.repository.list_access_checks(source.id),
            preview_messages=self.repository.list_preview_messages(source.id),
            jobs=self.repository.list_jobs(source.id),
        )

    def create_draft(
        self,
        input_ref: str,
        *,
        added_by: str,
        purpose: str = "lead_monitoring",
        start_recent_days: int | None = None,
    ) -> MonitoredSourceRecord:
        if start_recent_days is not None and start_recent_days <= 0:
            raise ValueError("start_recent_days must be positive")
        parsed = parse_source_input(input_ref, purpose)
        now = utc_now()
        lead_enabled, catalog_enabled = _purpose_flags(purpose)
        default_userbot = UserbotAccountService(self.session).select_default_userbot()
        start_mode = _start_mode(
            start_recent_days=start_recent_days,
            start_message_id=parsed.start_message_id,
        )
        source = self.repository.create(
            source_kind=parsed.source_kind,
            telegram_id=None,
            username=parsed.username,
            title=None,
            invite_link_hash=parsed.invite_link_hash,
            input_ref=parsed.input_ref,
            source_purpose=purpose,
            assigned_userbot_account_id=default_userbot.id if default_userbot else None,
            priority="normal",
            status="draft",
            lead_detection_enabled=lead_enabled,
            catalog_ingestion_enabled=catalog_enabled,
            phase_enabled=True,
            start_mode=start_mode,
            start_message_id=parsed.start_message_id,
            start_recent_limit=None,
            start_recent_days=start_recent_days,
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
                "assigned_userbot_account_id": source.assigned_userbot_account_id,
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

    def request_access_check(self, source_id: str, *, actor: str) -> SchedulerJobRecord:
        source = self.set_status(source_id, "checking_access", actor=actor)
        return self.scheduler.enqueue(
            job_type="check_source_access",
            scope_type="telegram_source",
            scope_id=source.id,
            userbot_account_id=source.assigned_userbot_account_id,
            monitored_source_id=source.id,
            idempotency_key=f"source:{source.id}:check_access",
            payload_json={"requested_by": actor, "check_type": "onboarding"},
        )

    def request_preview(
        self,
        source_id: str,
        *,
        actor: str,
        limit: int = 20,
    ) -> SchedulerJobRecord:
        source = self._require(source_id)
        if source.status not in {"preview_ready", "active"}:
            raise ActivationRequiresPreview("source must be preview_ready before preview fetch")
        return self.scheduler.enqueue(
            job_type="fetch_source_preview",
            scope_type="telegram_source",
            scope_id=source.id,
            userbot_account_id=source.assigned_userbot_account_id,
            monitored_source_id=source.id,
            idempotency_key=f"source:{source.id}:preview",
            payload_json={"limit": limit, "requested_by": actor},
        )

    def activate_from_web(
        self,
        source_id: str,
        *,
        actor: str,
    ) -> tuple[MonitoredSourceRecord, SchedulerJobRecord]:
        source = self._require(source_id)
        if source.status != "preview_ready":
            raise ActivationRequiresPreview("source must be preview_ready before activation")
        activated = self.activate(source.id, actor=actor)
        now = utc_now()
        checkpoint_message_id = self._activation_checkpoint(source)
        update_values: dict[str, Any] = {"next_poll_at": now, "updated_at": now}
        if checkpoint_message_id is not None and activated.checkpoint_message_id is None:
            update_values["checkpoint_message_id"] = checkpoint_message_id
            update_values["checkpoint_date"] = now
        activated = self.repository.update(source.id, **update_values)
        job = self.scheduler.enqueue(
            job_type="poll_monitored_source",
            scope_type="telegram_source",
            scope_id=source.id,
            userbot_account_id=activated.assigned_userbot_account_id,
            monitored_source_id=source.id,
            idempotency_key=f"source:{source.id}:poll",
            run_after_at=now,
            checkpoint_before_json={"message_id": activated.checkpoint_message_id},
            payload_json={"limit": 100, "requested_by": actor},
        )
        return activated, job

    def pause(self, source_id: str, *, actor: str) -> MonitoredSourceRecord:
        return self.set_status(source_id, "paused", actor=actor)

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

    def _activation_checkpoint(self, source: MonitoredSourceRecord) -> int | None:
        if source.checkpoint_message_id is not None:
            return source.checkpoint_message_id
        if source.start_mode == "from_message":
            return source.start_message_id
        if source.start_mode != "from_now":
            return None

        preview_ids = [
            row.telegram_message_id for row in self.repository.list_preview_messages(source.id)
        ]
        access_ids = [
            row.last_message_id
            for row in self.repository.list_access_checks(source.id, limit=1)
            if row.last_message_id is not None
        ]
        message_ids = [*preview_ids, *access_ids]
        return max(message_ids) if message_ids else None


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
        path_parts = [part for part in parsed.path.strip("/").split("/") if part]
        username_from_path: str | None = path_parts[0] if path_parts else None
        message_id = _public_message_id(path_parts)
        input_ref = (
            f"{parsed.scheme}://{parsed.netloc}/{username_from_path}"
            if username_from_path and message_id is not None
            else normalized
        )
        source_kind = (
            "telegram_channel" if purpose == "catalog_ingestion" else "telegram_supergroup"
        )
        return ParsedSourceInput(
            input_ref=input_ref,
            username=username_from_path,
            source_kind=source_kind,
            start_message_id=message_id,
        )

    if "joinchat" in normalized or normalized.startswith("https://t.me/+"):
        return ParsedSourceInput(
            input_ref=normalized,
            username=None,
            source_kind="telegram_private_group",
            invite_link_hash=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        )

    return ParsedSourceInput(input_ref=normalized, username=None, source_kind="telegram_supergroup")


def _start_mode(*, start_recent_days: int | None, start_message_id: int | None) -> str:
    if start_recent_days is not None:
        return "recent_days"
    if start_message_id is not None:
        return "from_message"
    return "from_now"


def _public_message_id(path_parts: list[str]) -> int | None:
    if len(path_parts) < 2 or not path_parts[1].isdigit():
        return None
    return int(path_parts[1])


def _purpose_flags(purpose: str) -> tuple[bool, bool]:
    if purpose == "lead_monitoring":
        return True, False
    if purpose == "catalog_ingestion":
        return False, True
    if purpose == "both":
        return True, True
    raise ValueError(f"Unsupported source purpose: {purpose}")
