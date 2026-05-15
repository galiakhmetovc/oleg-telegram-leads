from __future__ import annotations

from typing import Any

import httpx

from app.domain.notifications import TelegramSendResult


class TelegramSendError(RuntimeError):
    pass


class HttpTelegramMessageSender:
    def __init__(self, *, timeout_seconds: float = 10.0) -> None:
        self._timeout_seconds = timeout_seconds

    async def get_bot_username(self, *, bot_token: str) -> str:
        url = f"https://api.telegram.org/bot{bot_token}/getMe"
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            try:
                response = await client.post(url)
            except httpx.HTTPError as exc:
                raise TelegramSendError("Telegram API request failed") from exc

        payload = _response_payload(response)
        if response.status_code >= 400 or not payload.get("ok"):
            description = str(payload.get("description") or f"HTTP {response.status_code}")
            raise TelegramSendError(description)
        result = payload.get("result")
        if not isinstance(result, dict):
            raise TelegramSendError("Telegram API response has no bot result")
        username = result.get("username")
        if not isinstance(username, str):
            raise TelegramSendError("Telegram API response has no bot username")
        return username

    async def send_text(
        self,
        *,
        bot_token: str,
        chat_id: str,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> TelegramSendResult:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            try:
                response = await client.post(url, json=payload)
            except httpx.HTTPError as exc:
                raise TelegramSendError("Telegram API request failed") from exc

        return _message_result(response, chat_id=chat_id)

    async def edit_text(
        self,
        *,
        bot_token: str,
        chat_id: str,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> TelegramSendResult:
        url = f"https://api.telegram.org/bot{bot_token}/editMessageText"
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            try:
                response = await client.post(url, json=payload)
            except httpx.HTTPError as exc:
                raise TelegramSendError("Telegram API request failed") from exc

        return _message_result(response, chat_id=chat_id)

    async def answer_callback_query(
        self,
        *,
        bot_token: str,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
    ) -> None:
        url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
        payload: dict[str, Any] = {
            "callback_query_id": callback_query_id,
            "show_alert": show_alert,
        }
        if text is not None:
            payload["text"] = text
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            try:
                response = await client.post(url, json=payload)
            except httpx.HTTPError as exc:
                raise TelegramSendError("Telegram API request failed") from exc

        payload = _response_payload(response)
        if response.status_code >= 400 or not payload.get("ok"):
            description = str(payload.get("description") or f"HTTP {response.status_code}")
            raise TelegramSendError(description)


def _response_payload(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise TelegramSendError("Telegram API returned non-JSON response") from exc
    if not isinstance(payload, dict):
        raise TelegramSendError("Telegram API returned unexpected response")
    return payload


def _message_result(response: httpx.Response, *, chat_id: str) -> TelegramSendResult:
    payload = _response_payload(response)
    if response.status_code >= 400 or not payload.get("ok"):
        description = str(payload.get("description") or f"HTTP {response.status_code}")
        raise TelegramSendError(description)

    result = payload.get("result")
    if not isinstance(result, dict):
        raise TelegramSendError("Telegram API response has no message result")
    message_id = result.get("message_id")
    if not isinstance(message_id, int):
        raise TelegramSendError("Telegram API response has no message id")
    return TelegramSendResult(message_id=message_id, chat_id=chat_id)
