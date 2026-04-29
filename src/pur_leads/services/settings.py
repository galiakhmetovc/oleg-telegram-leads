"""Typed settings behavior."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.repositories.settings import SettingsRepository
from pur_leads.services.ai_concurrency import DEFAULT_MODEL_CONCURRENCY_LIMITS
from pur_leads.services.audit import AuditService

ALLOWED_VALUE_TYPES = {"bool", "int", "float", "string", "json", "secret_ref"}


class RawSecretValueError(ValueError):
    """Raised when a raw secret is passed instead of a secret reference."""


@dataclass(frozen=True)
class SettingDefault:
    value: Any
    value_type: str


DEFAULT_SETTINGS: dict[str, SettingDefault] = {
    "telegram_worker_count": SettingDefault(1, "int"),
    "worker_concurrency": SettingDefault(1, "int"),
    "worker_capacity_global_cap": SettingDefault(32, "int"),
    "worker_realtime_reserved_slots": SettingDefault(2, "int"),
    "local_parser_concurrency": SettingDefault(4, "int"),
    "telegram_api_id": SettingDefault(None, "int"),
    "telegram_api_hash_secret_ref": SettingDefault(None, "secret_ref"),
    "telegram_bot_token_secret_ref": SettingDefault(None, "secret_ref"),
    "telegram_default_userbot_account_id": SettingDefault(None, "string"),
    "telegram_read_jobs_per_userbot": SettingDefault(1, "int"),
    "telegram_flood_sleep_threshold_seconds": SettingDefault(60, "int"),
    "telegram_get_history_wait_seconds": SettingDefault(1, "int"),
    "telegram_lead_notifications_enabled": SettingDefault(True, "bool"),
    "telegram_lead_notification_chat_id": SettingDefault(None, "string"),
    "telegram_lead_notification_thread_id": SettingDefault(None, "int"),
    "telegram_notification_min_interval_seconds": SettingDefault(1, "int"),
    "telegram_bot_send_concurrency_per_bot": SettingDefault(1, "int"),
    "telegram_digest_enabled": SettingDefault(True, "bool"),
    "telegram_digest_interval_minutes": SettingDefault(360, "int"),
    "telegram_digest_include_maybe": SettingDefault(True, "bool"),
    "telegram_digest_include_catalog_pending": SettingDefault(True, "bool"),
    "telegram_digest_include_source_issues": SettingDefault(True, "bool"),
    "telegram_digest_include_contact_reasons": SettingDefault(True, "bool"),
    "notify_leads": SettingDefault(True, "bool"),
    "notify_live_leads": SettingDefault(True, "bool"),
    "notify_maybe": SettingDefault(False, "bool"),
    "notify_retro_leads": SettingDefault(False, "bool"),
    "notify_reclassification_leads": SettingDefault(False, "bool"),
    "notify_high_value_low_confidence": SettingDefault(True, "bool"),
    "lead_notify_min_confidence": SettingDefault(0.7, "float"),
    "lead_notify_high_value_min_confidence": SettingDefault(0.45, "float"),
    "high_value_notify_enabled": SettingDefault(True, "bool"),
    "high_value_notify_threshold": SettingDefault(0.75, "float"),
    "high_value_negative_score_max": SettingDefault(0.35, "float"),
    "lead_cluster_notify_on_update": SettingDefault(False, "bool"),
    "catalog_ingestion_pur_channel_enabled": SettingDefault(True, "bool"),
    "zai_api_key_secret_ref": SettingDefault(None, "secret_ref"),
    "catalog_llm_extraction_enabled": SettingDefault(True, "bool"),
    "catalog_llm_provider": SettingDefault("zai", "string"),
    "catalog_llm_base_url": SettingDefault("https://api.z.ai/api/coding/paas/v4", "string"),
    "catalog_llm_model": SettingDefault("glm-5.1", "string"),
    "catalog_llm_temperature": SettingDefault(0.0, "float"),
    "catalog_llm_max_tokens": SettingDefault(4096, "int"),
    "catalog_llm_fallback_to_heuristic": SettingDefault(True, "bool"),
    "ai_model_concurrency_enabled": SettingDefault(True, "bool"),
    "ai_model_concurrency_limits": SettingDefault(DEFAULT_MODEL_CONCURRENCY_LIMITS, "json"),
    "ai_model_concurrency_utilization_ratio": SettingDefault(0.8, "float"),
    "ai_model_concurrency_default_limit": SettingDefault(1, "int"),
    "ai_model_concurrency_lease_seconds": SettingDefault(180, "int"),
    "ai_model_concurrency_retry_after_seconds": SettingDefault(5, "int"),
    "lead_llm_shadow_enabled": SettingDefault(False, "bool"),
    "lead_llm_shadow_provider": SettingDefault("zai", "string"),
    "lead_llm_shadow_base_url": SettingDefault("https://api.z.ai/api/coding/paas/v4", "string"),
    "lead_llm_shadow_model": SettingDefault("glm-4.5-flash", "string"),
    "lead_llm_shadow_temperature": SettingDefault(0.0, "float"),
    "lead_llm_shadow_max_tokens": SettingDefault(2048, "int"),
    "lead_llm_shadow_max_messages_per_job": SettingDefault(10, "int"),
    "lead_llm_shadow_fallback_on_error": SettingDefault(True, "bool"),
    "manual_catalog_add_enabled": SettingDefault(True, "bool"),
    "manual_catalog_create_candidate_first": SettingDefault(True, "bool"),
    "manual_catalog_default_status_for_admin": SettingDefault("approved", "string"),
    "manual_catalog_requires_evidence_note": SettingDefault(True, "bool"),
    "manual_catalog_allow_direct_approved": SettingDefault(True, "bool"),
    "web_manual_forward_import_enabled": SettingDefault(True, "bool"),
    "telegram_manual_forward_input_enabled": SettingDefault(False, "bool"),
    "lead_monitoring_public_groups_enabled": SettingDefault(True, "bool"),
    "external_page_ingestion_enabled": SettingDefault(True, "bool"),
    "external_page_allowed_domains": SettingDefault(["telegra.ph"], "json"),
    "external_page_fetch_timeout_seconds": SettingDefault(20, "int"),
    "external_page_fetch_concurrency": SettingDefault(4, "int"),
    "external_page_max_bytes": SettingDefault(1_048_576, "int"),
    "backup_enabled": SettingDefault(True, "bool"),
    "backup_storage_backend": SettingDefault("local", "string"),
    "backup_path": SettingDefault("artifacts/backups", "string"),
    "backup_sqlite_enabled": SettingDefault(True, "bool"),
    "backup_verify_after_write": SettingDefault(True, "bool"),
    "backup_retention_days": SettingDefault(30, "int"),
    "restore_dry_run_required": SettingDefault(True, "bool"),
    "backup_sessions_enabled": SettingDefault(False, "bool"),
    "backup_secret_values_enabled": SettingDefault(False, "bool"),
    "backup_encryption_required_for_secrets": SettingDefault(True, "bool"),
}


class SettingsService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = SettingsRepository(session)
        self.audit = AuditService(session)

    def get(
        self,
        key: str,
        scope: str = "global",
        scope_id: str | None = None,
    ) -> Any:
        record = self.repository.get(key, scope=scope, scope_id=scope_id)
        if record is not None:
            return record.value_json
        default = DEFAULT_SETTINGS.get(key)
        if default is None:
            return None
        return default.value

    def set(
        self,
        key: str,
        value: Any,
        *,
        value_type: str,
        updated_by: str,
        scope: str = "global",
        scope_id: str | None = None,
        reason: str | None = None,
        description: str | None = None,
        requires_restart: bool = False,
    ) -> None:
        self._validate_value(value, value_type)

        now = utc_now()
        existing = self.repository.get(key, scope=scope, scope_id=scope_id)
        old_value = existing.value_json if existing is not None else None

        self.repository.set(
            key,
            value,
            value_type,
            updated_by,
            now,
            scope=scope,
            scope_id=scope_id,
            description=description,
            requires_restart=requires_restart,
            is_secret_ref=value_type == "secret_ref",
        )
        self.repository.add_revision(
            setting_key=key,
            scope=scope,
            scope_id=scope_id,
            old_value_hash=self._hash_value(old_value) if existing is not None else None,
            new_value_hash=self._hash_value(value),
            old_value_json=old_value,
            new_value_json=value,
            changed_by=updated_by,
            change_reason=reason,
            created_at=now,
        )
        self.audit.record_change(
            actor=updated_by,
            action="settings.update",
            entity_type="setting",
            entity_id=key,
            old_value_json={"value": old_value, "scope": scope, "scope_id": scope_id},
            new_value_json={"value": value, "scope": scope, "scope_id": scope_id},
        )
        self.session.commit()

    def list(self, scope: str | None = None):
        return self.repository.list(scope=scope)

    @staticmethod
    def _validate_value(value: Any, value_type: str) -> None:
        if value_type not in ALLOWED_VALUE_TYPES:
            raise ValueError(f"Unsupported setting value_type: {value_type}")
        if value_type == "secret_ref":
            if not isinstance(value, dict) or set(value) != {"secret_ref_id"}:
                raise RawSecretValueError(
                    "secret_ref settings must store only a secret reference id"
                )
            if not isinstance(value["secret_ref_id"], str) or not value["secret_ref_id"]:
                raise RawSecretValueError("secret_ref_id must be a non-empty string")

    @staticmethod
    def _hash_value(value: Any) -> str:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
