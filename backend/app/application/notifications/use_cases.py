from __future__ import annotations

import logging
import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.application.notifications.batching import TELEGRAM_SEND_MESSAGE_CHAR_LIMIT
from app.application.notifications.batching import pack_notification_batches
from app.application.notifications.ports import NotificationOutboxRepository
from app.application.notifications.ports import NotificationSettingsRepository, TelegramMessageSender
from app.application.notifications.routing import match_notification_routes
from app.application.notifications.routing import NotificationMessageContext
from app.application.notifications.routing import render_notification_message
from app.domain.enrichment import TextEnrichmentResult
from app.domain.llm_verification import LlmVerificationRun, SourceMessageForLlmVerification
from app.domain.notifications import NotificationOutboxItem
from app.domain.notifications import NotificationSettings, NotificationSummarySettings
from app.domain.notifications import TelegramBot, TelegramChat
from app.domain.notifications import TelegramSendResult

LLM_LEAD_SOURCE_ROUTE_TEMPERATURES = {
    "cold_leads": "cold",
    "warm_leads": "warm",
}
LLM_LEAD_NOTIFICATION_ROUTE_IDS = {
    "cold_leads": "llm_cold_leads",
    "warm_leads": "llm_warm_leads",
}
LLM_LEAD_TEMPERATURE_LABELS = {
    "cold": "холодный",
    "warm": "теплый",
}
LLM_LEAD_CONFIDENCE_MIN = 0.5
LLM_LEAD_RECOMMENDATIONS = {"keep", "promote", "manual_review"}
DEFAULT_TELEGRAM_TEST_MESSAGE = "Проверка уведомлений PUR Leads v2"
OLD_DEFAULT_ROUTE_MESSAGE_TEMPLATE = (
    "Найден лид ПУР\n"
    "Score: {score}\n"
    "Температура: {temperature}\n"
    "Очередь: {review_lane}\n"
    "Текст: {text}"
)
DEFAULT_ROUTE_MESSAGE_TEMPLATE = (
    "Лид ПУР\n\n"
    "Оценка: {score} ({temperature})\n"
    "Очередь: {review_lane_label}\n"
    "Зоны решения: {solution_areas}\n"
    "Сегменты: {customer_segments}\n\n"
    "Почему сработало:\n"
    "{reasons_detailed}\n\n"
    "Текст:\n"
    "{text_preview}"
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TelegramBotTestResult:
    username: str


class UpdateNotificationSettings:
    def __init__(self, repository: NotificationSettingsRepository) -> None:
        self._repository = repository

    async def execute(self, settings: NotificationSettings) -> NotificationSettings:
        current = await self._repository.get_settings()
        bots_by_id = {bot.id: bot for bot in current.bots}
        normalized = NotificationSettings(
            bots=[
                TelegramBot(
                    id=_required_str(bot.id, "Bot id is required"),
                    name=_required_str(bot.name, "Bot name is required"),
                    enabled=bot.enabled,
                    token=_optional_str(bot.token) or bots_by_id.get(bot.id, bot).token,
                )
                for bot in settings.bots
            ],
            chats=[
                TelegramChat(
                    id=_required_str(chat.id, "Chat id is required"),
                    name=_required_str(chat.name, "Chat name is required"),
                    enabled=chat.enabled,
                    telegram_chat_id=_required_str(
                        chat.telegram_chat_id,
                        "Telegram chat id is required",
                    ),
                )
                for chat in settings.chats
            ],
            routes=settings.routes,
            updated_at=None,
            summary=_normalize_summary(settings.summary)
            if settings.summary is not None
            else current.summary,
        )
        _validate_unique([bot.id for bot in normalized.bots], "Bot ids must be unique")
        _validate_unique([chat.id for chat in normalized.chats], "Chat ids must be unique")
        _validate_unique([route.id for route in normalized.routes], "Route ids must be unique")
        bot_ids = {bot.id for bot in normalized.bots}
        chat_ids = {chat.id for chat in normalized.chats}
        for bot in normalized.bots:
            if bot.enabled and not bot.token:
                raise ValueError(f"Telegram bot token is required for enabled bot {bot.id}")
        for route in normalized.routes:
            _required_str(route.name, "Route name is required")
            if route.match_mode not in {"all", "any"}:
                raise ValueError("Route match_mode must be all or any")
            if route.bot_id not in bot_ids:
                raise ValueError(f"Route {route.id} references unknown bot {route.bot_id}")
            if route.chat_id not in chat_ids:
                raise ValueError(f"Route {route.id} references unknown chat {route.chat_id}")
        if normalized.summary is not None:
            if normalized.summary.bot_id not in bot_ids:
                raise ValueError(f"Summary references unknown bot {normalized.summary.bot_id}")
            if normalized.summary.chat_id not in chat_ids:
                raise ValueError(f"Summary references unknown chat {normalized.summary.chat_id}")
            if normalized.summary.day_start_hour == normalized.summary.night_start_hour:
                raise ValueError("Summary day_start_hour and night_start_hour must differ")
        return await self._repository.save_settings(normalized)


class TestTelegramBot:
    def __init__(
        self,
        repository: NotificationSettingsRepository,
        sender: TelegramMessageSender,
    ) -> None:
        self._repository = repository
        self._sender = sender

    async def execute(self, bot_id: str) -> TelegramBotTestResult:
        settings = await self._repository.get_settings()
        bot = _find_enabled_bot(settings, bot_id)
        username = await self._sender.get_bot_username(bot_token=bot.token or "")
        return TelegramBotTestResult(username=username)


class SendTelegramChatTestNotification:
    def __init__(
        self,
        repository: NotificationSettingsRepository,
        sender: TelegramMessageSender,
    ) -> None:
        self._repository = repository
        self._sender = sender

    async def execute(self, *, bot_id: str, chat_id: str, message: str | None) -> TelegramSendResult:
        settings = await self._repository.get_settings()
        bot = _find_enabled_bot(settings, bot_id)
        chat = _find_enabled_chat(settings, chat_id)
        text = _optional_str(message) or DEFAULT_TELEGRAM_TEST_MESSAGE
        return await self._sender.send_text(
            bot_token=bot.token or "",
            chat_id=chat.telegram_chat_id,
            text=text,
        )


class QueueNotificationsForEnrichment:
    def __init__(
        self,
        *,
        settings_repository: NotificationSettingsRepository,
        outbox_repository: NotificationOutboxRepository,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._settings_repository = settings_repository
        self._outbox_repository = outbox_repository
        self._now = now or (lambda: datetime.now(UTC))

    async def execute(
        self,
        result: TextEnrichmentResult,
        context: NotificationMessageContext | None = None,
    ) -> list[NotificationOutboxItem]:
        settings = await self._settings_repository.get_settings()
        bots = {bot.id: bot for bot in settings.bots if bot.enabled and bot.token}
        chats = {chat.id: chat for chat in settings.chats if chat.enabled}
        created_at = self._now()
        items: list[NotificationOutboxItem] = []
        for route in match_notification_routes(settings.routes, result):
            if route.bot_id not in bots or route.chat_id not in chats:
                continue
            template = _route_message_template(route.message_template)
            items.append(
                NotificationOutboxItem(
                    id=uuid4(),
                    route_id=route.id,
                    bot_id=route.bot_id,
                    chat_id=route.chat_id,
                    source_message_id=context.source_message_id if context else None,
                    enrichment_job_id=context.enrichment_job_id if context else None,
                    text=render_notification_message(template, result, context),
                    status="pending",
                    attempts=0,
                    last_error=None,
                    created_at=created_at,
                    sent_at=None,
                )
            )
        if not items:
            return []
        return await self._outbox_repository.enqueue(items)


class QueueLlmLeadNotification:
    def __init__(
        self,
        *,
        settings_repository: NotificationSettingsRepository,
        outbox_repository: NotificationOutboxRepository,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._settings_repository = settings_repository
        self._outbox_repository = outbox_repository
        self._now = now or (lambda: datetime.now(UTC))

    async def execute(
        self,
        *,
        run: LlmVerificationRun,
        source: SourceMessageForLlmVerification,
        context: NotificationMessageContext | None,
    ) -> list[NotificationOutboxItem]:
        if not _should_notify_llm_lead(run, source):
            return []
        settings = await self._settings_repository.get_settings()
        target = _llm_notification_target(settings)
        if target is None:
            return []
        if run.route_id is None:
            return []
        notification_route_id = _llm_notification_route_id(run.route_id)
        if notification_route_id is None:
            return []
        bot_id, chat_id = target
        return await self._outbox_repository.enqueue(
            [
                NotificationOutboxItem(
                    id=uuid4(),
                    route_id=notification_route_id,
                    bot_id=bot_id,
                    chat_id=chat_id,
                    source_message_id=source.source_message_id,
                    enrichment_job_id=source.enrichment_job_id,
                    text=_render_llm_lead_notification(run, source, context),
                    status="pending",
                    attempts=0,
                    last_error=None,
                    created_at=self._now(),
                    sent_at=None,
                )
            ]
        )


class FlushNotificationOutbox:
    def __init__(
        self,
        *,
        settings_repository: NotificationSettingsRepository,
        outbox_repository: NotificationOutboxRepository,
        sender: TelegramMessageSender,
        max_message_chars: int = TELEGRAM_SEND_MESSAGE_CHAR_LIMIT,
        flush_interval: timedelta = timedelta(minutes=5),
        min_chat_send_interval_seconds: float = 3.1,
        pending_limit: int = 500,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._settings_repository = settings_repository
        self._outbox_repository = outbox_repository
        self._sender = sender
        self._max_message_chars = max_message_chars
        self._flush_interval = flush_interval
        self._min_chat_send_interval_seconds = min_chat_send_interval_seconds
        self._pending_limit = pending_limit
        self._sleep = sleep

    async def execute(self, *, now: datetime | None = None) -> list[TelegramSendResult]:
        current_time = now or datetime.now(UTC)
        pending = await self._outbox_repository.list_pending(limit=self._pending_limit)
        if not pending:
            return []

        settings = await self._settings_repository.get_settings()
        bots = {bot.id: bot for bot in settings.bots if bot.enabled and bot.token}
        chats = {chat.id: chat for chat in settings.chats if chat.enabled}
        routes = {route.id: route for route in settings.routes}
        sent: list[TelegramSendResult] = []
        sent_once_by_chat: set[str] = set()
        handled_item_ids: set[UUID] = set()
        batched_pending: list[NotificationOutboxItem] = []

        for item in pending:
            route = routes.get(item.route_id)
            if route is None or route.delivery_mode != "interactive":
                batched_pending.append(item)
                continue
            bot = bots.get(item.bot_id)
            chat = chats.get(item.chat_id)
            if bot is None or chat is None:
                await self._outbox_repository.mark_failed(
                    [item.id],
                    error="Telegram bot or chat is not configured",
                )
                handled_item_ids.add(item.id)
                continue
            if item.source_message_id is None:
                await self._outbox_repository.mark_failed(
                    [item.id],
                    error="Interactive notification requires source_message_id",
                )
                handled_item_ids.add(item.id)
                continue
            if chat.id in sent_once_by_chat and self._min_chat_send_interval_seconds > 0:
                await self._sleep(self._min_chat_send_interval_seconds)
            try:
                sent.append(
                    await self._sender.send_text(
                        bot_token=bot.token or "",
                        chat_id=chat.telegram_chat_id,
                        text=item.text,
                        reply_markup=_lead_action_keyboard(item.source_message_id),
                    )
                )
            except Exception as exc:
                await self._outbox_repository.mark_failed(
                    [item.id],
                    error=str(exc) or type(exc).__name__,
                )
                handled_item_ids.add(item.id)
                logger.exception("Failed to flush interactive notification")
                continue
            await self._outbox_repository.mark_sent([item.id], sent_at=current_time)
            handled_item_ids.add(item.id)
            sent_once_by_chat.add(chat.id)

        for group in _group_pending_items(batched_pending):
            due = current_time - min(item.created_at for item in group) >= self._flush_interval
            batches = pack_notification_batches(
                group,
                max_message_chars=self._max_message_chars,
            )
            ready_batches = batches if due else [batch for batch in batches if batch.is_full]
            for batch in ready_batches:
                bot = bots.get(batch.bot_id)
                chat = chats.get(batch.chat_id)
                if bot is None or chat is None:
                    await self._outbox_repository.mark_failed(
                        batch.item_ids,
                        error="Telegram bot or chat is not configured",
                    )
                    handled_item_ids.update(batch.item_ids)
                    continue
                if chat.id in sent_once_by_chat and self._min_chat_send_interval_seconds > 0:
                    await self._sleep(self._min_chat_send_interval_seconds)
                try:
                    sent.append(
                        await self._sender.send_text(
                            bot_token=bot.token or "",
                            chat_id=chat.telegram_chat_id,
                            text=batch.text,
                        )
                    )
                except Exception as exc:
                    await self._outbox_repository.mark_failed(
                        batch.item_ids,
                        error=str(exc) or type(exc).__name__,
                    )
                    handled_item_ids.update(batch.item_ids)
                    logger.exception("Failed to flush notification batch")
                    continue
                await self._outbox_repository.mark_sent(batch.item_ids, sent_at=current_time)
                handled_item_ids.update(batch.item_ids)
                sent_once_by_chat.add(chat.id)
        unhandled_ids = [item.id for item in pending if item.id not in handled_item_ids]
        if unhandled_ids:
            await self._outbox_repository.release_pending(unhandled_ids)
        return sent


class DispatchNotificationsForEnrichment:
    def __init__(
        self,
        repository: NotificationSettingsRepository,
        sender: TelegramMessageSender,
    ) -> None:
        self._repository = repository
        self._sender = sender

    async def execute(self, result: TextEnrichmentResult) -> list[TelegramSendResult]:
        settings = await self._repository.get_settings()
        bots = {bot.id: bot for bot in settings.bots if bot.enabled and bot.token}
        chats = {chat.id: chat for chat in settings.chats if chat.enabled}
        sent: list[TelegramSendResult] = []
        for route in match_notification_routes(settings.routes, result):
            bot = bots.get(route.bot_id)
            chat = chats.get(route.chat_id)
            if bot is None or chat is None:
                continue
            template = _route_message_template(route.message_template)
            message = render_notification_message(template, result)
            try:
                sent.append(
                    await self._sender.send_text(
                        bot_token=bot.token or "",
                        chat_id=chat.telegram_chat_id,
                        text=message,
                    )
                )
            except Exception:
                logger.exception("Failed to dispatch notification route %s", route.id)
        return sent


def _group_pending_items(
    items: list[NotificationOutboxItem],
) -> list[list[NotificationOutboxItem]]:
    groups: dict[tuple[str, str], list[NotificationOutboxItem]] = {}
    for item in items:
        groups.setdefault((item.bot_id, item.chat_id), []).append(item)
    return list(groups.values())


def _normalize_summary(
    summary: NotificationSummarySettings | None,
) -> NotificationSummarySettings | None:
    if summary is None:
        return None
    if not 0 <= summary.day_start_hour <= 23:
        raise ValueError("Summary day_start_hour must be between 0 and 23")
    if not 0 <= summary.night_start_hour <= 23:
        raise ValueError("Summary night_start_hour must be between 0 and 23")
    timezone = _required_str(summary.timezone, "Summary timezone is required")
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Summary timezone is invalid") from exc
    return NotificationSummarySettings(
        enabled=summary.enabled,
        bot_id=_required_str(summary.bot_id, "Summary bot id is required"),
        chat_id=_required_str(summary.chat_id, "Summary chat id is required"),
        timezone=timezone,
        day_start_hour=summary.day_start_hour,
        night_start_hour=summary.night_start_hour,
    )


def _lead_action_keyboard(source_message_id: UUID) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "Взял", "callback_data": f"lh:claim:{source_message_id}"},
                {"text": "Не лид", "callback_data": f"lh:notlead:{source_message_id}"},
            ]
        ]
    }


