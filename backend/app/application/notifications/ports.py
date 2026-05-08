from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.notifications import NotificationOutboxItem, NotificationSettings, TelegramSendResult


class NotificationSettingsRepository(Protocol):
    async def get_settings(self) -> NotificationSettings:
        """Return notification bots, chats, and routes."""
        ...

    async def save_settings(
        self,
        settings: NotificationSettings,
    ) -> NotificationSettings:
        """Persist notification bots, chats, and routes."""
        ...


class TelegramMessageSender(Protocol):
    async def get_bot_username(self, *, bot_token: str) -> str:
        """Return Telegram bot username from the Bot API getMe method."""
        ...

    async def send_text(self, *, bot_token: str, chat_id: str, text: str) -> TelegramSendResult:
        """Send a plain text message to a Telegram chat."""
        ...


class NotificationOutboxRepository(Protocol):
    async def enqueue(
        self,
        items: list[NotificationOutboxItem],
    ) -> list[NotificationOutboxItem]: ...

    async def list_pending(self, *, limit: int) -> list[NotificationOutboxItem]: ...

    async def mark_sent(self, ids: list[UUID], *, sent_at: datetime) -> None: ...

    async def mark_failed(self, ids: list[UUID], *, error: str) -> None: ...
