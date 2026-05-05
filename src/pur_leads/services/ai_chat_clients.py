"""Reusable AI chat client construction from the provider registry."""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy.orm import Session

from pur_leads.integrations.ai.zai_client import ZaiChatCompletionClient
from pur_leads.services.ai_concurrency import AiModelConcurrencyService
from pur_leads.services.ai_registry import AiAgentRouteSelection, AiRegistryService
from pur_leads.services.secrets import SecretRefService
from pur_leads.services.settings import SettingsService


def select_ai_route(
    session: Session,
    *,
    agent_key: str,
    route_role: str,
) -> AiAgentRouteSelection | None:
    routes = AiRegistryService(session).select_routes(agent_key=agent_key, route_role=route_role)
    return routes[0] if routes else None


def build_zai_chat_client_for_route(
    session: Session,
    *,
    route: AiAgentRouteSelection,
    settings: Any,
    worker_name: str,
    task_type: str,
    default_timeout_seconds: float | None = None,
) -> ZaiChatCompletionClient:
    if route.provider != "zai":
        raise ValueError(f"Unsupported AI provider for chat route: {route.provider}")
    api_key = zai_api_key_for_route(session, settings, route)
    if not api_key:
        raise ValueError("Z.AI API key is not configured for selected route")
    settings_service = SettingsService(session)
    return ZaiChatCompletionClient(
        api_key=api_key,
        base_url=route.base_url,
        timeout_seconds=llm_request_timeout_seconds(
            settings_service,
            task_type=task_type,
            model=route.model,
            default=(
                default_timeout_seconds
                if default_timeout_seconds is not None
                else float(getattr(settings, "catalog_llm_timeout_seconds", 60.0))
            ),
        ),
        connect_timeout_seconds=llm_connect_timeout_seconds(settings_service),
        concurrency_limiter=build_ai_model_concurrency_limiter(
            session,
            worker_name=worker_name,
        ),
        provider_account_id=route.provider_account_id,
        thinking_type=zai_thinking_type_for_route(route),
        response_format=zai_response_format_for_route(route),
        worker_name=worker_name,
    )


def build_ai_model_concurrency_limiter(session: Session, *, worker_name: str):
    settings_service = SettingsService(session)
    if not bool(settings_service.get("ai_model_concurrency_enabled")):
        return None
    configured_limits = settings_service.repository.get("ai_model_concurrency_limits")
    registry_limits = AiRegistryService(session).model_concurrency_limits(provider_key="zai")
    limits_value = (
        configured_limits.value_json
        if configured_limits is not None
        else registry_limits or settings_service.get("ai_model_concurrency_limits")
    )
    limits = limits_value if isinstance(limits_value, dict) else None
    return AiModelConcurrencyService(
        session,
        limits=limits,
        utilization_ratio=float(
            setting_or_default(settings_service, "ai_model_concurrency_utilization_ratio", 0.8)
        ),
        default_limit=int(
            setting_or_default(settings_service, "ai_model_concurrency_default_limit", 1)
        ),
        lease_seconds=int(
            setting_or_default(settings_service, "ai_model_concurrency_lease_seconds", 180)
        ),
        retry_after_seconds=int(
            setting_or_default(settings_service, "ai_model_concurrency_retry_after_seconds", 5)
        ),
    )


def llm_connect_timeout_seconds(settings_service: SettingsService) -> float:
    return float(setting_value_or_default(settings_service, "llm_connect_timeout_seconds", 5))


def llm_request_timeout_seconds(
    settings_service: SettingsService,
    *,
    task_type: str,
    model: str,
    default: float,
) -> float:
    hard_cap = float(
        setting_value_or_default(settings_service, "llm_request_timeout_hard_cap_seconds", 180)
    )
    by_model = setting_value_or_default(
        settings_service, "llm_request_timeout_seconds_by_model", {}
    )
    by_task = setting_value_or_default(settings_service, "llm_request_timeout_seconds_by_task", {})
    selected = _timeout_from_map(by_model, model.casefold())
    if selected is None:
        selected = _timeout_from_map(by_task, task_type.casefold())
    if selected is None:
        selected = float(default)
    return min(max(1.0, float(selected)), max(1.0, hard_cap))


def zai_thinking_type_for_route(route: AiAgentRouteSelection | None) -> str | None:
    if route is None or not route.supports_thinking:
        return None
    mode = str(route.thinking_mode or ("on" if route.thinking_enabled else "off")).casefold()
    if mode in {"off", "disabled", "none", "false", "0"}:
        return "disabled"
    return "enabled"


def zai_response_format_for_route(route: AiAgentRouteSelection | None) -> dict[str, str] | None:
    if route is None or not route.structured_output_required:
        return None
    if not (route.supports_structured_output or route.supports_json_mode):
        return None
    return {"type": "json_object"}


def zai_api_key_for_route(
    session: Session,
    settings: Any,
    route: AiAgentRouteSelection | None,
) -> str | None:
    if route is None or not route.auth_secret_ref:
        return setting_secret_or_env(
            session,
            "zai_api_key_secret_ref",
            getattr(settings, "zai_api_key", None) or env_str("PUR_ZAI_API_KEY", "ZAI_API_KEY"),
        )
    value = resolve_ai_auth_secret_ref(session, route.auth_secret_ref)
    if value:
        return value
    if route.auth_secret_ref == "env:PUR_ZAI_API_KEY":
        return setting_secret_or_env(
            session,
            "zai_api_key_secret_ref",
            getattr(settings, "zai_api_key", None) or env_str("PUR_ZAI_API_KEY", "ZAI_API_KEY"),
        )
    return None


def resolve_ai_auth_secret_ref(session: Session, auth_secret_ref: str) -> str | None:
    ref = auth_secret_ref.strip()
    if not ref:
        return None
    try:
        if ref.startswith("secret_ref:"):
            return SecretRefService(session).resolve_value(ref.split(":", 1)[1])
        if ref.startswith("env:"):
            return env_str(ref.split(":", 1)[1])
        return SecretRefService(session).resolve_value(ref)
    except (FileNotFoundError, KeyError, ValueError):
        return None


def setting_secret_or_env(session: Session, setting_key: str, fallback: str | None) -> str | None:
    try:
        return SecretRefService(session).resolve_setting_secret(setting_key) or fallback
    except (FileNotFoundError, KeyError, ValueError):
        return fallback


def setting_or_default(settings_service: SettingsService, key: str, default: Any) -> Any:
    record = settings_service.repository.get(key)
    return record.value_json if record is not None else default


def setting_value_or_default(settings_service: SettingsService, key: str, default: Any) -> Any:
    try:
        value = settings_service.get(key)
    except Exception:
        return default
    return default if value is None else value


def env_str(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def _timeout_from_map(value: Any, key: str) -> float | None:
    if not isinstance(value, dict):
        return None
    for raw_key, raw_value in value.items():
        if str(raw_key).casefold() != key:
            continue
        try:
            timeout = float(raw_value)
        except (TypeError, ValueError):
            return None
        return timeout if timeout > 0 else None
    return None
