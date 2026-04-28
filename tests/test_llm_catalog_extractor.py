import pytest

from pur_leads.integrations.ai.chat import AiChatCompletion, AiChatMessage
from pur_leads.integrations.catalog.llm_extractor import LlmCatalogExtractor


class FakeChatClient:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[list[AiChatMessage]] = []

    async def complete(self, *, messages, model, temperature, max_tokens):  # noqa: ANN001
        self.calls.append(messages)
        return AiChatCompletion(
            content=self.content,
            model=model,
            request_id="req-1",
            usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            raw_response={"id": "chatcmpl-test"},
        )


@pytest.mark.asyncio
async def test_llm_catalog_extractor_maps_structured_facts():
    client = FakeChatClient(
        """
        {
          "facts": [
            {
              "fact_type": "product",
              "canonical_name": "Dahua Hero A1",
              "category": "video_surveillance",
              "terms": ["hero a1", "dahua hero", "wi-fi camera"],
              "attributes": [{"name": "connectivity", "value": "Wi-Fi"}],
              "evidence_quote": "Dahua Hero A1 Wi-Fi камера",
              "confidence": 0.91
            },
            {
              "fact_type": "lead_phrase",
              "canonical_name": "нужна камера на дачу",
              "category": "video_surveillance",
              "terms": ["нужна камера на дачу"],
              "evidence_quote": "Если нужна камера на дачу",
              "confidence": 0.82
            },
            {
              "fact_type": "negative_phrase",
              "canonical_name": "обзор камеры без покупки",
              "category": "video_surveillance",
              "terms": ["обзор камеры"],
              "evidence_quote": "это обзор камеры",
              "confidence": 0.77
            },
            {
              "fact_type": "offer",
              "canonical_name": "Dahua Hero A1 price",
              "category": "video_surveillance",
              "offer": {"price_text": "от 9900 руб", "currency": "RUB"},
              "evidence_quote": "от 9900 руб",
              "confidence": 0.88
            }
          ]
        }
        """
    )
    extractor = LlmCatalogExtractor(client=client, model="glm-test")

    facts = await extractor.extract_catalog_facts(
        source_id="source-1",
        chunk_id="chunk-1",
        payload={"text": "Dahua Hero A1 Wi-Fi камера. Если нужна камера на дачу."},
    )

    assert [fact.candidate_type for fact in facts] == [
        "item",
        "lead_phrase",
        "negative_phrase",
        "offer",
    ]
    assert facts[0].fact_type == "product"
    assert facts[0].canonical_name == "Dahua Hero A1"
    assert facts[0].value_json["category_slug"] == "video_surveillance"
    assert facts[0].value_json["terms"] == ["hero a1", "dahua hero", "wi-fi camera"]
    assert facts[0].value_json["attributes"] == [{"name": "connectivity", "value": "Wi-Fi"}]
    assert facts[1].fact_type == "lead_intent"
    assert facts[1].value_json["polarity"] == "positive"
    assert facts[2].value_json["polarity"] == "negative"
    assert facts[3].candidate_type == "offer"
    assert facts[3].value_json["price_text"] == "от 9900 руб"
    assert facts[3].confidence == 0.88
    assert facts[0].source_id == "source-1"
    assert facts[0].chunk_id == "chunk-1"
    assert extractor.last_token_usage_json == {
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
        "request_id": "req-1",
        "model": "glm-test",
    }
    assert "Return strict JSON" in client.calls[0][0].content


@pytest.mark.asyncio
async def test_llm_catalog_extractor_rejects_invalid_json():
    extractor = LlmCatalogExtractor(client=FakeChatClient("not-json"), model="glm-test")

    with pytest.raises(ValueError, match="valid JSON"):
        await extractor.extract_catalog_facts(
            source_id="source-1",
            chunk_id="chunk-1",
            payload={"text": "bad"},
        )
