from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.application.llm_verification.ports import ActiveNlpConfigReader
from app.application.llm_verification.ports import LlmTaskPublisher, LlmVerificationClient, LlmVerificationRepository
from app.application.llm_verification.settings_ports import LlmSettingsRepository
from app.application.llm_verification.use_cases import ListMessageLlmVerifications
from app.application.llm_verification.use_cases import ListLlmVerifications
from app.application.llm_verification.use_cases import QueueSourceMessageForLlm
from app.application.llm_verification.use_cases import SourceMessageForLlmVerificationNotFound
from app.core.config import get_settings
from app.db.session import create_sessionmaker
from app.infrastructure.llm.ollama_client import OllamaLlmVerificationClient
from app.infrastructure.persistence.llm_verification_repository import PostgresLlmVerificationRepository
from app.infrastructure.persistence.llm_settings_repository import PostgresLlmSettingsRepository
from app.infrastructure.persistence.nlp_config_repository import PostgresNlpConfigRepository
from app.infrastructure.queue.llm_publisher import CeleryLlmTaskPublisher

router = APIRouter(prefix="/llm-verifications", tags=["llm-verifications"])


class LlmVerificationResponse(BaseModel):
    id: UUID
    source_message_id: UUID
    enrichment_job_id: UUID
    model: str
    route_id: str | None
    schema_version: str
    status: str
    prompt: str | None
    attempts: int
    context_pack: dict[str, Any]
    response: dict[str, Any] | None
    raw_response: str | None
    error: str | None
    claimed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LlmVerificationPageResponse(BaseModel):
    total: int
    items: list[LlmVerificationResponse]


class LlmVerificationConfigResponse(BaseModel):
    model: str
    endpoint: str
    timeout_seconds: float
    execution_mode: str


def get_llm_verification_repository() -> LlmVerificationRepository:
    return PostgresLlmVerificationRepository(create_sessionmaker())


def get_nlp_config_repository() -> ActiveNlpConfigReader:
    return PostgresNlpConfigRepository(create_sessionmaker())


def get_llm_settings_repository() -> LlmSettingsRepository:
    settings = get_settings()
    return PostgresLlmSettingsRepository(
        create_sessionmaker(),
        default_model=settings.llm_verification_model,
        default_endpoint=settings.llm_verification_endpoint,
        default_timeout_seconds=settings.llm_verification_timeout_seconds,
    )


def get_llm_task_publisher() -> LlmTaskPublisher:
    return CeleryLlmTaskPublisher()


def get_llm_client() -> LlmVerificationClient:
    settings = get_settings()
    return OllamaLlmVerificationClient(
        endpoint=settings.llm_verification_endpoint,
        timeout_seconds=settings.llm_verification_timeout_seconds,
    )


def get_llm_verification_model() -> str:
    return get_settings().llm_verification_model


async def get_llm_verification_config(
    repository: LlmSettingsRepository = Depends(get_llm_settings_repository),
) -> LlmVerificationConfigResponse:
    settings = await repository.get_settings()
    return LlmVerificationConfigResponse(
        model=settings.model,
        endpoint=settings.endpoint,
        timeout_seconds=settings.timeout_seconds,
        execution_mode="celery_queue:llm",
    )


@router.get("/config", response_model=LlmVerificationConfigResponse)
async def read_llm_verification_config(
    config: LlmVerificationConfigResponse = Depends(get_llm_verification_config),
) -> LlmVerificationConfigResponse:
    return config


@router.post(
    "/messages/{source_message_id}",
    response_model=LlmVerificationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def verify_source_message(
    source_message_id: UUID,
    repository: LlmVerificationRepository = Depends(get_llm_verification_repository),
    nlp_config_repository: ActiveNlpConfigReader = Depends(get_nlp_config_repository),
    settings_repository: LlmSettingsRepository = Depends(get_llm_settings_repository),
    task_publisher: LlmTaskPublisher = Depends(get_llm_task_publisher),
) -> LlmVerificationResponse:
    try:
        settings = await settings_repository.get_settings()
        run = await QueueSourceMessageForLlm(
            repository=repository,
            nlp_config_repository=nlp_config_repository,
            settings=settings,
        ).execute(source_message_id, route_id="manual")
    except SourceMessageForLlmVerificationNotFound as exc:
        raise HTTPException(status_code=404, detail="source message not found") from exc
    await task_publisher.publish(run.id)
    return _run_response(run)


@router.get("", response_model=LlmVerificationPageResponse)
async def list_llm_verifications(
    limit: int = 50,
    offset: int = 0,
    repository: LlmVerificationRepository = Depends(get_llm_verification_repository),
) -> LlmVerificationPageResponse:
    total, runs = await ListLlmVerifications(repository=repository).execute(limit=limit, offset=offset)
    return LlmVerificationPageResponse(total=total, items=[_run_response(run) for run in runs])


@router.get("/messages/{source_message_id}", response_model=LlmVerificationPageResponse)
async def list_source_message_verifications(
    source_message_id: UUID,
    repository: LlmVerificationRepository = Depends(get_llm_verification_repository),
) -> LlmVerificationPageResponse:
    runs = await ListMessageLlmVerifications(repository=repository).execute(source_message_id)
    return LlmVerificationPageResponse(total=len(runs), items=[_run_response(run) for run in runs])


def _run_response(run: Any) -> LlmVerificationResponse:
    return LlmVerificationResponse(
        id=run.id,
        source_message_id=run.source_message_id,
        enrichment_job_id=run.enrichment_job_id,
        model=run.model,
        route_id=run.route_id,
        schema_version=run.schema_version,
        status=run.status,
        prompt=run.prompt,
        attempts=run.attempts,
        context_pack=run.context_pack,
        response=run.response,
        raw_response=run.raw_response,
        error=run.error,
        claimed_at=run.claimed_at,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )
