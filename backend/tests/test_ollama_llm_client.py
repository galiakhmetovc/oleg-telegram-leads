from __future__ import annotations

import json

import pytest

from app.domain.llm_settings import DEFAULT_LLM_SYSTEM_PROMPT
from app.infrastructure.llm.ollama_client import OllamaLlmVerificationClient


@pytest.mark.asyncio
async def test_ollama_client_tells_model_to_use_evidence_only_from_target_message(monkeypatch) -> None:
    FakeAsyncClient.requests = []
    monkeypatch.setattr("app.infrastructure.llm.ollama_client.httpx.AsyncClient", FakeAsyncClient)

    await OllamaLlmVerificationClient(endpoint="http://ollama.local/api/chat", timeout_seconds=30).verify(
        model="lead-qwen-ru",
        context_pack={
            "message": {"text": "В поисках двух человек для раскопки водопровода"},
            "rule_engine_result": {"fact_labels": [], "signal_labels": []},
        },
        system_prompt=DEFAULT_LLM_SYSTEM_PROMPT,
    )

    payload = FakeAsyncClient.requests[0]["json"]
    system_prompt = payload["messages"][0]["content"]
    assert "evidence" in system_prompt
    assert "anti_evidence" in system_prompt
    assert "только из message.text" in system_prompt
    assert "score не является confidence" in system_prompt
    assert "matched_golden_ids всегда возвращай пустым массивом" in system_prompt
    assert "golden_examples" not in system_prompt


class FakeResponse:
    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, object]:
        return {
            "message": {
                "content": json.dumps(
                    {
                        "verdict": "not_lead",
                        "confidence": 0.9,
                        "recommendation": "keep",
                        "agrees_with_rule_engine": True,
                        "matched_golden_ids": [],
                        "missing_fact_types": [],
                        "suspicious_fact_types": [],
                        "missing_signal_types": [],
                        "evidence": [],
                        "anti_evidence": ["раскопка водопровода"],
                    }
                )
            }
        }


class FakeAsyncClient:
    requests: list[dict[str, object]] = []

    def __init__(self, *, timeout: float) -> None:
        self.timeout = timeout

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(self, endpoint: str, *, json: dict[str, object]) -> FakeResponse:
        self.requests.append({"endpoint": endpoint, "json": json, "timeout": self.timeout})
        return FakeResponse()
