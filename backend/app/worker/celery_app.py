from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "pur_leads_v2",
    broker=settings.redis_url,
    include=["app.worker.tasks"],
)
celery_app.conf.update(
    task_acks_late=True,
    task_serializer="json",
    accept_content=["json"],
    result_backend=None,
)
