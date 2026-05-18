from __future__ import annotations

from uuid import UUID

from app.worker.celery_app import celery_app

LLM_QUEUE_NAME = "llm"
LLM_TASK_NAME = "app.worker.tasks.verify_llm_run"


class CeleryLlmTaskPublisher:
    async def publish(self, run_id: UUID) -> None:
        celery_app.send_task(LLM_TASK_NAME, args=[str(run_id)], queue=LLM_QUEUE_NAME)
