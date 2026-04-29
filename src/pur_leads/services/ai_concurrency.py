"""DB-backed AI model concurrency limiting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from math import floor
from typing import Any

from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.integrations.ai.chat import AiModelLease
from pur_leads.models.ai import ai_model_concurrency_leases_table

DEFAULT_MODEL_CONCURRENCY_LIMITS: dict[str, int] = {
    "glm-4.6": 3,
    "glm-4.6v-flashx": 3,
    "glm-4.7": 2,
    "glm-image": 1,
    "glm-5-turbo": 1,
    "glm-5v-turbo": 1,
    "glm-5.1": 1,
    "glm-4.5": 10,
    "glm-4.6v": 10,
    "glm-4.7-flash": 1,
    "glm-4.7-flashx": 3,
    "glm-ocr": 2,
    "glm-5": 2,
    "glm-4-plus": 20,
    "glm-4.5v": 10,
    "glm-4.6v-flash": 1,
    "autoglm-phone-multilingual": 5,
    "glm-4.5-air": 5,
    "glm-4.5-airx": 5,
    "glm-4.5-flash": 2,
    "glm-4-32b-0414-128k": 15,
    "cogview-4-250304": 5,
    "glm-asr-2512": 5,
    "viduq1-text": 5,
    "viduq1-image": 5,
    "viduq1-start-end": 5,
    "vidu2-image": 5,
    "vidu2-start-end": 5,
    "vidu2-reference": 5,
    "cogvideox-3": 1,
}


@dataclass(frozen=True)
class AiModelLeaseRecord:
    id: str
    provider: str
    provider_account_id: str | None
    model: str
    normalized_model: str
    worker_name: str


class AiModelConcurrencyService:
    def __init__(
        self,
        session: Session,
        *,
        limits: dict[str, int] | None = None,
        utilization_ratio: float = 0.8,
        default_limit: int = 1,
        lease_seconds: int = 180,
        retry_after_seconds: int = 5,
    ) -> None:
        self.session = session
        self.limits = _normalized_limits(limits or DEFAULT_MODEL_CONCURRENCY_LIMITS)
        self.utilization_ratio = utilization_ratio
        self.default_limit = default_limit
        self.lease_seconds = lease_seconds
        self.retry_after_seconds = retry_after_seconds

    def acquire_model_slot(
        self,
        *,
        provider: str,
        model: str,
        worker_name: str,
        provider_account_id: str | None = None,
    ) -> AiModelLease | None:
        limit = self.effective_limit_for_model(model, provider_account_id=provider_account_id)
        record = self.acquire_slot(
            provider=provider,
            provider_account_id=provider_account_id,
            model=model,
            limit=limit,
            worker_name=worker_name,
            lease_seconds=self.lease_seconds,
            raw_limit=self.raw_limit_for_model(model, provider_account_id=provider_account_id),
            utilization_ratio=self.utilization_ratio,
        )
        if record is None:
            return None
        return AiModelLease(
            id=record.id,
            provider=record.provider,
            model=record.model,
            provider_account_id=record.provider_account_id,
        )

    def release_model_slot(self, lease: AiModelLease) -> None:
        self.release_slot(lease.id)

    def raw_limit_for_model(self, model: str, *, provider_account_id: str | None = None) -> int:
        normalized_model = _normalize_model(model)
        if provider_account_id:
            account_key = _account_model_key(provider_account_id, normalized_model)
            if account_key in self.limits:
                return max(1, int(self.limits[account_key]))
        return max(1, int(self.limits.get(normalized_model, self.default_limit)))

    def effective_limit_for_model(
        self, model: str, *, provider_account_id: str | None = None
    ) -> int:
        return _effective_limit(
            self.raw_limit_for_model(model, provider_account_id=provider_account_id),
            self.utilization_ratio,
        )

    def acquire_slot(
        self,
        *,
        provider: str,
        provider_account_id: str | None = None,
        model: str,
        limit: int,
        worker_name: str,
        lease_seconds: int,
        raw_limit: int | None = None,
        utilization_ratio: float | None = None,
    ) -> AiModelLeaseRecord | None:
        effective_limit = max(1, int(limit))
        normalized_model = _normalize_model(model)
        now = utc_now()
        expires_at = now + timedelta(seconds=max(1, int(lease_seconds)))

        # SQLite has no SELECT FOR UPDATE. BEGIN IMMEDIATE serializes count+insert
        # across worker processes while keeping the normal scheduler path unchanged.
        self.session.commit()
        self.session.execute(text("BEGIN IMMEDIATE"))
        self._delete_expired(
            provider=provider,
            provider_account_id=provider_account_id,
            normalized_model=normalized_model,
            now=now,
        )
        active_count = self._active_count(
            provider=provider,
            provider_account_id=provider_account_id,
            normalized_model=normalized_model,
            now=now,
        )
        if active_count >= effective_limit:
            self.session.commit()
            return None

        lease_id = new_id()
        self.session.execute(
            insert(ai_model_concurrency_leases_table).values(
                id=lease_id,
                provider=provider,
                ai_provider_account_id=provider_account_id,
                model=model,
                normalized_model=normalized_model,
                worker_name=worker_name,
                raw_limit=raw_limit,
                utilization_ratio=utilization_ratio,
                effective_limit=effective_limit,
                acquired_at=now,
                lease_expires_at=expires_at,
                metadata_json={
                    "effective_limit": effective_limit,
                    "raw_limit": raw_limit,
                    "utilization_ratio": utilization_ratio,
                },
            )
        )
        self.session.commit()
        return AiModelLeaseRecord(
            id=lease_id,
            provider=provider,
            provider_account_id=provider_account_id,
            model=model,
            normalized_model=normalized_model,
            worker_name=worker_name,
        )

    def release_slot(self, lease_id: str) -> None:
        self.session.execute(
            delete(ai_model_concurrency_leases_table).where(
                ai_model_concurrency_leases_table.c.id == lease_id
            )
        )
        self.session.commit()

    def _delete_expired(  # noqa: ANN001
        self,
        *,
        provider: str,
        provider_account_id: str | None,
        normalized_model: str,
        now,
    ) -> None:
        conditions = [
            ai_model_concurrency_leases_table.c.provider == provider,
            ai_model_concurrency_leases_table.c.normalized_model == normalized_model,
            ai_model_concurrency_leases_table.c.lease_expires_at <= now,
        ]
        conditions.append(
            ai_model_concurrency_leases_table.c.ai_provider_account_id == provider_account_id
            if provider_account_id is not None
            else ai_model_concurrency_leases_table.c.ai_provider_account_id.is_(None)
        )
        self.session.execute(
            delete(ai_model_concurrency_leases_table).where(*conditions)
        )

    def _active_count(  # noqa: ANN001
        self,
        *,
        provider: str,
        provider_account_id: str | None,
        normalized_model: str,
        now,
    ) -> int:
        conditions = [
            ai_model_concurrency_leases_table.c.provider == provider,
            ai_model_concurrency_leases_table.c.normalized_model == normalized_model,
            ai_model_concurrency_leases_table.c.lease_expires_at > now,
        ]
        conditions.append(
            ai_model_concurrency_leases_table.c.ai_provider_account_id == provider_account_id
            if provider_account_id is not None
            else ai_model_concurrency_leases_table.c.ai_provider_account_id.is_(None)
        )
        value = self.session.execute(
            select(func.count())
            .select_from(ai_model_concurrency_leases_table)
            .where(*conditions)
        ).scalar_one()
        return int(value)


def _effective_limit(raw_limit: int, utilization_ratio: float) -> int:
    safe_ratio = max(0.0, min(1.0, utilization_ratio))
    return max(1, floor(max(1, raw_limit) * safe_ratio))


def _normalized_limits(limits: dict[str, int]) -> dict[str, int]:
    return {
        _normalize_model(key): max(1, int(value))
        for key, value in limits.items()
        if isinstance(key, str) and _int_like(value)
    }


def _normalize_model(model: str) -> str:
    return model.strip().casefold().replace("_", "-")


def _account_model_key(provider_account_id: str, normalized_model: str) -> str:
    return f"{provider_account_id}:{normalized_model}"


def _int_like(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        int(value)
    except (TypeError, ValueError):
        return False
    return True
