from datetime import datetime

import pytest

from pur_leads.integrations.ai.chat import AiChatCompletion
from pur_leads.integrations.leads.llm_shadow_classifier import (
    LlmLeadShadowClassifier,
    PROMPT_VERSION,
)
from pur_leads.workers.runtime import LeadMessageForClassification


class FakeAiChatClient:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict] = []

    async def complete(self, *, messages, model, temperature, max_tokens):  # noqa: ANN001
        self.calls.append(
            {
                "messages": messages,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        return AiChatCompletion(
            content=self.content,
            model=model,
            request_id="req-1",
            usage={"prompt_tokens": 111, "completion_tokens": 22, "total_tokens": 133},
            raw_response={},
        )


@pytest.mark.asyncio
async def test_llm_lead_shadow_classifier_parses_structured_json_and_uses_flash_model():
    client = FakeAiChatClient(
        """
        {
          "items": [
            {
              "source_message_id": "msg-1",
              "decision": "lead",
              "confidence": 0.87,
              "commercial_value_score": 0.8,
              "negative_score": 0.05,
              "reason": "Пользователь ищет камеру для дома",
              "signals": ["ищет камеру"],
              "negative_signals": [],
              "matched_text": ["камеру для дома"],
              "notify_reason": "purchase_intent"
            }
          ]
        }
        """
    )
    classifier = LlmLeadShadowClassifier(
        client=client,
        model="glm-4.5-flash",
        temperature=0.0,
        max_tokens=1024,
    )

    results = await classifier.classify_message_batch(
        messages=[
            LeadMessageForClassification(
                source_message_id="msg-1",
                monitored_source_id="source-1",
                telegram_message_id=10,
                sender_id="sender-1",
                message_date=datetime(2026, 4, 29, 12, 0, 0),
                message_text="ищу камеру для дома",
                normalized_text="ищу камеру для дома",
            )
        ],
        payload={"detection_mode": "live"},
    )

    assert client.calls[0]["model"] == "glm-4.5-flash"
    assert client.calls[0]["temperature"] == 0.0
    assert client.calls[0]["max_tokens"] == 1024
    assert results[0].classifier_version_id == ""
    assert results[0].source_message_id == "msg-1"
    assert results[0].decision == "lead"
    assert results[0].detection_mode == "live"
    assert results[0].confidence == 0.87
    assert results[0].commercial_value_score == 0.8
    assert results[0].negative_score == 0.05
    assert results[0].high_value_signals_json == ["ищет камеру"]
    assert results[0].matches is not None
    assert results[0].matches[0].match_type == "llm_signal"
    assert results[0].matches[0].matched_text == "камеру для дома"
    assert classifier.prompt_version == PROMPT_VERSION
    assert classifier.last_token_usage_json == {
        "prompt_tokens": 111,
        "completion_tokens": 22,
        "total_tokens": 133,
        "request_id": "req-1",
        "model": "glm-4.5-flash",
    }
