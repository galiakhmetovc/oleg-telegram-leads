"""Telegram Bot API notification adapter."""

from __future__ import annotations

from typing import Any

import httpx


class TelegramBotApiError(RuntimeError):
    def __init__(self, message: str, *, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class TelegramBotRateLimitError(TelegramBotApiError):
    pass


class TelegramBotLeadNotifier:
    def __init__(
        self,
        bot_token: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 10,
    ) -> None:
        self.bot_token = bot_token
        self.transport = transport
        self.timeout = timeout

    async def send_lead_notification(self, *, chat_id: str, text: str) -> dict[str, Any]:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            response = await client.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "disable_web_page_preview": True,
                },
            )
            _raise_for_bot_error(response)
            payload = response.json()
        result = payload.get("result") if isinstance(payload, dict) else None
        if isinstance(result, dict):
            return {"message_id": result.get("message_id")}
        return {}


def _raise_for_bot_error(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    retry_after = _retry_after_seconds(response)
    if response.status_code == 429:
        raise TelegramBotRateLimitError(
            "Telegram Bot API rate limit",
            retry_after_seconds=retry_after,
        )
    raise TelegramBotApiError(
        f"Telegram Bot API error {response.status_code}",
        retry_after_seconds=retry_after,
    )


def _retry_after_seconds(response: httpx.Response) -> int | None:
    header_value = response.headers.get("retry-after")
    if header_value is not None:
        try:
            return max(1, int(header_value))
        except ValueError:
            pass
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    parameters = payload.get("parameters")
    if not isinstance(parameters, dict):
        return None
    value = parameters.get("retry_after")
    if value is None or isinstance(value, bool):
        return None
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return None
