import httpx
import pytest

from pur_leads.integrations.telegram.bot_notifier import (
    TelegramBotLeadNotifier,
    TelegramBotRateLimitError,
)


@pytest.mark.asyncio
async def test_bot_notifier_raises_safe_rate_limit_error_with_retry_after():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "secret-token" in str(request.url)
        return httpx.Response(
            429,
            json={"ok": False, "parameters": {"retry_after": 17}},
            request=request,
        )

    notifier = TelegramBotLeadNotifier(
        "secret-token",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(TelegramBotRateLimitError) as exc_info:
        await notifier.send_lead_notification(chat_id="chat", text="lead")

    assert exc_info.value.retry_after_seconds == 17
    assert "secret-token" not in str(exc_info.value)
    assert "sendMessage" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_bot_notifier_success_returns_message_id():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 42}})

    notifier = TelegramBotLeadNotifier(
        "secret-token",
        transport=httpx.MockTransport(handler),
    )

    result = await notifier.send_lead_notification(chat_id="chat", text="lead")

    assert result == {"message_id": 42}
