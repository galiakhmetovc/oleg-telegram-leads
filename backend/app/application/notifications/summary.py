from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal, Protocol
from zoneinfo import ZoneInfo

from app.application.notifications.ports import NotificationSettingsRepository
from app.application.notifications.ports import TelegramMessageSender
from app.domain.notifications import TelegramSendResult

NotificationSummaryKind = Literal["day", "night"]


@dataclass(frozen=True)
class NotificationSummaryPeriod:
    kind: NotificationSummaryKind
    start_at: datetime
    end_at: datetime
    timezone: str


@dataclass(frozen=True)
class NotificationSummaryMetrics:
    source_chats_enabled: int
    source_chats_by_status: dict[str, int]
    messages_received: int
    messages_processed: int
    messages_waiting: int
    messages_failed: int
    leads_by_temperature: dict[str, int]
    enrichment_jobs_by_status: dict[str, int]
    llm_runs_by_status: dict[str, int]
    notification_outbox_by_status: dict[str, int]
    redis_queues: dict[str, int | None]


class NotificationSummaryRepository(Protocol):
    async def claim_run(
        self,
        *,
        period_kind: str,
        period_start: datetime,
        period_end: datetime,
        bot_id: str,
        chat_id: str,
        now: datetime,
    ) -> bool: ...

    async def collect_metrics(
        self,
        *,
        period_start: datetime,
        period_end: datetime,
    ) -> NotificationSummaryMetrics: ...

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
    ) -> None: ...

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
    ) -> None: ...


class SendNotificationSummary:
    def __init__(
        self,
        *,
        settings_repository: NotificationSettingsRepository,
        summary_repository: NotificationSummaryRepository,
        sender: TelegramMessageSender,
    ) -> None:
        self._settings_repository = settings_repository
        self._summary_repository = summary_repository
        self._sender = sender

    async def execute(self, *, now: datetime | None = None) -> TelegramSendResult | None:
        current_time = now or datetime.now(UTC)
        settings = await self._settings_repository.get_settings()
        summary_settings = settings.summary
        if summary_settings is None or not summary_settings.enabled:
            return None

        bot = next(
            (
                item
                for item in settings.bots
                if item.id == summary_settings.bot_id and item.enabled and item.token
            ),
            None,
        )
        chat = next(
            (
                item
                for item in settings.chats
                if item.id == summary_settings.chat_id and item.enabled and item.telegram_chat_id.strip()
            ),
            None,
        )
        if bot is None or chat is None:
            return None

        period = latest_completed_summary_period(
            now=current_time,
            timezone_name=summary_settings.timezone,
            day_start_hour=summary_settings.day_start_hour,
            night_start_hour=summary_settings.night_start_hour,
        )
        claimed = await self._summary_repository.claim_run(
            period_kind=period.kind,
            period_start=period.start_at,
            period_end=period.end_at,
            bot_id=bot.id,
            chat_id=chat.id,
            now=current_time,
        )
        if not claimed:
            return None

        try:
            metrics = await self._summary_repository.collect_metrics(
                period_start=period.start_at,
                period_end=period.end_at,
            )
            result = await self._sender.send_text(
                bot_token=bot.token or "",
                chat_id=chat.telegram_chat_id,
                text=render_notification_summary_message(period, metrics),
            )
        except Exception as exc:
            await self._summary_repository.mark_run_failed(
                period_kind=period.kind,
                period_start=period.start_at,
                period_end=period.end_at,
                bot_id=bot.id,
                chat_id=chat.id,
                error=str(exc) or type(exc).__name__,
                failed_at=current_time,
            )
            raise

        await self._summary_repository.mark_run_sent(
            period_kind=period.kind,
            period_start=period.start_at,
            period_end=period.end_at,
            bot_id=bot.id,
            chat_id=chat.id,
            telegram_message_id=result.message_id,
            sent_at=current_time,
        )
        return result


