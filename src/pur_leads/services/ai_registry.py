"""AI provider/model/agent registry behavior."""

from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.models.ai import (
    ai_agent_routes_table,
    ai_agents_table,
    ai_model_limits_table,
    ai_models_table,
    ai_provider_accounts_table,
    ai_providers_table,
)
from pur_leads.services.audit import AuditService

ZAI_BASE_URL = "https://api.z.ai/api/coding/paas/v4"
DEFAULT_UTILIZATION_RATIO = 0.8

ZAI_MODEL_SEED: tuple[dict[str, Any], ...] = (
    {"model": "GLM-4.6", "type": "language", "limit": 3},
    {"model": "GLM-4.6V-FlashX", "type": "language", "limit": 3},
    {"model": "GLM-4.7", "type": "language", "limit": 2},
    {"model": "GLM-Image", "type": "image_generation", "limit": 1},
    {"model": "GLM-5-Turbo", "type": "language", "limit": 1},
    {"model": "GLM-5V-Turbo", "type": "language", "limit": 1},
    {"model": "GLM-5.1", "type": "language", "limit": 1},
    {"model": "GLM-4.5", "type": "language", "limit": 10},
    {"model": "GLM-4.6V", "type": "language", "limit": 10},
    {"model": "GLM-4.7-Flash", "type": "language", "limit": 1},
    {"model": "GLM-4.7-FlashX", "type": "language", "limit": 3},
    {"model": "GLM-OCR", "type": "ocr", "limit": 2},
    {"model": "GLM-5", "type": "language", "limit": 2},
    {"model": "GLM-4-Plus", "type": "language", "limit": 20},
    {"model": "GLM-4.5V", "type": "language", "limit": 10},
    {"model": "GLM-4.6V-Flash", "type": "language", "limit": 1},
    {"model": "AutoGLM-Phone-Multilingual", "type": "language", "limit": 5},
    {"model": "GLM-4.5-Air", "type": "language", "limit": 5},
    {"model": "GLM-4.5-AirX", "type": "language", "limit": 5},
    {"model": "GLM-4.5-Flash", "type": "language", "limit": 2},
    {"model": "GLM-4-32B-0414-128K", "type": "language", "limit": 15},
    {"model": "CogView-4-250304", "type": "image_generation", "limit": 5},
    {"model": "GLM-ASR-2512", "type": "realtime_audio_video", "limit": 5},
    {"model": "ViduQ1-text", "type": "video_generation", "limit": 5},
    {"model": "Viduq1-Image", "type": "video_generation", "limit": 5},
    {"model": "Viduq1-Start-End", "type": "video_generation", "limit": 5},
    {"model": "Vidu2-Image", "type": "video_generation", "limit": 5},
    {"model": "Vidu2-Start-End", "type": "video_generation", "limit": 5},
    {"model": "Vidu2-Reference", "type": "video_generation", "limit": 5},
    {"model": "CogVideoX-3", "type": "video_generation", "limit": 1},
)

ZAI_THINKING_MODELS = {
    "glm-5.1",
    "glm-5",
    "glm-5-turbo",
    "glm-5v-turbo",
    "glm-4.7",
    "glm-4.7-flash",
    "glm-4.7-flashx",
    "glm-4.6",
    "glm-4.6v",
    "glm-4.6v-flash",
    "glm-4.6v-flashx",
    "glm-4.5",
    "glm-4.5-air",
    "glm-4.5-airx",
    "glm-4.5-flash",
    "glm-4.5v",
}

ZAI_STRUCTURED_OUTPUT_MODELS = {
    "glm-5.1",
    "glm-5",
    "glm-5-turbo",
    "glm-5v-turbo",
    "glm-4.7",
    "glm-4.7-flash",
    "glm-4.7-flashx",
    "glm-4.6",
    "glm-4.6v",
    "glm-4.6v-flash",
    "glm-4.6v-flashx",
    "glm-4.5",
    "glm-4.5-air",
    "glm-4.5-airx",
    "glm-4.5-flash",
    "glm-4.5v",
    "glm-4-32b-0414-128k",
}

ZAI_VISION_LANGUAGE_MODELS = {
    "glm-5v-turbo",
    "glm-4.6v",
    "glm-4.6v-flash",
    "glm-4.6v-flashx",
    "glm-4.5v",
}

ZAI_CHAT_COMPLETION_DOC_URL = "https://docs.z.ai/api-reference/llm/chat-completion"
ZAI_THINKING_DOC_URL = "https://docs.z.ai/guides/capabilities/thinking-mode"
ZAI_STRUCTURED_OUTPUT_DOC_URL = "https://docs.z.ai/guides/capabilities/struct-output"
ZAI_OCR_DOC_URL = "https://docs.z.ai/guides/vlm/glm-ocr"

