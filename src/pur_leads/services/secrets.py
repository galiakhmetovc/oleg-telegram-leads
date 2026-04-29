"""Secret reference behavior."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.repositories.secrets import SecretRefsRepository
from pur_leads.services.audit import AuditService
from pur_leads.services.settings import SettingsService

SECRET_TYPES = {
    "telegram_session",
    "telegram_api",
    "ai_api_key",
    "web_session_secret",
    "bootstrap_admin_password",
    "archive_s3_credentials",
    "other",
}
STORAGE_BACKENDS = {"env", "file", "system_keyring", "external_secret_manager"}


class SecretRefService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = SecretRefsRepository(session)
        self.audit = AuditService(session)

    def create_ref(
        self,
        *,
        secret_type: str,
        display_name: str,
        storage_backend: str,
        storage_ref: str,
    ) -> str:
        self._validate(secret_type, storage_backend)
        record = self.repository.create(
            secret_type=secret_type,
            display_name=display_name,
            storage_backend=storage_backend,
            storage_ref=storage_ref,
            now=utc_now(),
        )
        self.session.commit()
        return record.id

    def create_local_secret(
        self,
        *,
        secret_type: str,
        display_name: str,
        value: str,
        storage_root: Path | str,
    ) -> str:
        self._validate(secret_type, "file")
        secret_id = new_id()
        root = Path(storage_root)
        root.mkdir(parents=True, exist_ok=True)
        root.chmod(0o700)
        path = root / f"{secret_id}.secret"
        path.write_text(value, encoding="utf-8")
        path.chmod(0o600)
        record = self.repository.create(
            secret_id=secret_id,
            secret_type=secret_type,
            display_name=display_name,
            storage_backend="file",
            storage_ref=str(path),
            now=utc_now(),
        )
        self.session.commit()
        return record.id

    def resolve_setting_secret(self, setting_key: str) -> str | None:
        value = SettingsService(self.session).get(setting_key)
        if not isinstance(value, dict):
            return None
        secret_id = value.get("secret_ref_id")
        if not isinstance(secret_id, str) or not secret_id:
            return None
        return self.resolve_value(secret_id)

    def resolve_value(self, secret_id: str) -> str:
        record = self.repository.get(secret_id)
        if record is None:
            raise KeyError(secret_id)
        if record.storage_backend == "env":
            value = os.getenv(record.storage_ref)
            if value is None:
                raise FileNotFoundError(f"Environment secret is missing: {record.display_name}")
            return value
        if record.storage_backend == "file":
            return Path(record.storage_ref).read_text(encoding="utf-8")
        raise ValueError(f"Secret backend is not resolvable locally: {record.storage_backend}")

    def mark_missing(self, secret_id: str, *, checked_by: str) -> None:
        existing = self.repository.get(secret_id)
        if existing is None:
            raise KeyError(secret_id)

        record = self.repository.mark_missing(secret_id, utc_now())
        self.audit.record_event(
            event_type="scheduler",
            severity="error",
            message="Secret reference is missing",
            entity_type="secret_ref",
            entity_id=secret_id,
            details_json={
                "checked_by": checked_by,
                "display_name": record.display_name,
                "storage_backend": record.storage_backend,
            },
        )

    def public_view(self, secret_id: str) -> dict[str, Any]:
        record = self.repository.get(secret_id)
        if record is None:
            raise KeyError(secret_id)
        return {
            "id": record.id,
            "secret_type": record.secret_type,
            "display_name": record.display_name,
            "storage_backend": record.storage_backend,
            "status": record.status,
        }

    @staticmethod
    def _validate(secret_type: str, storage_backend: str) -> None:
        if secret_type not in SECRET_TYPES:
            raise ValueError(f"Unsupported secret_type: {secret_type}")
        if storage_backend not in STORAGE_BACKENDS:
            raise ValueError(f"Unsupported storage_backend: {storage_backend}")
