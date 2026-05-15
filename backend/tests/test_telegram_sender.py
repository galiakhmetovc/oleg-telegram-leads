from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.domain.notifications import TelegramSendResult
from app.infrastructure.notifications.telegram_sender import HttpTelegramMessageSender


@pytest.mark.asyncio
async def test_http_telegram_sender_includes_reply_markup(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, Any] | None]] = []

    monkeypatch.setattr(
        "app.infrastructure.notifications.telegram_sender.httpx.AsyncClient",
        _telegram_client_factory(calls),
    )
    reply_markup = {
        "inline_keyboard": [[{"text": "Взял", "callback_data": "lh:claim:source"}]]
    }

    result = await HttpTelegramMessageSender().send_text(
        bot_token="token-secret",
        chat_id="-100sales",
        text="Лид",
        reply_markup=reply_markup,
    )

    assert result.message_id == 777
    assert calls == [
        (
            "https://api.telegram.org/bottoken-secret/sendMessage",
            {"chat_id": "-100sales", "text": "Лид", "reply_markup": reply_markup},
        )
    ]


@pytest.mark.asyncio
async def test_http_telegram_sender_edits_text_and_answers_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, Any] | None]] = []
    monkeypatch.setattr(
        "app.infrastructure.notifications.telegram_sender.httpx.AsyncClient",
        _telegram_client_factory(calls),
    )
    sender = HttpTelegramMessageSender()
    reply_markup = {"inline_keyboard": []}

    edited = await sender.edit_text(
        bot_token="token-secret",
        chat_id="-100sales",
        message_id=42,
        text="Лид взят",
        reply_markup=reply_markup,
    )
    await sender.answer_callback_query(
        bot_token="token-secret",
        callback_query_id="callback-1",
        text="Заявка назначена",
        show_alert=True,
    )

    assert edited == TelegramSendResult(message_id=777, chat_id="-100sales")
    assert calls == [
        (
            "https://api.telegram.org/bottoken-secret/editMessageText",
            {
                "chat_id": "-100sales",
                "message_id": 42,
                "text": "Лид взят",
                "reply_markup": reply_markup,
            },
        ),
        (
            "https://api.telegram.org/bottoken-secret/answerCallbackQuery",
            {
                "callback_query_id": "callback-1",
                "text": "Заявка назначена",
                "show_alert": True,
            },
        ),
    ]


def _telegram_client_factory(
    calls: list[tuple[str, dict[str, Any] | None]],
) -> type:
    class FakeAsyncClient:
        def __init__(self, *, timeout: float) -> None:
            self.timeout = timeout

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
            return None

        async def post(
            self,
            url: str,
            json: dict[str, Any] | None = None,
        ) -> httpx.Response:
            calls.append((url, json))
            result: dict[str, object] | bool
            if url.endswith("/answerCallbackQuery"):
                result = True
            else:
                result = {"message_id": 777}
            return httpx.Response(200, json={"ok": True, "result": result})

    return FakeAsyncClient