AGENT_SEED: tuple[dict[str, Any], ...] = (
    {
        "agent_key": "catalog_extractor",
        "display_name": "Catalog extractor",
        "task_type": "catalog_extraction",
        "default_strategy": "primary_fallback",
    },
    {
        "agent_key": "lead_detector",
        "display_name": "Lead detector",
        "task_type": "lead_detection",
        "default_strategy": "fuzzy_primary_llm_shadow",
    },
    {
        "agent_key": "ocr_extractor",
        "display_name": "OCR extractor",
        "task_type": "ocr",
        "default_strategy": "primary_fallback",
    },
)

ROUTE_SEED: tuple[dict[str, Any], ...] = (
    {
        "agent_key": "catalog_extractor",
        "model": "GLM-5.1",
        "route_role": "primary",
        "priority": 10,
        "max_output_tokens": 4096,
    },
    {
        "agent_key": "catalog_extractor",
        "model": "GLM-4.5-Air",
        "route_role": "fallback",
        "priority": 20,
        "max_output_tokens": 4096,
    },
    {
        "agent_key": "lead_detector",
        "model": "GLM-4.5-Flash",
        "route_role": "shadow",
        "priority": 10,
        "max_output_tokens": 512,
    },
    {
        "agent_key": "ocr_extractor",
        "model": "GLM-OCR",
        "route_role": "primary",
        "priority": 10,
        "max_output_tokens": 4096,
    },
)


@dataclass(frozen=True)
class AiAgentRouteSelection:
    route_id: str
    agent_id: str
    provider_account_id: str
    model_id: str
    provider: str
    model: str
    model_type: str
    base_url: str
    route_role: str
    priority: int
    max_output_tokens: int | None
    temperature: float | None
    thinking_enabled: bool
    thinking_mode: str
    structured_output_required: bool
    supports_structured_output: bool
    supports_json_mode: bool
    supports_thinking: bool
    supports_tools: bool
    supports_streaming: bool
    supports_image_input: bool
    supports_document_input: bool
    endpoint_family: str | None
    thinking_control_values: list[str]