def _should_notify_llm_lead(
    run: LlmVerificationRun,
    source: SourceMessageForLlmVerification,
) -> bool:
    if run.route_id is None:
        return False
    expected_temperature = LLM_LEAD_SOURCE_ROUTE_TEMPERATURES.get(run.route_id)
    if run.status != "completed" or expected_temperature is None:
        return False
    if not isinstance(run.response, dict):
        return False
    assessment = source.enrichment_result.lead_assessment
    if assessment is None or not assessment.is_lead or assessment.temperature != expected_temperature:
        return False
    verdict = str(run.response.get("verdict") or "")
    recommendation = str(run.response.get("recommendation") or "")
    confidence = _confidence_value(run.response.get("confidence"))
    return (
        verdict == "lead"
        and recommendation in LLM_LEAD_RECOMMENDATIONS
        and confidence is not None
        and confidence >= LLM_LEAD_CONFIDENCE_MIN
    )


def _llm_notification_route_id(source_route_id: str) -> str | None:
    return LLM_LEAD_NOTIFICATION_ROUTE_IDS.get(source_route_id)


def _llm_notification_target(settings: NotificationSettings) -> tuple[str, str] | None:
    bot_ids = {bot.id for bot in settings.bots if bot.enabled and bot.token}
    chat_ids = {chat.id for chat in settings.chats if chat.enabled and chat.telegram_chat_id.strip()}
    for route in sorted(settings.routes, key=lambda item: item.priority, reverse=True):
        if route.enabled and route.bot_id in bot_ids and route.chat_id in chat_ids:
            return route.bot_id, route.chat_id
    if bot_ids and chat_ids:
        return sorted(bot_ids)[0], sorted(chat_ids)[0]
    return None


