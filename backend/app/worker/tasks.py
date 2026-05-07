from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from app.core.config import get_settings
from app.db.session import create_sessionmaker
from app.infrastructure.nlp.config_loader import load_nlp_config
from app.infrastructure.nlp.russian_text_enricher import RussianTextEnricher
from app.infrastructure.persistence.enrichment_repository import PostgresEnrichmentJobRepository
from app.worker.celery_app import celery_app


@celery_app.task(name="app.worker.tasks.enrich_text_job")  # type: ignore[untyped-decorator]
def enrich_text_job(job_id: str) -> None:
    asyncio.run(_run_enrichment_job(UUID(job_id)))


async def _run_enrichment_job(job_id: UUID) -> None:
    settings = get_settings()
    repository = PostgresEnrichmentJobRepository(create_sessionmaker())
    snapshot = await repository.get_job(job_id)
    if snapshot is None:
        return

    config = load_nlp_config(settings.nlp_config_dir)
    stage_names = [stage.name for stage in config.enabled_stages]
    stage_count = len(stage_names)
    stage_index_by_name = {stage_name: index for index, stage_name in enumerate(stage_names, start=1)}

    await repository.mark_running(job_id, stage_count=stage_count)

    try:
        enricher = RussianTextEnricher(config)

        loop = asyncio.get_running_loop()

        def progress(stage_name: str, progress_percent: int, message: str) -> None:
            future = asyncio.run_coroutine_threadsafe(
                repository.record_stage_progress(
                    job_id,
                    stage_name=stage_name,
                    stage_index=stage_index_by_name.get(stage_name, 0),
                    stage_count=stage_count,
                    progress_percent=progress_percent,
                    message=message,
                ),
                loop,
            )
            future.result()

        result = await asyncio.to_thread(enricher.enrich, snapshot.input_text, progress)
        await repository.complete_job(job_id, result)
    except Exception as exc:
        await repository.fail_job(job_id, _error_payload(exc))
        raise


def _error_payload(exc: Exception) -> dict[str, Any]:
    return {"type": type(exc).__name__, "message": str(exc)}
