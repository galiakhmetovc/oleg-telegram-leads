from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.cli import telegram_userbot_worker
from app.domain.telegram_ingestion import TelegramUserbotFloodWait


class StopWorkerLoop(RuntimeError):
    pass


@dataclass(frozen=True)
class FakeSummary:
    accounts: int = 1
    messages_created: int = 0
    duplicates: int = 0
    skipped: int = 0


class FloodThenCrashWatcher:
    calls = 0

    def __init__(self, **kwargs: object) -> None:
        pass

    async def execute(self) -> FakeSummary:
        type(self).calls += 1
        if type(self).calls == 1:
            raise TelegramUserbotFloodWait(3)
        raise RuntimeError("second reconnect")


class UnusedPoller:
    def __init__(self, **kwargs: object) -> None:
        pass

    async def execute(self) -> FakeSummary:
        return FakeSummary()


@pytest.mark.asyncio
async def test_userbot_worker_reconnects_after_flood_wait_without_reading_missing_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) == 2:
            raise StopWorkerLoop()

    monkeypatch.setattr(telegram_userbot_worker, "WatchTelegramSources", FloodThenCrashWatcher)
    monkeypatch.setattr(telegram_userbot_worker, "PollTelegramSources", UnusedPoller)
    monkeypatch.setattr("app.cli.telegram_userbot_worker.asyncio.sleep", fake_sleep)

    with pytest.raises(StopWorkerLoop):
        await telegram_userbot_worker._run(
            mode="listen",
            once=False,
            interval=20,
            batch_limit=100,
            cooldown_recovery_limit=10,
            cooldown_recovery_delay=15,
            idle_retry=60,
        )

    assert sleeps == [20, 60]
    assert FloodThenCrashWatcher.calls == 2