def _render_llm_lead_notification(
    run: LlmVerificationRun,
    source: SourceMessageForLlmVerification,
    context: NotificationMessageContext | None,
) -> str:
    assessment = source.enrichment_result.lead_assessment
    response = run.response or {}
    review_lane = assessment.review_lane if assessment else None
    temperature = assessment.temperature if assessment else "none"
    temperature_label = LLM_LEAD_TEMPERATURE_LABELS.get(temperature, "лид")
    lead_phrase = f"{temperature_label} лид" if temperature_label != "лид" else "лид"
    lines = [
        f"LLM подтвердил {lead_phrase}",
        "",
        f"LLM: {response.get('verdict')} / {response.get('recommendation')} / confidence {_format_confidence(response.get('confidence'))}",
        f"Оценка: {assessment.score if assessment else 0} ({temperature})",
        f"Очередь: {review_lane.label if review_lane else 'не указано'}",
    ]
    evidence = _llm_response_list(response.get("evidence"))
    if evidence:
        lines.extend(["", "Evidence:", *[f"- {_truncate_plain_text(item, max_length=220)}" for item in evidence[:5]]])
    anti_evidence = _llm_response_list(response.get("anti_evidence"))
    if anti_evidence:
        lines.extend(["", "Anti-evidence:", *[f"- {_truncate_plain_text(item, max_length=220)}" for item in anti_evidence[:5]]])
    lines.extend(["", "Текст:", _truncate_plain_text(source.text, max_length=1200)])
    links = _context_link_lines(context)
    if links:
        lines.extend(["", "Ссылки:", *links])
    return "\n".join(lines)


