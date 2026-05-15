from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.application.notifications.use_cases import FlushNotificationOutbox
from app.domain.notifications import NotificationOutboxItem, NotificationRoute
from app.domain.notifications import NotificationRouteConditions, NotificationSettings
from app.domain.notifications import TelegramBot, TelegramChat, TelegramSendResult


class InMemoryNotificationSettingsRepository:
    def __init__(self, settings: NotificationSettings) -> None:
        self.settings = settings

    async def get_settings(self) -> NotificationSettings:
        return self.settings

    async def save_settings(self, settings: NotificationSettings) -> NotificationSettings:
        self.settings = settings
        return settings


class InMemoryNotificationOutboxRepository:
    def __init__(self, items: list[NotificationOutboxItem]) -> None:
        self.items = items
        self.sent_ids: list[UUID] = []
        self.failed_ids: list[UUID] = []
        self.released_ids: list[UUID] = []
        self.failed_errors: list[str] = []

    async def enqueue(self, items: list[NotificationOutboxItem]) -> list[NotificationOutboxItem]:
        self.items.extend(items)
        return items

    async def list_pending(self, *, limit: int) -> list[NotificationOutboxItem]:
        return [item for item in self.items if item.status == "pending"][:limit]

    async def mark_sent(self, ids: list[UUID], *, sent_at: datetime) -> None:
        self.sent_ids.extend(ids)
        sent_id_set = set(ids)
        self.items = [
            item.mark_sent(sent_at) if item.id in sent_id_set else item
            for item in self.items
        ]

    async def mark_failed(self, ids: list[UUID], *, error: str) -> None:
        self.failed_ids.extend(ids)
        self.failed_errors.append(error)
        failed_id_set = set(ids)
        self.items = [
            item.mark_failed(error) if item.id in failed_id_set else item
            for item in self.items
        ]

    async def release_pending(self, ids: list[UUID]) -> None:
        self.released_ids.extend(ids)


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
        return TelegramSendResult(message_id=len(self.sent), chat_id=chat_id)


@pytest.mark.asyncio
async def test_flush_interactive_notification_sends_inline_buttons() -> None:
    now = datetime(2026, 5, 15, 10, 0, tzinfo=UTC)
    source_message_id = uuid4()
    item = _outbox_item(now=now, source_message_id=source_message_id)
    outbox = InMemoryNotificationOutboxRepository([item])
    sender = RecordingTelegramMessageSender()

    sent = await FlushNotificationOutbox(
        settings_repository=InMemoryNotificationSettingsRepository(_notification_settings()),
        outbox_repository=outbox,
        sender=sender,
        flush_interval=timedelta(minutes=5),
        min_chat_send_interval_seconds=0,
    ).execute(now=now)

    assert len(sent) == 1
    assert outbox.sent_ids == [item.id]
    assert outbox.released_ids == []
    assert sender.sent == [
        (
            "token-secret",
            "-100sales",
            "Лид ПУР\n\nТекст: нужен умный дом",
            {
                "inline_keyboard": [
                    [
                        {"text": "Взял", "callback_data": f"lh:claim:{source_message_id}"},
                        {"text": "Не лид", "callback_data": f"lh:notlead:{source_message_id}"},
                    ]
                ]
            },
        )
    ]


@pytest.mark.asyncio
async def test_interactive_route_requires_source_message_id() -> None:
    now = datetime(2026, 5, 15, 10, 0, tzinfo=UTC)
    item = _outbox_item(now=now, source_message_id=None)
    outbox = InMemoryNotificationOutboxRepository([item])
    sender = RecordingTelegramMessageSender()

    sent = await FlushNotificationOutbox(
        settings_repository=InMemoryNotificationSettingsRepository(_notification_settings()),
        outbox_repository=outbox,
        sender=sender,
        flush_interval=timedelta(minutes=5),
        min_chat_send_interval_seconds=0,
    ).execute(now=now)

    assert sent == []
    assert sender.sent == []
    assert outbox.failed_ids == [item.id]
    assert outbox.failed_errors == ["Interactive notification requires source_message_id"]
    assert outbox.released_ids == []


def _notification_settings() -> NotificationSettings:
    return NotificationSettings(
        bots=[TelegramBot(id="main_bot", name="Main", enabled=True, token="token-secret")],
        chats=[
            TelegramChat(
                id="sales_chat",
                name="Sales",
                enabled=True,
                telegram_chat_id="-100sales",
            )
        ],
        routes=[
            NotificationRoute(
                id="hot",
                name="Горячие лиды",
                enabled=True,
                priority=100,
                bot_id="main_bot",
                chat_id="sales_chat",
                match_mode="all",
                delivery_mode="interactive",
                conditions=NotificationRouteConditions(is_lead=True, score_min=80),
                message_template="",
            )
        ],
        updated_at=None,
    )


def _outbox_item(
    *,
    now: datetime,
    source_message_id: UUID | None,
) -> NotificationOutboxItem:
    return NotificationOutboxItem(
        id=uuid4(),
        route_id="hot",
        bot_id="main_bot",
        chat_id="sales_chat",
        source_message_id=source_message_id,
        enrichment_job_id=uuid4(),
        text="Лид ПУР\n\nТекст: нужен умный дом",
        status="pending",
        attempts=0,
        last_error=None,
        created_at=now,
        sent_at=None,
    )
