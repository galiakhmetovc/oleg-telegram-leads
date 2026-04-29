import json

import httpx
import pytest

from pur_leads.integrations.ai.chat import AiModelConcurrencyLimitExceeded, AiModelLease
from pur_leads.integrations.ai.zai_client import AiProviderError, ZaiChatCompletionClient


class FakeLimiter:
    def __init__(self, *, acquired: bool = True) -> None:
        self.acquired = acquired
        self.acquire_calls: list[dict] = []
        self.released: list[str] = []

    def acquire_model_slot(self, *, provider, model, worker_name):  # noqa: ANN001
        self.acquire_calls.append(
            {"provider": provider, "model": model, "worker_name": worker_name}
        )
        if not self.acquired:
            return None
        return AiModelLease(id="lease-1", provider=provider, model=model)

    def release_model_slot(self, lease: AiModelLease) -> None:
        self.released.append(lease.id)


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
async def test_zai_chat_client_uses_model_concurrency_limiter_and_releases_slot():
    requests: list[httpx.Request] = []
    limiter = FakeLimiter()

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "request_id": "req-1",
                "model": "glm-4.5-flash",
                "choices": [{"message": {"content": '{"items": []}'}}],
                "usage": {},
            },
        )

    client = ZaiChatCompletionClient(
        api_key="secret-key",
        base_url="https://api.z.ai/api/coding/paas/v4",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        concurrency_limiter=limiter,
        worker_name="worker-1",
    )

    await client.complete(
        messages=[{"role": "user", "content": "classify lead"}],
        model="glm-4.5-flash",
        temperature=0.0,
        max_tokens=512,
    )

    assert len(requests) == 1
    assert limiter.acquire_calls == [
        {"provider": "zai", "model": "glm-4.5-flash", "worker_name": "worker-1"}
    ]
    assert limiter.released == ["lease-1"]


@pytest.mark.asyncio
async def test_zai_chat_client_raises_without_request_when_model_slot_is_unavailable():
    requests: list[httpx.Request] = []
    limiter = FakeLimiter(acquired=False)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={})

    client = ZaiChatCompletionClient(
        api_key="secret-key",
        base_url="https://api.z.ai/api/coding/paas/v4",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        concurrency_limiter=limiter,
        worker_name="worker-1",
    )

    with pytest.raises(AiModelConcurrencyLimitExceeded) as exc:
        await client.complete(
            messages=[{"role": "user", "content": "classify lead"}],
            model="glm-4.5-flash",
            temperature=0.0,
            max_tokens=512,
        )

    assert requests == []
    assert exc.value.retry_after_seconds == 5
    assert "glm-4.5-flash" in str(exc.value)
    assert limiter.released == []


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