def _format_confidence(value: object) -> str:
    confidence = _confidence_value(value)
    if confidence is not None:
        return f"{confidence:.2f}".rstrip("0").rstrip(".")
    return str(value or "не указано")


def _confidence_value(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _llm_response_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _truncate_plain_text(text: str, *, max_length: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 1].rstrip() + "..."


def _context_link_lines(context: NotificationMessageContext | None) -> list[str]:
    if context is None:
        return []
    lines: list[str] = []
    if context.telegram_message_url:
        lines.append(f"Telegram: {context.telegram_message_url}")
    if context.app_message_url:
        lines.append(f"Аналитика: {context.app_message_url}")
    return lines


def _find_enabled_bot(settings: NotificationSettings, bot_id: str) -> TelegramBot:
    bot = next((item for item in settings.bots if item.id == bot_id), None)
    if bot is None or not bot.enabled or not bot.token:
        raise ValueError("Telegram bot is not configured")
    return bot


def _find_enabled_chat(settings: NotificationSettings, chat_id: str) -> TelegramChat:
    chat = next((item for item in settings.chats if item.id == chat_id), None)
    if chat is None or not chat.enabled or not chat.telegram_chat_id.strip():
        raise ValueError("Telegram chat is not configured")
    return chat


def _optional_str(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _route_message_template(value: str | None) -> str:
    template = _optional_str(value)
    if template is None or template == OLD_DEFAULT_ROUTE_MESSAGE_TEMPLATE:
        return DEFAULT_ROUTE_MESSAGE_TEMPLATE
    return template


def _required_str(value: str, message: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(message)
    return stripped


def _validate_unique(values: list[str], message: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(message)