class AiRegistryService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def bootstrap_defaults(self, *, actor: str) -> dict[str, Any]:
        provider_id = self._upsert_provider()
        account_id = self._upsert_account(provider_id)
        model_ids = {
            seed["model"]: self._upsert_model(provider_id, seed) for seed in ZAI_MODEL_SEED
        }
        for seed in ZAI_MODEL_SEED:
            self._upsert_limit(provider_id, model_ids[seed["model"]], raw_limit=int(seed["limit"]))
        agent_ids = {seed["agent_key"]: self._upsert_agent(seed) for seed in AGENT_SEED}
        for seed in ROUTE_SEED:
            model_id = model_ids.get(seed["model"])
            agent_id = agent_ids.get(seed["agent_key"])
            if model_id is not None and agent_id is not None:
                self._upsert_route(
                    account_id=account_id, agent_id=agent_id, model_id=model_id, seed=seed
                )
        self.session.commit()
        return {
            "provider_key": "zai",
            "provider_id": provider_id,
            "account_id": account_id,
            "model_count": len(model_ids),
            "agent_count": len(agent_ids),
            "actor": actor,
        }

    def configure_zai_account(
        self,
        *,
        actor: str,
        base_url: str,
        auth_secret_ref: str,
    ) -> dict[str, Any]:
        provider = self._provider_by_key("zai")
        if provider is None:
            bootstrap = self.bootstrap_defaults(actor=actor)
            provider_id = str(bootstrap["provider_id"])
        else:
            provider_id = str(provider["id"])
        account_id = self._default_account_id(provider_id)
        if account_id is None:
            account_id = self._upsert_account(provider_id)
        old_value = self._account_by_id(account_id)
        now = utc_now()
        self.session.execute(
            update(ai_provider_accounts_table)
            .where(ai_provider_accounts_table.c.id == account_id)
            .values(
                base_url=base_url.strip().rstrip("/"),
                auth_secret_ref=auth_secret_ref,
                enabled=True,
                updated_at=now,
            )
        )
        updated = self._account_by_id(account_id)
        AuditService(self.session).record_change(
            actor=actor,
            action="ai_registry.account_configure",
            entity_type="ai_provider_account",
            entity_id=account_id,
            old_value_json=old_value,
            new_value_json=updated,
        )
        self.session.commit()
        return updated or {}

    def select_routes(
        self,
        *,
        agent_key: str,
        route_role: str | None = None,
    ) -> list[AiAgentRouteSelection]:
        conditions = [
            ai_agents_table.c.agent_key == agent_key,
            ai_agents_table.c.enabled.is_(True),
            ai_agent_routes_table.c.enabled.is_(True),
            ai_provider_accounts_table.c.enabled.is_(True),
            ai_models_table.c.status == "active",
            ai_providers_table.c.status == "active",
        ]
        if route_role is not None:
            conditions.append(ai_agent_routes_table.c.route_role == route_role)
        rows = (
            self.session.execute(
                select(
                    ai_agent_routes_table.c.id.label("route_id"),
                    ai_agents_table.c.id.label("agent_id"),
                    ai_provider_accounts_table.c.id.label("provider_account_id"),
                    ai_models_table.c.id.label("model_id"),
                    ai_providers_table.c.provider_key.label("provider"),
                    ai_models_table.c.provider_model_name.label("model"),
                    ai_models_table.c.model_type,
                    ai_provider_accounts_table.c.base_url,
                    ai_agent_routes_table.c.route_role,
                    ai_agent_routes_table.c.priority,
                    ai_agent_routes_table.c.max_output_tokens,
                    ai_agent_routes_table.c.temperature,
                    ai_agent_routes_table.c.thinking_enabled,
                    ai_agent_routes_table.c.thinking_mode,
                    ai_agent_routes_table.c.structured_output_required,
                    ai_models_table.c.supports_structured_output,
                    ai_models_table.c.supports_json_mode,
                    ai_models_table.c.supports_thinking,
                    ai_models_table.c.supports_tools,
                    ai_models_table.c.supports_streaming,
                    ai_models_table.c.supports_image_input,
                    ai_models_table.c.supports_document_input,
                    ai_models_table.c.metadata_json.label("model_metadata_json"),
                )
                .select_from(
                    ai_agent_routes_table.join(
                        ai_agents_table,
                        ai_agent_routes_table.c.ai_agent_id == ai_agents_table.c.id,
                    )
                    .join(
                        ai_provider_accounts_table,
                        ai_agent_routes_table.c.ai_provider_account_id
                        == ai_provider_accounts_table.c.id,
                    )
                    .join(
                        ai_models_table,
                        ai_agent_routes_table.c.ai_model_id == ai_models_table.c.id,
                    )
                    .join(
                        ai_providers_table,
                        ai_models_table.c.ai_provider_id == ai_providers_table.c.id,
                    )
                )
                .where(*conditions)
                .order_by(ai_agent_routes_table.c.priority, ai_agent_routes_table.c.created_at)
            )
            .mappings()
            .all()
        )
        return [_route_selection_from_row(row) for row in rows]

    def model_concurrency_limits(self, *, provider_key: str) -> dict[str, int]:
        rows = (
            self.session.execute(
                select(
                    ai_models_table.c.normalized_model_name,
                    ai_model_limits_table.c.raw_limit,
                )
                .select_from(
                    ai_model_limits_table.join(
                        ai_models_table,
                        ai_model_limits_table.c.ai_model_id == ai_models_table.c.id,
                    ).join(
                        ai_providers_table,
                        ai_model_limits_table.c.ai_provider_id == ai_providers_table.c.id,
                    )
                )
                .where(
                    ai_providers_table.c.provider_key == provider_key,
                    ai_providers_table.c.status == "active",
                    ai_models_table.c.status == "active",
                    ai_model_limits_table.c.limit_scope == "concurrency",
                )
                .order_by(ai_models_table.c.normalized_model_name)
            )
            .mappings()
            .all()
        )
        return {str(row["normalized_model_name"]): max(1, int(row["raw_limit"])) for row in rows}

    def snapshot(self) -> dict[str, Any]:
        providers = [
            dict(row)
            for row in self.session.execute(
                select(ai_providers_table).order_by(ai_providers_table.c.provider_key)
            )
            .mappings()
            .all()
        ]
        accounts = [
            dict(row)
            for row in self.session.execute(
                select(ai_provider_accounts_table).order_by(
                    ai_provider_accounts_table.c.priority,
                    ai_provider_accounts_table.c.display_name,
                )
            )
            .mappings()
            .all()
        ]
        limit_rows = [
            dict(row)
            for row in self.session.execute(select(ai_model_limits_table)).mappings().all()
        ]
        limit_by_model_id = {row["ai_model_id"]: row for row in limit_rows}
        models = [
            {
                **dict(row),
                "limit": self._limit_payload(limit_by_model_id.get(row["id"])),
            }
            for row in self.session.execute(
                select(ai_models_table).order_by(
                    ai_models_table.c.model_type,
                    ai_models_table.c.normalized_model_name,
                )
            )
            .mappings()
            .all()
        ]
        agents = [
            dict(row)
            for row in self.session.execute(
                select(ai_agents_table).order_by(ai_agents_table.c.agent_key)
            )
            .mappings()
            .all()
        ]
        return {
            "providers": providers,
            "accounts": accounts,
            "models": models,
            "agents": agents,
            "routes": self.list_route_payloads(),
        }

    def list_route_payloads(self) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.session.execute(self._route_payload_statement()).mappings().all()
        ]

    def update_model_limit(
        self,
        limit_id: str,
        *,
        actor: str,
        raw_limit: int | None = None,
        utilization_ratio: float | None = None,
    ) -> dict[str, Any]:
        existing = self._limit_by_id(limit_id)
        if existing is None:
            raise KeyError(limit_id)
        next_raw_limit = int(existing["raw_limit"] if raw_limit is None else raw_limit)
        next_utilization_ratio = float(
            existing["utilization_ratio"] if utilization_ratio is None else utilization_ratio
        )
        if next_raw_limit < 1:
            raise ValueError("raw_limit must be >= 1")
        if next_utilization_ratio <= 0 or next_utilization_ratio > 1:
            raise ValueError("utilization_ratio must be > 0 and <= 1")
        now = utc_now()
        values = {
            "raw_limit": next_raw_limit,
            "utilization_ratio": next_utilization_ratio,
            "effective_limit": _effective_limit(next_raw_limit, next_utilization_ratio),
            "source": "operator_configured",
            "updated_at": now,
        }
        self.session.execute(
            update(ai_model_limits_table)
            .where(ai_model_limits_table.c.id == limit_id)
            .values(**values)
        )
        updated = self._limit_by_id(limit_id)
        AuditService(self.session).record_change(
            actor=actor,
            action="ai_registry.limit_update",
            entity_type="ai_model_limit",
            entity_id=limit_id,
            old_value_json=existing,
            new_value_json=updated,
        )
        return self._limit_payload(updated)

    def upsert_agent_route(
        self,
        *,
        agent_key: str,
        model_id: str,
        route_role: str,
        actor: str,
        account_id: str | None = None,
        priority: int = 50,
        enabled: bool = True,
        max_output_tokens: int | None = None,
        temperature: float | None = 0.0,
        thinking_enabled: bool = False,
        thinking_mode: str | None = None,
        structured_output_required: bool = True,
    ) -> dict[str, Any]:
        normalized_role = route_role.strip().casefold()
        if not normalized_role:
            raise ValueError("route_role is required")
        agent = self._agent_by_key(agent_key)
        if agent is None:
            raise KeyError(agent_key)
        model = self._model_by_id(model_id)
        if model is None:
            raise KeyError(model_id)
        resolved_account_id = account_id or self._default_account_id(str(model["ai_provider_id"]))
        if resolved_account_id is None:
            raise KeyError("provider account")
        resolved_thinking_mode = _normalize_thinking_mode(
            thinking_mode,
            thinking_enabled=thinking_enabled,
        )
        existing = self._route_by_agent_model_role(
            agent_id=str(agent["id"]),
            model_id=model_id,
            route_role=normalized_role,
        )
        now = utc_now()
        values = {
            "ai_agent_id": agent["id"],
            "ai_provider_account_id": resolved_account_id,
            "ai_model_id": model_id,
            "route_role": normalized_role,
            "priority": max(0, int(priority)),
            "weight": 1.0,
            "enabled": bool(enabled),
            "max_input_tokens": None,
            "max_output_tokens": max_output_tokens,
            "temperature": temperature,
            "thinking_enabled": _thinking_enabled_from_mode(resolved_thinking_mode),
            "thinking_mode": resolved_thinking_mode,
            "structured_output_required": bool(structured_output_required),
            "fallback_on_error": True,
            "fallback_on_rate_limit": True,
            "fallback_on_invalid_output": True,
            "route_conditions_json": None,
            "metadata_json": {},
            "updated_at": now,
        }
        if existing is None:
            route_id = new_id()
            self.session.execute(
                insert(ai_agent_routes_table).values(id=route_id, created_at=now, **values)
            )
            old_value = None
        else:
            route_id = str(existing["id"])
            old_value = self.route_payload(route_id)
            self.session.execute(
                update(ai_agent_routes_table)
                .where(ai_agent_routes_table.c.id == route_id)
                .values(**values)
            )
        updated = self.route_payload(route_id)
        AuditService(self.session).record_change(
            actor=actor,
            action="ai_registry.route_upsert",
            entity_type="ai_agent_route",
            entity_id=route_id,
            old_value_json=old_value,
            new_value_json=updated,
        )
        return updated

    def update_agent_route(
        self,
        route_id: str,
        *,
        actor: str,
        enabled: bool | None = None,
        priority: int | None = None,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
        thinking_enabled: bool | None = None,
        thinking_mode: str | None = None,
        structured_output_required: bool | None = None,
    ) -> dict[str, Any]:
        old_value = self.route_payload(route_id)
        if old_value is None:
            raise KeyError(route_id)
        values: dict[str, Any] = {"updated_at": utc_now()}
        if enabled is not None:
            values["enabled"] = bool(enabled)
        if priority is not None:
            values["priority"] = max(0, int(priority))
        if max_output_tokens is not None:
            values["max_output_tokens"] = int(max_output_tokens)
        if temperature is not None:
            values["temperature"] = float(temperature)
        if thinking_mode is not None:
            resolved_thinking_mode = _normalize_thinking_mode(thinking_mode)
            values["thinking_mode"] = resolved_thinking_mode
            values["thinking_enabled"] = _thinking_enabled_from_mode(resolved_thinking_mode)
        if thinking_enabled is not None and thinking_mode is None:
            resolved_thinking_mode = _normalize_thinking_mode(
                None,
                thinking_enabled=bool(thinking_enabled),
            )
            values["thinking_mode"] = resolved_thinking_mode
            values["thinking_enabled"] = _thinking_enabled_from_mode(resolved_thinking_mode)
        if structured_output_required is not None:
            values["structured_output_required"] = bool(structured_output_required)
        self.session.execute(
            update(ai_agent_routes_table)
            .where(ai_agent_routes_table.c.id == route_id)
            .values(**values)
        )
        updated = self.route_payload(route_id)
        AuditService(self.session).record_change(
            actor=actor,
            action="ai_registry.route_update",
            entity_type="ai_agent_route",
            entity_id=route_id,
            old_value_json=old_value,
            new_value_json=updated,
        )
        return updated

    def route_payload(self, route_id: str) -> dict[str, Any] | None:
        row = (
            self.session.execute(
                self._route_payload_statement().where(ai_agent_routes_table.c.id == route_id)
            )
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None

    def _upsert_provider(self) -> str:
        now = utc_now()
        existing = self._provider_by_key("zai")
        values = {
            "provider_key": "zai",
            "display_name": "Z.AI",
            "provider_type": "zai_platform",
            "default_base_url": ZAI_BASE_URL,
            "documentation_url": "https://docs.z.ai/",
            "status": "active",
            "metadata_json": {},
            "updated_at": now,
        }
        if existing is not None:
            return str(existing["id"])
        provider_id = new_id()
        self.session.execute(
            insert(ai_providers_table).values(id=provider_id, created_at=now, **values)
        )
        return provider_id

    def _upsert_account(self, provider_id: str) -> str:
        now = utc_now()
        row = (
            self.session.execute(
                select(ai_provider_accounts_table).where(
                    ai_provider_accounts_table.c.ai_provider_id == provider_id,
                    ai_provider_accounts_table.c.display_name == "Default Z.AI account",
                )
            )
            .mappings()
            .first()
        )
        values = {
            "ai_provider_id": provider_id,
            "display_name": "Default Z.AI account",
            "base_url": ZAI_BASE_URL,
            "auth_secret_ref": "env:PUR_ZAI_API_KEY",
            "plan_type": "unknown",
            "enabled": True,
            "priority": 10,
            "request_timeout_seconds": 60.0,
            "policy_warning_required": True,
            "metadata_json": {},
            "notes": None,
            "updated_at": now,
        }
        if row is not None:
            return str(row["id"])
        account_id = new_id()
        self.session.execute(
            insert(ai_provider_accounts_table).values(
                id=account_id,
                policy_warning_acknowledged_at=None,
                created_at=now,
                **values,
            )
        )
        return account_id

    def _upsert_model(self, provider_id: str, seed: dict[str, Any]) -> str:
        now = utc_now()
        normalized = _normalize_model(str(seed["model"]))
        existing = (
            self.session.execute(
                select(ai_models_table).where(
                    ai_models_table.c.ai_provider_id == provider_id,
                    ai_models_table.c.normalized_model_name == normalized,
                )
            )
            .mappings()
            .first()
        )
        model_type = str(seed["type"])
        capabilities = _zai_model_capabilities(normalized_model=normalized, model_type=model_type)
        values = {
            "ai_provider_id": provider_id,
            "provider_model_name": seed["model"],
            "normalized_model_name": normalized,
            "display_name": seed["model"],
            "model_type": model_type,
            "context_window_tokens": None,
            "max_output_tokens": None,
            "supports_structured_output": capabilities["supports_structured_output"],
            "supports_json_mode": capabilities["supports_json_mode"],
            "supports_thinking": capabilities["supports_thinking"],
            "supports_tools": capabilities["supports_tools"],
            "supports_streaming": capabilities["supports_streaming"],
            "supports_image_input": capabilities["supports_image_input"],
            "supports_document_input": capabilities["supports_document_input"],
            "supports_audio_input": capabilities["supports_audio_input"],
            "supports_video_input": capabilities["supports_video_input"],
            "default_temperature": 0.0 if model_type in {"language", "ocr"} else None,
            "status": "active",
            "source_url": capabilities["source_url"],
            "verified_at": None,
            "metadata_json": capabilities["metadata_json"],
            "updated_at": now,
        }
        if existing is not None:
            update_values = {key: value for key, value in values.items() if key != "status"}
            self.session.execute(
                update(ai_models_table)
                .where(ai_models_table.c.id == existing["id"])
                .values(**update_values)
            )
            return str(existing["id"])
        model_id = new_id()
        self.session.execute(insert(ai_models_table).values(id=model_id, created_at=now, **values))
        return model_id

    def _upsert_limit(self, provider_id: str, model_id: str, *, raw_limit: int) -> str:
        now = utc_now()
        existing = (
            self.session.execute(
                select(ai_model_limits_table).where(
                    ai_model_limits_table.c.ai_model_id == model_id,
                    ai_model_limits_table.c.limit_scope == "concurrency",
                )
            )
            .mappings()
            .first()
        )
        values = {
            "ai_provider_id": provider_id,
            "ai_model_id": model_id,
            "limit_scope": "concurrency",
            "raw_limit": raw_limit,
            "utilization_ratio": DEFAULT_UTILIZATION_RATIO,
            "effective_limit": _effective_limit(raw_limit, DEFAULT_UTILIZATION_RATIO),
            "window_seconds": None,
            "source": "operator_configured",
            "quota_multiplier_json": None,
            "source_url": None,
            "verified_at": None,
            "notes": None,
            "updated_at": now,
        }
        if existing is not None:
            return str(existing["id"])
        limit_id = new_id()
        self.session.execute(
            insert(ai_model_limits_table).values(id=limit_id, created_at=now, **values)
        )
        return limit_id

    def _upsert_agent(self, seed: dict[str, Any]) -> str:
        now = utc_now()
        existing = (
            self.session.execute(
                select(ai_agents_table).where(ai_agents_table.c.agent_key == seed["agent_key"])
            )
            .mappings()
            .first()
        )
        values = {
            "agent_key": seed["agent_key"],
            "display_name": seed["display_name"],
            "task_type": seed["task_type"],
            "input_schema_json": None,
            "output_schema_json": None,
            "default_strategy": seed["default_strategy"],
            "enabled": True,
            "metadata_json": {},
            "updated_at": now,
        }
        if existing is not None:
            return str(existing["id"])
        agent_id = new_id()
        self.session.execute(insert(ai_agents_table).values(id=agent_id, created_at=now, **values))
        return agent_id

    def _upsert_route(
        self,
        *,
        account_id: str,
        agent_id: str,
        model_id: str,
        seed: dict[str, Any],
    ) -> str:
        now = utc_now()
        existing = (
            self.session.execute(
                select(ai_agent_routes_table).where(
                    ai_agent_routes_table.c.ai_agent_id == agent_id,
                    ai_agent_routes_table.c.ai_model_id == model_id,
                    ai_agent_routes_table.c.route_role == seed["route_role"],
                )
            )
            .mappings()
            .first()
        )
        values = {
            "ai_agent_id": agent_id,
            "ai_provider_account_id": account_id,
            "ai_model_id": model_id,
            "route_role": seed["route_role"],
            "priority": seed["priority"],
            "weight": 1.0,
            "enabled": True,
            "max_input_tokens": None,
            "max_output_tokens": seed.get("max_output_tokens"),
            "temperature": 0.0,
            "thinking_enabled": False,
            "thinking_mode": "off",
            "structured_output_required": True,
            "fallback_on_error": True,
            "fallback_on_rate_limit": True,
            "fallback_on_invalid_output": True,
            "route_conditions_json": None,
            "metadata_json": {},
            "updated_at": now,
        }
        if existing is not None:
            return str(existing["id"])
        route_id = new_id()
        self.session.execute(
            insert(ai_agent_routes_table).values(id=route_id, created_at=now, **values)
        )
        return route_id

    def _provider_by_key(self, provider_key: str) -> dict[str, Any] | None:
        row = (
            self.session.execute(
                select(ai_providers_table).where(ai_providers_table.c.provider_key == provider_key)
            )
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None

    def _agent_by_key(self, agent_key: str) -> dict[str, Any] | None:
        row = (
            self.session.execute(
                select(ai_agents_table).where(ai_agents_table.c.agent_key == agent_key)
            )
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None

    def _model_by_id(self, model_id: str) -> dict[str, Any] | None:
        row = (
            self.session.execute(select(ai_models_table).where(ai_models_table.c.id == model_id))
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None

    def _default_account_id(self, provider_id: str) -> str | None:
        row = (
            self.session.execute(
                select(ai_provider_accounts_table.c.id)
                .where(
                    ai_provider_accounts_table.c.ai_provider_id == provider_id,
                    ai_provider_accounts_table.c.enabled.is_(True),
                )
                .order_by(ai_provider_accounts_table.c.priority)
            )
            .mappings()
            .first()
        )
        return str(row["id"]) if row is not None else None

    def _account_by_id(self, account_id: str) -> dict[str, Any] | None:
        row = (
            self.session.execute(
                select(ai_provider_accounts_table).where(
                    ai_provider_accounts_table.c.id == account_id
                )
            )
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None

    def _limit_by_id(self, limit_id: str) -> dict[str, Any] | None:
        row = (
            self.session.execute(
                select(ai_model_limits_table).where(ai_model_limits_table.c.id == limit_id)
            )
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None

    def _route_by_agent_model_role(
        self,
        *,
        agent_id: str,
        model_id: str,
        route_role: str,
    ) -> dict[str, Any] | None:
        row = (
            self.session.execute(
                select(ai_agent_routes_table).where(
                    ai_agent_routes_table.c.ai_agent_id == agent_id,
                    ai_agent_routes_table.c.ai_model_id == model_id,
                    ai_agent_routes_table.c.route_role == route_role,
                )
            )
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None

    def _route_payload_statement(self):
        return (
            select(
                ai_agent_routes_table.c.id,
                ai_agent_routes_table.c.ai_agent_id,
                ai_agent_routes_table.c.ai_provider_account_id,
                ai_agent_routes_table.c.ai_model_id,
                ai_agents_table.c.agent_key,
                ai_agents_table.c.task_type,
                ai_providers_table.c.provider_key.label("provider"),
                ai_provider_accounts_table.c.display_name.label("provider_account"),
                ai_models_table.c.provider_model_name.label("model"),
                ai_models_table.c.normalized_model_name,
                ai_models_table.c.model_type,
                ai_agent_routes_table.c.route_role,
                ai_agent_routes_table.c.priority,
                ai_agent_routes_table.c.weight,
                ai_agent_routes_table.c.enabled,
                ai_agent_routes_table.c.max_input_tokens,
                ai_agent_routes_table.c.max_output_tokens,
                ai_agent_routes_table.c.temperature,
                ai_agent_routes_table.c.thinking_enabled,
                ai_agent_routes_table.c.thinking_mode,
                ai_agent_routes_table.c.structured_output_required,
                ai_models_table.c.supports_structured_output,
                ai_models_table.c.supports_json_mode,
                ai_models_table.c.supports_thinking,
                ai_models_table.c.supports_tools,
                ai_models_table.c.supports_streaming,
                ai_models_table.c.supports_image_input,
                ai_models_table.c.supports_document_input,
                ai_models_table.c.metadata_json.label("model_metadata_json"),
                ai_agent_routes_table.c.fallback_on_error,
                ai_agent_routes_table.c.fallback_on_rate_limit,
                ai_agent_routes_table.c.fallback_on_invalid_output,
                ai_agent_routes_table.c.route_conditions_json,
                ai_agent_routes_table.c.metadata_json,
                ai_agent_routes_table.c.created_at,
                ai_agent_routes_table.c.updated_at,
            )
            .select_from(
                ai_agent_routes_table.join(
                    ai_agents_table,
                    ai_agent_routes_table.c.ai_agent_id == ai_agents_table.c.id,
                )
                .join(
                    ai_provider_accounts_table,
                    ai_agent_routes_table.c.ai_provider_account_id
                    == ai_provider_accounts_table.c.id,
                )
                .join(
                    ai_models_table,
                    ai_agent_routes_table.c.ai_model_id == ai_models_table.c.id,
                )
                .join(
                    ai_providers_table,
                    ai_models_table.c.ai_provider_id == ai_providers_table.c.id,
                )
            )
            .order_by(
                ai_agents_table.c.agent_key,
                ai_agent_routes_table.c.route_role,
                ai_agent_routes_table.c.priority,
            )
        )

    @staticmethod
    def _limit_payload(row: dict[str, Any] | None) -> dict[str, Any] | None:
        return dict(row) if row is not None else None


def _effective_limit(raw_limit: int, utilization_ratio: float) -> int:
    return max(1, floor(max(1, raw_limit) * max(0.0, min(1.0, utilization_ratio))))


def _route_selection_from_row(row: dict[str, Any]) -> AiAgentRouteSelection:
    data = dict(row)
    model_metadata = data.pop("model_metadata_json") or {}
    if not isinstance(model_metadata, dict):
        model_metadata = {}
    data["endpoint_family"] = _optional_string(model_metadata.get("endpoint_family"))
    thinking_values = model_metadata.get("thinking_control_values")
    data["thinking_control_values"] = (
        [str(value) for value in thinking_values] if isinstance(thinking_values, list) else []
    )
    data["thinking_mode"] = _normalize_thinking_mode(
        data.get("thinking_mode"),
        thinking_enabled=bool(data.get("thinking_enabled")),
    )
    return AiAgentRouteSelection(**data)


def _zai_model_capabilities(*, normalized_model: str, model_type: str) -> dict[str, Any]:
    endpoint_family = _zai_endpoint_family(normalized_model=normalized_model, model_type=model_type)
    supports_thinking = normalized_model in ZAI_THINKING_MODELS
    supports_structured_output = normalized_model in ZAI_STRUCTURED_OUTPUT_MODELS
    supports_json_mode = supports_structured_output
    supports_vision_input = normalized_model in ZAI_VISION_LANGUAGE_MODELS
    is_ocr = normalized_model == "glm-ocr"
    is_language = model_type == "language"
    metadata: dict[str, Any] = {
        "endpoint_family": endpoint_family,
        "thinking_control_style": "binary" if supports_thinking else "unsupported",
        "thinking_control_values": ["enabled", "disabled"] if supports_thinking else [],
        "provider_neutral_thinking_modes": ["off", "on"] if supports_thinking else ["off"],
        "structured_output_mode": "json_object" if supports_json_mode else None,
        "capability_source_urls": _zai_capability_source_urls(
            endpoint_family=endpoint_family,
            supports_thinking=supports_thinking,
            supports_structured_output=supports_structured_output,
        ),
    }
    return {
        "supports_structured_output": supports_structured_output,
        "supports_json_mode": supports_json_mode,
        "supports_thinking": supports_thinking,
        "supports_tools": is_language and endpoint_family == "chat_completions",
        "supports_streaming": is_language and endpoint_family == "chat_completions",
        "supports_image_input": supports_vision_input or is_ocr,
        "supports_document_input": supports_vision_input or is_ocr,
        "supports_audio_input": model_type == "realtime_audio_video",
        "supports_video_input": model_type in {"video_generation", "realtime_audio_video"}
        or supports_vision_input,
        "source_url": _zai_source_url(endpoint_family=endpoint_family),
        "metadata_json": metadata,
    }


def _zai_endpoint_family(*, normalized_model: str, model_type: str) -> str:
    if normalized_model == "glm-ocr":
        return "layout_parsing"
    if model_type == "image_generation":
        return "image_generation"
    if model_type == "video_generation":
        return "video_generation"
    if model_type == "realtime_audio_video":
        return "realtime_audio_video"
    return "chat_completions"


def _zai_source_url(*, endpoint_family: str) -> str:
    if endpoint_family == "layout_parsing":
        return ZAI_OCR_DOC_URL
    return ZAI_CHAT_COMPLETION_DOC_URL


def _zai_capability_source_urls(
    *,
    endpoint_family: str,
    supports_thinking: bool,
    supports_structured_output: bool,
) -> list[str]:
    urls = [ZAI_OCR_DOC_URL if endpoint_family == "layout_parsing" else ZAI_CHAT_COMPLETION_DOC_URL]
    if supports_thinking:
        urls.append(ZAI_THINKING_DOC_URL)
    if supports_structured_output:
        urls.append(ZAI_STRUCTURED_OUTPUT_DOC_URL)
    return urls


def _normalize_model(model: str) -> str:
    return model.strip().casefold().replace("_", "-")


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _normalize_thinking_mode(value: Any, *, thinking_enabled: bool = False) -> str:
    if value is None:
        return "on" if thinking_enabled else "off"
    normalized = str(value).strip().casefold().replace("_", "-")
    if normalized in {"", "false", "disabled", "disable", "none", "0", "no"}:
        return "off"
    if normalized in {"true", "enabled", "enable", "1", "yes"}:
        return "on"
    return normalized


def _thinking_enabled_from_mode(thinking_mode: str) -> bool:
    return thinking_mode not in {"off", "disabled", "none", "0", "false"}
