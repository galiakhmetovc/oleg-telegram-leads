from __future__ import annotations

import pytest

from app.cli import notification_summary_worker


class RecordingSummaryUseCase:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self) -> None:
        self.calls += 1


@pytest.mark.asyncio
async def test_summary_worker_runs_once(monkeypatch: pytest.MonkeyPatch) -> None:
    use_case = RecordingSummaryUseCase()
    monkeypatch.setattr(notification_summary_worker, "_build_use_case", lambda: use_case)

    await notification_summary_worker._run(once=True, interval=30)

    assert use_case.calls == 1
