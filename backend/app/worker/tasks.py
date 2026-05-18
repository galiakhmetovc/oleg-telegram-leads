from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.application.notifications.use_cases import QueueNotificationsForEnrichment
from app.application.notifications.use_cases import QueueLlmLeadNotification
from app.application.llm_verification.use_cases import ExecuteQueuedLlmVerification, QueueMatchedLlmVerifications
from app.application.notifications.routing import NotificationMessageContext
from app.core.config import get_settings
from app.db.session import create_sessionmaker
from app.domain.enrichment import EnrichmentStatus
from app.infrastructure.llm.ollama_client import OllamaLlmVerificationClient
from app.infrastructure.nlp.config_loader import NlpPipelineConfig
from app.infrastructure.nlp.config_loader import load_nlp_config_from_documents
from app.infrastructure.nlp.config_loader import read_nlp_config_documents
from app.infrastructure.nlp.russian_text_enricher import RussianTextEnricher
from app.infrastructure.persistence.enrichment_repository import PostgresEnrichmentJobRepository
from app.infrastructure.persistence.llm_settings_repository import PostgresLlmSettingsRepository
from app.infrastructure.persistence.llm_verification_repository import PostgresLlmVerificationRepository
from app.infrastructure.persistence.notification_settings_repository import (
    PostgresNotificationSettingsRepository,
)
from app.infrastructure.persistence.notification_outbox_repository import (
    PostgresNotificationOutboxRepository,
)
from app.infrastructure.persistence.nlp_config_repository import PostgresNlpConfigRepository
from app.infrastructure.persistence.telegram_ingestion_repository import (
    PostgresTelegramIngestionRepository,
)
from app.infrastructure.queue.llm_publisher import CeleryLlmTaskPublisher
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


PIPELINE_CACHE_MAX_SIZE = 3


@dataclass(frozen=True)
class CompiledPipeline:
    revision_id: UUID
    revision: int
    stage_names: tuple[str, ...]
    stage_index_by_name: dict[str, int]
    enricher: RussianTextEnricher


_PIPELINE_CACHE: OrderedDict[UUID, CompiledPipeline] = OrderedDict()


@celery_app.task(name="app.worker.tasks.enrich_text_job")  # type: ignore[untyped-decorator]
def enrich_text_job(job_id: str) -> None:
    asyncio.run(_run_enrichment_job(UUID(job_id)))


@celery_app.task(name="app.worker.tasks.verify_llm_run", queue="llm")  # type: ignore[untyped-decorator]
def verify_llm_run(run_id: str) -> None:
    asyncio.run(_run_llm_verification(UUID(run_id)))


async def _run_llm_verification(run_id: UUID) -> None:
    settings = get_settings()
    session_factory = create_sessionmaker()
    llm_settings = await PostgresLlmSettingsRepository(
        session_factory,
        default_model=settings.llm_verification_model,
        default_endpoint=settings.llm_verification_endpoint,
        default_timeout_seconds=settings.llm_verification_timeout_seconds,
    ).get_settings()
    run = await ExecuteQueuedLlmVerification(
        repository=PostgresLlmVerificationRepository(session_factory),
        client=OllamaLlmVerificationClient(
            endpoint=llm_settings.endpoint,
            timeout_seconds=llm_settings.timeout_seconds,
        ),
    ).execute(run_id)
    if run is not None and run.status == "completed":
        await _queue_llm_notification(session_factory, run)


async def _run_enrichment_job(job_id: UUID) -> None:
    settings = get_settings()
    session_factory = create_sessionmaker()
    repository = PostgresEnrichmentJobRepository(session_factory)
    snapshot = await repository.get_job(job_id)
    if snapshot is None or snapshot.status != EnrichmentStatus.QUEUED:
        return

    config_repository = PostgresNlpConfigRepository(session_factory)
    try:
        config_revision = await config_repository.get_active_or_seed(
            read_nlp_config_documents(settings.nlp_config_dir)
        )
        pipeline = _compiled_pipeline_for_revision(
            config_revision.id,
            config_revision.revision,
            config_revision.documents,
        )
    except Exception as exc:
        await repository.fail_job(job_id, _error_payload(exc))
        raise
    stage_count = len(pipeline.stage_names)

    snapshot = await repository.claim_queued_job(
        job_id,
        stage_count=stage_count,
        nlp_config_revision_id=config_revision.id,
        nlp_config_revision=config_revision.revision,
    )
    if snapshot is None:
        return

    try:
        loop = asyncio.get_running_loop()

        def progress(stage_name: str, progress_percent: int, message: str) -> None:
            future = asyncio.run_coroutine_threadsafe(
                repository.record_stage_progress(
                    job_id,
                    stage_name=stage_name,
                    stage_index=pipeline.stage_index_by_name.get(stage_name, 0),
                    stage_count=stage_count,
                    progress_percent=progress_percent,
                    message=message,
                ),
                loop,
            )
            future.result()

        result = await asyncio.to_thread(pipeline.enricher.enrich, snapshot.input_text, progress)
        await repository.complete_job(job_id, result)
        await _queue_notifications(session_factory, result, job_id)
        await _queue_llm_verifications(session_factory, job_id)
    except Exception as exc:
        await repository.fail_job(job_id, _error_payload(exc))
        raise


