from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.application.notifications.summary import NotificationSummaryMetrics
from app.application.notifications.summary import SendNotificationSummary
from app.application.notifications.summary import latest_completed_summary_period
from app.domain.notifications import NotificationSettings, NotificationSummarySettings
from app.domain.notifications import TelegramBot, TelegramChat, TelegramSendResult


class InMemoryNotificationSettingsRepository:
    def __init__(self, settings: NotificationSettings) -> None:
        self.settings = settings

    async def get_settings(self) -> NotificationSettings:
        return self.settings

    async def save_settings(self, settings: NotificationSettings) -> NotificationSettings:
        self.settings = settings
        return settings


class InMemorySummaryRepository:
    def __init__(self, metrics: NotificationSummaryMetrics) -> None:
        self.metrics = metrics
        self.claimed: set[tuple[str, datetime, datetime, str, str]] = set()
        self.sent: list[tuple[str, datetime, datetime, int]] = []
        self.failed: list[tuple[str, datetime, datetime, str]] = []

    async def claim_run(
        self,
        *,
        period_kind: str,
        period_start: datetime,
        period_end: datetime,
        bot_id: str,
        chat_id: str,
        now: datetime,
    ) -> bool:
        key = (period_kind, period_start, period_end, bot_id, chat_id)
        if key in self.claimed:
            return False
        self.claimed.add(key)
        return True

    async def collect_metrics(self, *, period_start: datetime, period_end: datetime) -> NotificationSummaryMetrics:
        return self.metrics

    async def mark_run_sent(
        self,
        *,
        period_kind: str,
        period_start: datetime,
        period_end: datetime,
        bot_id: str,
        chat_id: str,
        telegram_message_id: int,
        sent_at: datetime,
    ) -> None:
        self.sent.append((period_kind, period_start, period_end, telegram_message_id))

    async def mark_run_failed(
        self,
        *,
        period_kind: str,
        period_start: datetime,
        period_end: datetime,
        bot_id: str,
        chat_id: str,
        error: str,
        failed_at: datetime,
    ) -> None:
        self.failed.append((period_kind, period_start, period_end, error))


class RecordingTelegramMessageSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str, dict[str, Any] | None]] = []

    async def get_bot_username(self, *, bot_token: str) -> str:
        return "pur_bot"

    async def send_text(
        self,
        *,
        bot_token: str,
        chat_id: str,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> TelegramSendResult:
        self.sent.append((bot_token, chat_id, text, reply_markup))
        return TelegramSendResult(message_id=9001, chat_id=chat_id)


def test_latest_completed_summary_period_returns_moscow_day_window() -> None:
    period = latest_completed_summary_period(
        now=datetime(2026, 5, 15, 18, 5, tzinfo=UTC),
        timezone_name="Europe/Moscow",
        day_start_hour=9,
        night_start_hour=21,
    )

    assert period.kind == "day"
    assert period.start_at == datetime(2026, 5, 15, 6, 0, tzinfo=UTC)
    assert period.end_at == datetime(2026, 5, 15, 18, 0, tzinfo=UTC)


def test_latest_completed_summary_period_returns_moscow_night_window() -> None:
    period = latest_completed_summary_period(
        now=datetime(2026, 5, 15, 6, 5, tzinfo=UTC),
        timezone_name="Europe/Moscow",
        day_start_hour=9,
        night_start_hour=21,
    )

    assert period.kind == "night"
    assert period.start_at == datetime(2026, 5, 14, 18, 0, tzinfo=UTC)
    assert period.end_at == datetime(2026, 5, 15, 6, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_send_notification_summary_sends_once_for_period() -> None:
    now = datetime(2026, 5, 15, 18, 5, tzinfo=UTC)
    sender = RecordingTelegramMessageSender()
    repository = InMemorySummaryRepository(_metrics())
    use_case = SendNotificationSummary(
        settings_repository=InMemoryNotificationSettingsRepository(_settings()),
        summary_repository=repository,
        sender=sender,
    )

    first = await use_case.execute(now=now)
    second = await use_case.execute(now=now)

    assert first is not None
    assert second is None
    assert len(sender.sent) == 1
    assert sender.sent[0][0] == "token-secret"
    assert sender.sent[0][1] == "-100summary"
    assert "Сводка PUR Leads за день" in sender.sent[0][2]
    assert "Источники: 67 включено, 57 активных" in sender.sent[0][2]
    assert "Сообщения: 120 получено, 118 обработано, 2 ждут, 0 ошибок" in sender.sent[0][2]
    assert "Лиды: холодные 3, теплые 2, горячие 1" in sender.sent[0][2]
    assert "Очереди: в норме" in sender.sent[0][2]
    assert repository.sent == [
        (
            "day",
            datetime(2026, 5, 15, 6, 0, tzinfo=UTC),
            datetime(2026, 5, 15, 18, 0, tzinfo=UTC),
            9001,
        )
    ]


def _settings() -> NotificationSettings:
    return NotificationSettings(
        bots=[TelegramBot(id="main_bot", name="Main", enabled=True, token="token-secret")],
        chats=[
            TelegramChat(
                id="summary_chat",
                name="Сводки",
                enabled=True,
                telegram_chat_id="-100summary",
            )
        ],
        routes=[],
        updated_at=None,
        summary=NotificationSummarySettings(
            enabled=True,
            bot_id="main_bot",
            chat_id="summary_chat",
            timezone="Europe/Moscow",
            day_start_hour=9,
            night_start_hour=21,
        ),
    )


def _metrics() -> NotificationSummaryMetrics:
    return NotificationSummaryMetrics(
        source_chats_enabled=67,
        source_chats_by_status={"resolved": 57, "missing": 6, "pending": 2, "private": 2},
        messages_received=120,
        messages_processed=118,
        messages_waiting=2,
        messages_failed=0,
        leads_by_temperature={"cold": 3, "warm": 2, "hot": 1},
        enrichment_jobs_by_status={"completed": 118, "queued": 2},
        llm_runs_by_status={"queued": 0, "running": 0, "failed": 0},
        notification_outbox_by_status={"pending": 0, "sending": 0, "failed": 0},
        redis_queues={"celery": 0, "llm": 0},
    )
