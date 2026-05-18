from __future__ import annotations

import json
from typing import Any

import httpx

from app.domain.llm_verification import LLM_VERIFICATION_RESPONSE_SCHEMA


class OllamaLlmVerificationClient:
    def __init__(self, *, endpoint: str, timeout_seconds: float) -> None:
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds

    async def verify(
        self,
        *,
        model: str,
        context_pack: dict[str, object],
        system_prompt: str,
    ) -> tuple[dict[str, object], str]:
        payload = {
            "model": model,
            "stream": False,
            "format": LLM_VERIFICATION_RESPONSE_SCHEMA,
            "options": {"temperature": 0},
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": json.dumps(context_pack, ensure_ascii=False),
                },
            ],
        }
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(self._endpoint, json=payload)
            response.raise_for_status()
        response_payload = response.json()
        raw_content = _extract_content(response_payload)
        return _json_object(raw_content), raw_content


def _extract_content(payload: dict[str, Any]) -> str:
    message = payload.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
    response = payload.get("response")
    if isinstance(response, str):
        return response
    raise ValueError("Ollama response does not contain message.content")


def _json_object(raw_content: str) -> dict[str, object]:
    parsed = json.loads(raw_content)
    if not isinstance(parsed, dict):
        raise ValueError("LLM response JSON must be an object")
    return parsed
