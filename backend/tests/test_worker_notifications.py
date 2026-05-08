from __future__ import annotations

from uuid import uuid4

import pytest

from app.worker import tasks


@pytest.mark.asyncio
async def test_worker_skips_notifications_for_non_telegram_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    queued: list[object] = []

    async def no_context(session_factory: object, job_id: object) -> None:
        return None

    class RecordingQueueNotifications:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def execute(self, result: object, context: object) -> list[object]:
            queued.append((result, context))
            return []

    monkeypatch.setattr(tasks, "_notification_context", no_context)
    monkeypatch.setattr(tasks, "QueueNotificationsForEnrichment", RecordingQueueNotifications)

    await tasks._queue_notifications(object(), object(), uuid4())

    assert queued == []
