"""Z.AI chat-completion client."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx

from pur_leads.integrations.ai.chat import (
    AiChatCompletion,
    AiModelConcurrencyLimitExceeded,
    AiModelConcurrencyLimiter,
    AiModelLease,
    ChatMessageInput,
    message_payload,
)


class AiProviderError(RuntimeError):
    def __init__(
        self,
        *,
        status_code: int | None,
        error_code: str | None,
        message: str,
    ) -> None:
        super().__init__(f"AI provider error {error_code or 'unknown'}: {message}")
        self.status_code = status_code
        self.error_code = error_code
        self.provider_message = message


class ZaiChatCompletionClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout_seconds: float = 60.0,
        http_client: httpx.AsyncClient | None = None,
        concurrency_limiter: AiModelConcurrencyLimiter | None = None,
        worker_name: str = "worker",
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.http_client = http_client
        self.concurrency_limiter = concurrency_limiter
        self.worker_name = worker_name

    async def complete(
        self,
        *,
        messages: Sequence[ChatMessageInput],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> AiChatCompletion:
        payload = {
            "model": model,
            "messages": [message_payload(message) for message in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
            "do_sample": False,
            "thinking": {"type": "disabled"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        lease: AiModelLease | None = None
        if self.concurrency_limiter is not None:
            lease = self.concurrency_limiter.acquire_model_slot(
                provider="zai",
                model=model,
                worker_name=self.worker_name,
            )
            if lease is None:
                raise AiModelConcurrencyLimitExceeded(
                    provider="zai",
                    model=model,
                    retry_after_seconds=int(
                        getattr(self.concurrency_limiter, "retry_after_seconds", 5)
                    ),
                )
        client = self.http_client or httpx.AsyncClient(timeout=self.timeout_seconds)
        close_client = self.http_client is None
        try:
            try:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
            finally:
                if lease is not None and self.concurrency_limiter is not None:
                    self.concurrency_limiter.release_model_slot(lease)
        finally:
            if close_client:
                await client.aclose()

        data = _json_response(response)
        if response.status_code >= 400:
            error_value = data.get("error")
            error = error_value if isinstance(error_value, dict) else {}
            raise AiProviderError(
                status_code=response.status_code,
                error_code=_optional_string(error.get("code")),
                message=_optional_string(error.get("message")) or response.reason_phrase,
            )
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AiProviderError(
                status_code=response.status_code,
                error_code="invalid_response",
                message="AI provider response did not include message content",
            ) from exc
        if not isinstance(content, str):
            raise AiProviderError(
                status_code=response.status_code,
                error_code="invalid_response",
                message="AI provider message content is not text",
            )
        usage_value = data.get("usage")
        usage = usage_value if isinstance(usage_value, dict) else {}
        return AiChatCompletion(
            content=content,
            model=_optional_string(data.get("model")) or model,
            request_id=_optional_string(data.get("request_id")),
            usage=usage,
            raw_response=data,
        )


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError as exc:
        raise AiProviderError(
            status_code=response.status_code,
            error_code="invalid_json",
            message="AI provider returned non-JSON response",
        ) from exc
    if not isinstance(data, dict):
        raise AiProviderError(
            status_code=response.status_code,
            error_code="invalid_json",
            message="AI provider returned non-object response",
        )
    return data


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None
