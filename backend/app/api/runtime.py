from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.core.config import get_settings
from app.db.session import create_sessionmaker
from app.infrastructure.persistence.runtime_repository import PostgresRuntimeRepository

router = APIRouter(prefix="/runtime", tags=["runtime"])


class RuntimeLogEntry(BaseModel):
    created_at: datetime
    service: str
    level: str
    message: str
    payload: dict[str, Any]


class RuntimeLogsResponse(BaseModel):
    items: list[RuntimeLogEntry]
    total: int
    limit: int
    offset: int


class ServiceStatusItem(BaseModel):
    service: str
    status: str
    details: dict[str, Any]


class SystemStatusResponse(BaseModel):
    services: list[ServiceStatusItem]


def get_runtime_repository() -> PostgresRuntimeRepository:
    return PostgresRuntimeRepository(create_sessionmaker())


@router.get("/logs", response_model=RuntimeLogsResponse)
async def list_runtime_logs(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    service: str | None = Query(default=None),
    level: str | None = Query(default=None),
    q: str | None = Query(default=None, min_length=1),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    repository: PostgresRuntimeRepository = Depends(get_runtime_repository),
) -> RuntimeLogsResponse:
    settings = get_settings()
    effective_limit = min(
        limit or settings.runtime_log_default_limit,
        settings.runtime_log_max_limit,
    )
    await repository.enforce_log_retention(
        enrichment_event_rows=settings.runtime_enrichment_event_retention_rows,
        notification_outbox_rows=settings.runtime_notification_outbox_retention_rows,
    )
    result = await repository.list_logs(
        limit=effective_limit,
        offset=offset,
        service=service,
        level=level,
        q=q,
        created_from=created_from,
        created_to=created_to,
    )
    return RuntimeLogsResponse(
        items=[RuntimeLogEntry(**item) for item in result["items"]],
        total=int(result["total"]),
        limit=effective_limit,
        offset=offset,
    )


@router.get("/status", response_model=SystemStatusResponse)
async def get_system_status(
    repository: PostgresRuntimeRepository = Depends(get_runtime_repository),
) -> SystemStatusResponse:
    return SystemStatusResponse(
        services=[ServiceStatusItem(**item) for item in await repository.system_status()]
    )
