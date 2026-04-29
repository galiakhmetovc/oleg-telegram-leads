"""Telegram Bot API setup helpers."""

from __future__ import annotations

from typing import Any

import httpx


class TelegramBotSetupError(RuntimeError):
    pass


class TelegramBotSetupClient:
    def __init__(
        self,
        *,
        base_url: str = "https://api.telegram.org",
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 10,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.timeout = timeout

    async def get_me(self, token: str) -> dict[str, Any]:
        return await self._request(token, "getMe")

    async def get_updates(self, token: str) -> list[dict[str, Any]]:
        result = await self._request(
            token,
            "getUpdates",
            json={
                "limit": 100,
                "timeout": 0,
                "allowed_updates": ["message", "channel_post", "my_chat_member"],
            },
        )
        if not isinstance(result, list):
            raise TelegramBotSetupError("Telegram getUpdates returned unexpected payload")
        return [item for item in result if isinstance(item, dict)]

    async def send_message(
        self,
        token: str,
        *,
        chat_id: str,
        text: str,
        message_thread_id: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if message_thread_id is not None:
            payload["message_thread_id"] = message_thread_id
        result = await self._request(token, "sendMessage", json=payload)
        if not isinstance(result, dict):
            return {}
        return result

    async def _request(
        self,
        token: str,
        method: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}/bot{token}/{method}"
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            response = await client.post(url, json=json or {})
        try:
            payload = response.json()
        except ValueError as exc:
            raise TelegramBotSetupError(f"Telegram {method} returned invalid JSON") from exc
        if response.status_code >= 400 or not payload.get("ok"):
            description = payload.get("description") if isinstance(payload, dict) else None
            raise TelegramBotSetupError(description or f"Telegram {method} failed")
        return payload.get("result")


def notification_candidates_from_updates(updates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: dict[tuple[str, int | None], dict[str, Any]] = {}
    for update in updates:
        message = _message_from_update(update)
        if not isinstance(message, dict):
            continue
        chat = message.get("chat")
        if not isinstance(chat, dict):
            continue
        chat_id = chat.get("id")
        chat_type = chat.get("type")
        if chat_id is None or chat_type not in {"group", "supergroup", "channel"}:
            continue
        thread_id = _optional_int(message.get("message_thread_id"))
        title = chat.get("title") or chat.get("username") or str(chat_id)
        candidate = {
            "chat_id": str(chat_id),
            "title": str(title),
            "chat_type": str(chat_type),
            "message_thread_id": thread_id,
        }
        candidates[(candidate["chat_id"], thread_id)] = candidate
    return list(candidates.values())


def _message_from_update(update: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("message", "channel_post", "edited_message", "edited_channel_post"):
        value = update.get(key)
        if isinstance(value, dict):
            return value
    return None


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
