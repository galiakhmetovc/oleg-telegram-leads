import json

import httpx
import pytest

from pur_leads.integrations.ai.zai_client import AiProviderError, ZaiChatCompletionClient


@pytest.mark.asyncio
async def test_zai_chat_client_posts_to_coding_endpoint_and_returns_usage():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payload = json.loads(request.content)
        assert request.url == "https://api.z.ai/api/coding/paas/v4/chat/completions"
        assert request.headers["authorization"] == "Bearer secret-key"
        assert payload["model"] == "glm-5.1"
        assert payload["messages"] == [{"role": "user", "content": "extract catalog"}]
        assert payload["temperature"] == 0.0
        assert payload["max_tokens"] == 1024
        assert payload["do_sample"] is False
        assert payload["thinking"] == {"type": "disabled"}
        return httpx.Response(
            200,
            json={
                "request_id": "req-1",
                "model": "glm-5.1",
                "choices": [{"message": {"content": '{"facts": []}'}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )

    client = ZaiChatCompletionClient(
        api_key="secret-key",
        base_url="https://api.z.ai/api/coding/paas/v4",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    completion = await client.complete(
        messages=[{"role": "user", "content": "extract catalog"}],
        model="glm-5.1",
        temperature=0.0,
        max_tokens=1024,
    )

    assert len(requests) == 1
    assert completion.content == '{"facts": []}'
    assert completion.model == "glm-5.1"
    assert completion.request_id == "req-1"
    assert completion.usage == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


@pytest.mark.asyncio
async def test_zai_chat_client_raises_masked_provider_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={"error": {"code": "1310", "message": "Weekly/Monthly Limit Exhausted"}},
        )

    client = ZaiChatCompletionClient(
        api_key="secret-key",
        base_url="https://api.z.ai/api/coding/paas/v4/",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(AiProviderError) as exc:
        await client.complete(
            messages=[{"role": "user", "content": "extract catalog"}],
            model="glm-5.1",
            temperature=0.0,
            max_tokens=1024,
        )

    assert exc.value.status_code == 429
    assert exc.value.error_code == "1310"
    assert "secret-key" not in str(exc.value)
