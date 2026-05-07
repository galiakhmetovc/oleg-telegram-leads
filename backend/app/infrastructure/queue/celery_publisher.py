from __future__ import annotations

from uuid import UUID

from app.worker.celery_app import celery_app


class CeleryEnrichmentTaskPublisher:
    async def publish(self, job_id: UUID) -> None:
        celery_app.send_task("app.worker.tasks.enrich_text_job", args=[str(job_id)])
