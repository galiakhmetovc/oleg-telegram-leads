from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import httpx

from app.domain.lead_handling import LeadHandlingActor
from app.infrastructure.notifications.telegram_sender import TelegramSendError


@dataclass(frozen=True)
class TelegramBotCallback:
    action: str
    source_message_id: UUID | None
    status: str | None
    callback_query_id: str
    chat_id: str
    chat_type: str
    message_id: int
    actor: LeadHandlingActor
    current_text: str


@dataclass(frozen=True)
class TelegramBotPrivateMessage:
    chat_id: str
    message_id: int
    actor: LeadHandlingActor
    text: str


@dataclass(frozen=True)
class TelegramBotUpdate:
    update_id: int
    callback: TelegramBotCallback | None = None
    private_message: TelegramBotPrivateMessage | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> TelegramBotUpdate:
        raw_update_id = payload["update_id"]
        update_id = raw_update_id if isinstance(raw_update_id, int) else int(str(raw_update_id))
        callback_payload = payload.get("callback_query")
        if isinstance(callback_payload, dict):
            callback = _callback_from_payload(callback_payload)
            return cls(update_id=update_id, callback=callback)
        message_payload = payload.get("message")
        if isinstance(message_payload, dict):
            private_message = _private_message_from_payload(message_payload)
            return cls(update_id=update_id, private_message=private_message)
        return cls(update_id=update_id)


class HttpTelegramBotUpdateClient:
    def __init__(self, *, timeout_seconds: float = 35.0) -> None:
        self._timeout_seconds = timeout_seconds

    async def get_updates(
        self,
        *,
        bot_token: str,
        offset: int | None,
        timeout_seconds: int,
    ) -> list[TelegramBotUpdate]:
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
        request_payload: dict[str, object] = {
            "timeout": timeout_seconds,
            "allowed_updates": ["callback_query", "message"],
        }
        if offset is not None:
            request_payload["offset"] = offset
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            try:
                response = await client.post(url, json=request_payload)
            except httpx.HTTPError as exc:
                raise TelegramSendError("Telegram API request failed") from exc
        payload = response.json()
        if response.status_code >= 400 or not isinstance(payload, dict) or not payload.get("ok"):
            description = payload.get("description") if isinstance(payload, dict) else None
            raise TelegramSendError(str(description or f"HTTP {response.status_code}"))
        result = payload.get("result")
        if not isinstance(result, list):
            raise TelegramSendError("Telegram API response has no updates result")
        return [
            TelegramBotUpdate.from_payload(item)
            for item in result
            if isinstance(item, dict) and "update_id" in item
        ]


def _callback_from_payload(payload: dict[object, object]) -> TelegramBotCallback | None:
    data = payload.get("data")
    message = payload.get("message")
    sender = payload.get("from")
    if not isinstance(data, str) or not isinstance(message, dict) or not isinstance(sender, dict):
        return None
    parsed = _parse_callback_data(data)
    if parsed is None:
        return None
    action, source_message_id, status = parsed
    chat = message.get("chat")
    if not isinstance(chat, dict):
        return None
    message_id = message.get("message_id")
    if not isinstance(message_id, int):
        return None
    return TelegramBotCallback(
        action=action,
        source_message_id=source_message_id,
        status=status,
        callback_query_id=str(payload.get("id") or ""),
        chat_id=str(chat.get("id") or ""),
        chat_type=str(chat.get("type") or ""),
        message_id=message_id,
        actor=_actor_from_payload(sender),
        current_text=str(message.get("text") or ""),
    )


def _private_message_from_payload(payload: dict[object, object]) -> TelegramBotPrivateMessage | None:
    chat = payload.get("chat")
    sender = payload.get("from")
    text = payload.get("text")
    message_id = payload.get("message_id")
    if (
        not isinstance(chat, dict)
        or chat.get("type") != "private"
        or not isinstance(sender, dict)
        or not isinstance(text, str)
        or not isinstance(message_id, int)
    ):
        return None
    return TelegramBotPrivateMessage(
        chat_id=str(chat.get("id") or ""),
        message_id=message_id,
        actor=_actor_from_payload(sender),
        text=text,
    )


def _parse_callback_data(data: str) -> tuple[str, UUID | None, str | None] | None:
    parts = data.split(":")
    if parts[:2] != ["lh", "my_leads"]:
        if len(parts) < 3 or parts[0] != "lh":
            return None
    action = parts[1]
    if action == "my_leads":
        return action, None, None
    if action in {"claim", "notlead", "open", "comment"} and len(parts) == 3:
        return action, UUID(parts[2]), None
    if action == "status" and len(parts) == 4:
        return action, UUID(parts[2]), parts[3]
    return None


def _actor_from_payload(payload: dict[object, object]) -> LeadHandlingActor:
    first_name = str(payload.get("first_name") or "").strip()
    last_name = str(payload.get("last_name") or "").strip()
    display_name = " ".join(part for part in [first_name, last_name] if part) or None
    username = payload.get("username")
    return LeadHandlingActor(
        telegram_user_id=str(payload.get("id") or ""),
        telegram_username=str(username) if username else None,
        display_name=display_name,
    )
