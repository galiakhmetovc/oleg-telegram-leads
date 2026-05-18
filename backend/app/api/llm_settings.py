from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.application.llm_verification.settings_ports import LlmSettingsRepository
from app.core.config import get_settings
from app.db.session import create_sessionmaker
from app.domain.llm_settings import LlmRoute, LlmRouteConditions, LlmSettings
from app.infrastructure.persistence.llm_settings_repository import PostgresLlmSettingsRepository

router = APIRouter(prefix="/settings/llm", tags=["settings"])


class LlmRouteConditionsPayload(BaseModel):
    source_chat_ids: list[str] = Field(default_factory=list)
    score_min: int | None = None
    score_max: int | None = None
    temperatures: list[str] = Field(default_factory=list)
    review_lanes: list[str] = Field(default_factory=list)
    include_signal_types: list[str] = Field(default_factory=list)
    exclude_signal_types: list[str] = Field(default_factory=list)
    include_fact_types: list[str] = Field(default_factory=list)
    exclude_fact_types: list[str] = Field(default_factory=list)
    include_reason_keys: list[str] = Field(default_factory=list)
    exclude_reason_keys: list[str] = Field(default_factory=list)
    include_solution_area_types: list[str] = Field(default_factory=list)
    exclude_solution_area_types: list[str] = Field(default_factory=list)
    include_customer_segment_types: list[str] = Field(default_factory=list)
    exclude_customer_segment_types: list[str] = Field(default_factory=list)


class LlmRoutePayload(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    enabled: bool = True
    priority: int = 0
    match_mode: str = "all"
    conditions: LlmRouteConditionsPayload = Field(default_factory=LlmRouteConditionsPayload)


class LlmSettingsPayload(BaseModel):
    enabled: bool
    model: str = Field(min_length=1)
    endpoint: str = Field(min_length=1)
    timeout_seconds: float = Field(gt=0)
    system_prompt: str = Field(min_length=1)
    routes: list[LlmRoutePayload] = Field(default_factory=list)
    updated_at: datetime | None = None


def get_llm_settings_repository() -> LlmSettingsRepository:
    settings = get_settings()
    return PostgresLlmSettingsRepository(
        create_sessionmaker(),
        default_model=settings.llm_verification_model,
        default_endpoint=settings.llm_verification_endpoint,
        default_timeout_seconds=settings.llm_verification_timeout_seconds,
    )


@router.get("", response_model=LlmSettingsPayload)
async def read_llm_settings(
    repository: LlmSettingsRepository = Depends(get_llm_settings_repository),
) -> LlmSettingsPayload:
    return _settings_payload(await repository.get_settings())


@router.put("", response_model=LlmSettingsPayload)
async def update_llm_settings(
    payload: LlmSettingsPayload,
    repository: LlmSettingsRepository = Depends(get_llm_settings_repository),
) -> LlmSettingsPayload:
    saved = await repository.save_settings(_settings_from_payload(payload))
    return _settings_payload(saved)


def _settings_payload(settings: LlmSettings) -> LlmSettingsPayload:
    return LlmSettingsPayload(
        enabled=settings.enabled,
        model=settings.model,
        endpoint=settings.endpoint,
        timeout_seconds=settings.timeout_seconds,
        system_prompt=settings.system_prompt,
        routes=[_route_payload(route) for route in settings.routes],
        updated_at=settings.updated_at,
    )


def _settings_from_payload(payload: LlmSettingsPayload) -> LlmSettings:
    return LlmSettings(
        enabled=payload.enabled,
        model=payload.model,
        endpoint=payload.endpoint,
        timeout_seconds=payload.timeout_seconds,
        system_prompt=payload.system_prompt,
        routes=[_route_from_payload(route) for route in payload.routes],
        updated_at=payload.updated_at,
    )


def _route_payload(route: LlmRoute) -> LlmRoutePayload:
    return LlmRoutePayload(
        id=route.id,
        name=route.name,
        enabled=route.enabled,
        priority=route.priority,
        match_mode=route.match_mode,
        conditions=LlmRouteConditionsPayload(**route.conditions.__dict__),
    )


def _route_from_payload(payload: LlmRoutePayload) -> LlmRoute:
    return LlmRoute(
        id=payload.id,
        name=payload.name,
        enabled=payload.enabled,
        priority=payload.priority,
        match_mode="any" if payload.match_mode == "any" else "all",
        conditions=LlmRouteConditions(**payload.conditions.model_dump()),
    )
