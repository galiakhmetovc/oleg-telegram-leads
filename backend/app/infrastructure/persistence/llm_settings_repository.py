from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.llm_settings import LlmRoute, LlmRouteConditions, LlmSettings, default_llm_settings
from app.infrastructure.persistence.tables import llm_settings

LLM_SETTINGS_ID = "default"


class PostgresLlmSettingsRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        default_model: str,
        default_endpoint: str,
        default_timeout_seconds: float,
    ) -> None:
        self._session_factory = session_factory
        self._default_model = default_model
        self._default_endpoint = default_endpoint
        self._default_timeout_seconds = default_timeout_seconds

    async def get_settings(self) -> LlmSettings:
        async with self._session_factory() as session:
            result = await session.execute(sa.select(llm_settings).where(llm_settings.c.id == LLM_SETTINGS_ID))
            row = result.mappings().first()
        if row is None:
            return default_llm_settings(
                model=self._default_model,
                endpoint=self._default_endpoint,
                timeout_seconds=self._default_timeout_seconds,
            )
        return _settings_from_row(row)

    async def save_settings(self, settings: LlmSettings) -> LlmSettings:
        updated_at = datetime.now(UTC)
        config = _settings_to_config(settings)
        statement = (
            insert(llm_settings)
            .values(id=LLM_SETTINGS_ID, config=config, updated_at=updated_at)
            .on_conflict_do_update(
                index_elements=[llm_settings.c.id],
                set_={"config": config, "updated_at": updated_at},
            )
        )
        async with self._session_factory() as session:
            await session.execute(statement)
            await session.commit()
        return LlmSettings(
            enabled=settings.enabled,
            model=settings.model,
            endpoint=settings.endpoint,
            timeout_seconds=settings.timeout_seconds,
            system_prompt=settings.system_prompt,
            routes=settings.routes,
            updated_at=updated_at,
        )


def _settings_from_row(row: Any) -> LlmSettings:
    config = row["config"] or {}
    return LlmSettings(
        enabled=bool(config.get("enabled", True)),
        model=str(config.get("model") or "lead-qwen-ru"),
        endpoint=str(config.get("endpoint") or "http://localhost:11434/api/chat"),
        timeout_seconds=float(config.get("timeout_seconds") or 60),
        system_prompt=str(config.get("system_prompt") or ""),
        routes=[_route_from_dict(item) for item in config.get("routes", [])],
        updated_at=row["updated_at"],
    )


def _settings_to_config(settings: LlmSettings) -> dict[str, Any]:
    return {
        "enabled": settings.enabled,
        "model": settings.model,
        "endpoint": settings.endpoint,
        "timeout_seconds": settings.timeout_seconds,
        "system_prompt": settings.system_prompt,
        "routes": [_route_to_dict(route) for route in settings.routes],
    }


def _route_from_dict(data: dict[str, Any]) -> LlmRoute:
    return LlmRoute(
        id=str(data["id"]),
        name=str(data["name"]),
        enabled=bool(data.get("enabled", True)),
        priority=int(data.get("priority", 0)),
        match_mode="any" if data.get("match_mode") == "any" else "all",
        conditions=_conditions_from_dict(data.get("conditions") or {}),
    )


def _route_to_dict(route: LlmRoute) -> dict[str, Any]:
    return {
        "id": route.id,
        "name": route.name,
        "enabled": route.enabled,
        "priority": route.priority,
        "match_mode": route.match_mode,
        "conditions": _conditions_to_dict(route.conditions),
    }


def _conditions_from_dict(data: dict[str, Any]) -> LlmRouteConditions:
    return LlmRouteConditions(
        source_chat_ids=_str_list(data.get("source_chat_ids")),
        score_min=_optional_int(data.get("score_min")),
        score_max=_optional_int(data.get("score_max")),
        temperatures=_str_list(data.get("temperatures")),
        review_lanes=_str_list(data.get("review_lanes")),
        include_signal_types=_str_list(data.get("include_signal_types")),
        exclude_signal_types=_str_list(data.get("exclude_signal_types")),
        include_fact_types=_str_list(data.get("include_fact_types")),
        exclude_fact_types=_str_list(data.get("exclude_fact_types")),
        include_reason_keys=_str_list(data.get("include_reason_keys")),
        exclude_reason_keys=_str_list(data.get("exclude_reason_keys")),
        include_solution_area_types=_str_list(data.get("include_solution_area_types")),
        exclude_solution_area_types=_str_list(data.get("exclude_solution_area_types")),
        include_customer_segment_types=_str_list(data.get("include_customer_segment_types")),
        exclude_customer_segment_types=_str_list(data.get("exclude_customer_segment_types")),
    )


def _conditions_to_dict(conditions: LlmRouteConditions) -> dict[str, Any]:
    return {
        "source_chat_ids": conditions.source_chat_ids,
        "score_min": conditions.score_min,
        "score_max": conditions.score_max,
        "temperatures": conditions.temperatures,
        "review_lanes": conditions.review_lanes,
        "include_signal_types": conditions.include_signal_types,
        "exclude_signal_types": conditions.exclude_signal_types,
        "include_fact_types": conditions.include_fact_types,
        "exclude_fact_types": conditions.exclude_fact_types,
        "include_reason_keys": conditions.include_reason_keys,
        "exclude_reason_keys": conditions.exclude_reason_keys,
        "include_solution_area_types": conditions.include_solution_area_types,
        "exclude_solution_area_types": conditions.exclude_solution_area_types,
        "include_customer_segment_types": conditions.include_customer_segment_types,
        "exclude_customer_segment_types": conditions.exclude_customer_segment_types,
    }


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