def _compiled_pipeline_for_revision(
    revision_id: UUID,
    revision: int,
    documents: dict[str, dict[str, Any]],
) -> CompiledPipeline:
    cached = _PIPELINE_CACHE.get(revision_id)
    if cached is not None:
        _PIPELINE_CACHE.move_to_end(revision_id)
        return cached

    config = load_nlp_config_from_documents(documents)
    pipeline = _compile_pipeline(revision_id, revision, config)
    _PIPELINE_CACHE[revision_id] = pipeline
    while len(_PIPELINE_CACHE) > PIPELINE_CACHE_MAX_SIZE:
        _PIPELINE_CACHE.popitem(last=False)
    return pipeline


def _compile_pipeline(
    revision_id: UUID,
    revision: int,
    config: NlpPipelineConfig,
) -> CompiledPipeline:
    stage_names = tuple(stage.name for stage in config.enabled_stages)
    return CompiledPipeline(
        revision_id=revision_id,
        revision=revision,
        stage_names=stage_names,
        stage_index_by_name={stage_name: index for index, stage_name in enumerate(stage_names, start=1)},
        enricher=RussianTextEnricher(config),
    )


async def _queue_notifications(
    session_factory: Any,
    result: Any,
    job_id: UUID,
) -> None:
    try:
        context = await _notification_context(session_factory, job_id)
        if context is None:
            logger.info("Skipping notifications for non-Telegram enrichment job %s", job_id)
            return
        await QueueNotificationsForEnrichment(
            settings_repository=PostgresNotificationSettingsRepository(session_factory),
            outbox_repository=PostgresNotificationOutboxRepository(session_factory),
        ).execute(result, context)
    except Exception:
        logger.exception("Notification queueing failed after enrichment completion")


async def _queue_llm_verifications(
    session_factory: Any,
    job_id: UUID,
) -> None:
    try:
        settings = get_settings()
        llm_repository = PostgresLlmVerificationRepository(session_factory)
        source = await llm_repository.get_source_message_by_enrichment_job_id(job_id)
        if source is None:
            logger.info("Skipping LLM verification for non-Telegram enrichment job %s", job_id)
            return
        llm_settings = await PostgresLlmSettingsRepository(
            session_factory,
            default_model=settings.llm_verification_model,
            default_endpoint=settings.llm_verification_endpoint,
            default_timeout_seconds=settings.llm_verification_timeout_seconds,
        ).get_settings()
        await QueueMatchedLlmVerifications(
            repository=llm_repository,
            nlp_config_repository=PostgresNlpConfigRepository(session_factory),
            task_publisher=CeleryLlmTaskPublisher(),
            settings=llm_settings,
        ).execute(source)
    except Exception:
        logger.exception("LLM verification queueing failed after enrichment completion")


async def _queue_llm_notification(
    session_factory: Any,
    run: Any,
) -> None:
    try:
        llm_repository = PostgresLlmVerificationRepository(session_factory)
        source = await llm_repository.get_source_message(run.source_message_id)
        if source is None:
            logger.info("Skipping LLM notification for missing source message %s", run.source_message_id)
            return
        await QueueLlmLeadNotification(
            settings_repository=PostgresNotificationSettingsRepository(session_factory),
            outbox_repository=PostgresNotificationOutboxRepository(session_factory),
        ).execute(
            run=run,
            source=source,
            context=await _notification_context(session_factory, run.enrichment_job_id),
        )
    except Exception:
        logger.exception("LLM notification queueing failed after LLM completion")


async def _notification_context(
    session_factory: Any,
    job_id: UUID,
) -> NotificationMessageContext | None:
    source = await PostgresTelegramIngestionRepository(
        session_factory,
    ).get_source_message_context_by_job(job_id)
    if source is None:
        return None
    public_base_url = get_settings().public_base_url.rstrip("/")
    source_message_id = str(source["source_message_id"])
    telegram_message_id = int(source["telegram_message_id"])
    return NotificationMessageContext(
        source_message_id=source["source_message_id"],
        enrichment_job_id=job_id,
        telegram_message_url=_telegram_message_url(
            input_ref=str(source.get("input_ref") or ""),
            telegram_chat_id=source.get("telegram_chat_id"),
            telegram_message_id=telegram_message_id,
        ),
        app_message_url=f"{public_base_url}/#/analytics/message/{source_message_id}",
    )


def _telegram_message_url(
    *,
    input_ref: str,
    telegram_chat_id: str | None,
    telegram_message_id: int,
) -> str | None:
    normalized = input_ref.strip().rstrip("/")
    if normalized.startswith("@") and len(normalized) > 1:
        return f"https://t.me/{normalized[1:]}/{telegram_message_id}"
    if normalized.startswith("https://t.me/") and "/+" not in normalized:
        return f"{normalized}/{telegram_message_id}"
    if telegram_chat_id and telegram_chat_id.startswith("-100"):
        return f"https://t.me/c/{telegram_chat_id[4:]}/{telegram_message_id}"
    return None


def _error_payload(exc: Exception) -> dict[str, Any]:
    return {"type": type(exc).__name__, "message": str(exc)}
