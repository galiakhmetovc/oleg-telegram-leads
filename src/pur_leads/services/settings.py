"""Typed settings behavior."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.repositories.settings import SettingsRepository

ALLOWED_VALUE_TYPES = {"bool", "int", "float", "string", "json", "secret_ref"}


class RawSecretValueError(ValueError):
    """Raised when a raw secret is passed instead of a secret reference."""


@dataclass(frozen=True)
class SettingDefault:
    value: Any
    value_type: str


DEFAULT_SETTINGS: dict[str, SettingDefault] = {
    "telegram_worker_count": SettingDefault(1, "int"),
    "telegram_read_jobs_per_userbot": SettingDefault(1, "int"),
    "catalog_ingestion_pur_channel_enabled": SettingDefault(True, "bool"),
    "lead_monitoring_public_groups_enabled": SettingDefault(True, "bool"),
    "backup_sessions_enabled": SettingDefault(False, "bool"),
    "backup_secret_values_enabled": SettingDefault(False, "bool"),
    "backup_encryption_required_for_secrets": SettingDefault(True, "bool"),
}


class SettingsService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = SettingsRepository(session)

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
