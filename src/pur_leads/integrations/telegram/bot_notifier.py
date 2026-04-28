"""Telegram Bot API notification adapter."""

from __future__ import annotations

from typing import Any

import httpx


class TelegramBotLeadNotifier:
    def __init__(self, bot_token: str) -> None:
        self.bot_token = bot_token

    async def send_lead_notification(self, *, chat_id: str, text: str) -> dict[str, Any]:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "disable_web_page_preview": True,
                },
            )
            response.raise_for_status()
            payload = response.json()
        result = payload.get("result") if isinstance(payload, dict) else None
        if isinstance(result, dict):
            return {"message_id": result.get("message_id")}
        return {}
