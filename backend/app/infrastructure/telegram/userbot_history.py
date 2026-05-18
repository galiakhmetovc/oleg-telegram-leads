from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from telethon import TelegramClient, errors, events
from telethon.sessions import StringSession

from app.domain.telegram_ingestion import TelegramFetchedMessage, TelegramUserbotFloodWait
from app.domain.telegram_ingestion import TelegramSourceSubscription


class TelethonUserbotHistoryClient:
    def __init__(
        self,
        *,
        api_id: int,
        api_hash: str,
        session_string: str,
    ) -> None:
        self._client = TelegramClient(StringSession(session_string), api_id, api_hash)

    async def __aenter__(self) -> TelethonUserbotHistoryClient:
        await self._client.connect()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self._client.disconnect()

    async def resolve_source(self, input_ref: str) -> str | None:
        try:
            entity = await self._client.get_entity(input_ref)
        except errors.FloodWaitError as exc:
            raise TelegramUserbotFloodWait(int(getattr(exc, "seconds", 0) or 0)) from exc
        return _entity_id(entity)

    async def get_latest_message_id(self, input_ref: str) -> tuple[str | None, int | None]:
        try:
            entity = await self._client.get_entity(input_ref)
            latest_messages = [message async for message in self._client.iter_messages(entity, limit=1)]
        except errors.FloodWaitError as exc:
            raise TelegramUserbotFloodWait(int(getattr(exc, "seconds", 0) or 0)) from exc
        latest_id = int(latest_messages[0].id) if latest_messages else None
        return _entity_id(entity), latest_id

    async def fetch_messages_after(
        self,
        input_ref: str,
        *,
        after_message_id: int,
        limit: int,
    ) -> list[TelegramFetchedMessage]:
        try:
            entity = await self._client.get_entity(input_ref)
            telegram_chat_id = _entity_id(entity)
            messages = [
                _message_from_telethon(telegram_chat_id, message)
                async for message in self._client.iter_messages(
                    entity,
                    limit=limit,
                    min_id=after_message_id,
                    reverse=True,
                    wait_time=1,
                )
            ]
        except errors.FloodWaitError as exc:
            raise TelegramUserbotFloodWait(int(getattr(exc, "seconds", 0) or 0)) from exc
        return [message for message in messages if message.text and message.text.strip()]

    async def watch_sources(
        self,
        sources: Sequence[TelegramSourceSubscription],
        handler: Callable[[UUID, TelegramFetchedMessage], Awaitable[None]],
        *,
        reload_after_seconds: float | None = None,
    ) -> None:
        try:
            for source in sources:
                entity = await self._client.get_entity(source.input_ref)
                telegram_chat_id = _entity_id(entity)

                async def _handle(
                    event: Any,
                    *,
                    source: TelegramSourceSubscription = source,
                    telegram_chat_id: str | None = telegram_chat_id,
                ) -> None:
                    message = _message_from_telethon(telegram_chat_id, event.message)
                    await handler(source.source_chat_id, message)

                self._client.add_event_handler(_handle, events.NewMessage(chats=entity))
            if reload_after_seconds is not None and reload_after_seconds > 0:
                try:
                    await asyncio.wait_for(
                        self._client.run_until_disconnected(),
                        timeout=reload_after_seconds,
                    )
                except TimeoutError:
                    await self._client.disconnect()
            else:
                await self._client.run_until_disconnected()
        except errors.FloodWaitError as exc:
            raise TelegramUserbotFloodWait(int(getattr(exc, "seconds", 0) or 0)) from exc


def _entity_id(entity: Any) -> str | None:
    value = getattr(entity, "id", None)
    return str(value) if value is not None else None


def _message_from_telethon(
    telegram_chat_id: str | None,
    message: Any,
) -> TelegramFetchedMessage:
    sender = getattr(message, "sender", None)
    sender_username = getattr(sender, "username", None) if sender is not None else None
    text = getattr(message, "message", None) or getattr(message, "raw_text", None)
    message_date = getattr(message, "date", None)
    sender_id = getattr(message, "sender_id", None)
    return TelegramFetchedMessage(
        telegram_chat_id=telegram_chat_id,
        telegram_message_id=int(message.id),
        message_date=message_date if isinstance(message_date, datetime) else None,
        sender_id=str(sender_id) if sender_id is not None else None,
        sender_username=str(sender_username) if sender_username else None,
        text=str(text) if text else None,
        raw_payload={
            "chat_id": telegram_chat_id,
            "message_id": int(message.id),
            "date": message_date.isoformat() if isinstance(message_date, datetime) else None,
            "sender_id": str(sender_id) if sender_id is not None else None,
        },
    )


class TelethonUserbotHistoryClientFactory:
    def create(
        self,
        *,
        api_id: int,
        api_hash: str,
        session_string: str,
    ) -> TelethonUserbotHistoryClient:
        return TelethonUserbotHistoryClient(
            api_id=api_id,
            api_hash=api_hash,
            session_string=session_string,
        )