def latest_completed_summary_period(
    *,
    now: datetime,
    timezone_name: str,
    day_start_hour: int,
    night_start_hour: int,
) -> NotificationSummaryPeriod:
    zone = ZoneInfo(timezone_name)
    local_now = _ensure_aware(now).astimezone(zone)
    local_date = local_now.date()
    if local_now.hour >= night_start_hour:
        kind: NotificationSummaryKind = "day"
        start = _local_boundary(local_date, day_start_hour, zone)
        end = _local_boundary(local_date, night_start_hour, zone)
    elif local_now.hour >= day_start_hour:
        kind = "night"
        start = _local_boundary(local_date - timedelta(days=1), night_start_hour, zone)
        end = _local_boundary(local_date, day_start_hour, zone)
    else:
        kind = "day"
        previous = local_date - timedelta(days=1)
        start = _local_boundary(previous, day_start_hour, zone)
        end = _local_boundary(previous, night_start_hour, zone)
    return NotificationSummaryPeriod(
        kind=kind,
        start_at=start.astimezone(UTC),
        end_at=end.astimezone(UTC),
        timezone=timezone_name,
    )


def render_notification_summary_message(
    period: NotificationSummaryPeriod,
    metrics: NotificationSummaryMetrics,
) -> str:
    label = "день" if period.kind == "day" else "ночь"
    active_sources = _active_source_count(metrics.source_chats_by_status)
    cold = metrics.leads_by_temperature.get("cold", 0)
    warm = metrics.leads_by_temperature.get("warm", 0)
    hot = metrics.leads_by_temperature.get("hot", 0)
    return "\n".join(
        [
            f"Сводка PUR Leads за {label}",
            f"Период: {_format_period_window(period)}",
            "",
            f"Источники: {metrics.source_chats_enabled} включено, {active_sources} активных",
            f"Статусы источников: {_format_counts(metrics.source_chats_by_status)}",
            (
                "Сообщения: "
                f"{metrics.messages_received} получено, "
                f"{metrics.messages_processed} обработано, "
                f"{metrics.messages_waiting} ждут, "
                f"{metrics.messages_failed} ошибок"
            ),
            f"Лиды: холодные {cold}, теплые {warm}, горячие {hot}",
            f"Очереди: {_queue_status(metrics)}",
            f"Enrichment: {_format_counts(metrics.enrichment_jobs_by_status)}",
            f"LLM: {_format_counts(metrics.llm_runs_by_status)}",
            f"Outbox: {_format_counts(metrics.notification_outbox_by_status)}",
            f"Redis: {_format_redis_queues(metrics.redis_queues)}",
        ]
    )


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _local_boundary(local_date: date, hour: int, zone: ZoneInfo) -> datetime:
    return datetime.combine(local_date, time(hour=hour), tzinfo=zone)


def _format_period_window(period: NotificationSummaryPeriod) -> str:
    zone = ZoneInfo(period.timezone)
    start = period.start_at.astimezone(zone)
    end = period.end_at.astimezone(zone)
    return f"{start:%d.%m %H:%M} - {end:%d.%m %H:%M} {period.timezone}"


def _active_source_count(counts: dict[str, int]) -> int:
    return counts.get("resolved", 0) + counts.get("active", 0)


def _format_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "нет данных"
    return ", ".join(f"{key} {value}" for key, value in sorted(counts.items()))


def _format_redis_queues(queues: dict[str, int | None]) -> str:
    if not queues:
        return "нет данных"
    return ", ".join(
        f"{name} {value if value is not None else 'unknown'}"
        for name, value in sorted(queues.items())
    )


def _queue_status(metrics: NotificationSummaryMetrics) -> str:
    failed_counts = [
        metrics.messages_failed,
        metrics.enrichment_jobs_by_status.get("failed", 0),
        metrics.llm_runs_by_status.get("failed", 0),
        metrics.notification_outbox_by_status.get("failed", 0),
    ]
    if any(count > 0 for count in failed_counts):
        return "есть ошибки"
    if any(depth is None for depth in metrics.redis_queues.values()):
        return "нет данных по Redis"
    return "в норме"
