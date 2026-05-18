from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.llm_settings import get_llm_settings_repository
from app.domain.llm_settings import LlmSettings
from app.main import create_app


def test_reads_and_updates_llm_settings_with_routes() -> None:
    repository = InMemoryLlmSettingsRepository()
    app = create_app()
    app.dependency_overrides[get_llm_settings_repository] = lambda: repository
    client = TestClient(app)

    initial = client.get("/api/v1/settings/llm")

    assert initial.status_code == 200
    assert initial.json()["model"] == "lead-qwen-ru"
    assert initial.json()["routes"] == []

    payload = {
        "enabled": True,
        "model": "lead-qwen-ru",
        "endpoint": "http://host.docker.internal:11434/api/chat",
        "timeout_seconds": 180,
        "system_prompt": "Return clean JSON",
        "routes": [
            {
                "id": "designers_non_noise",
                "name": "Дизайнерские чаты без шума",
                "enabled": True,
                "priority": 100,
                "match_mode": "all",
                "conditions": {
                    "source_chat_ids": ["chat-designers"],
                    "score_min": 20,
                    "review_lanes": ["direct_pur_lead"],
                    "exclude_signal_types": ["operator_noise"],
                    "exclude_fact_types": ["operator_noise_fact"],
                },
            }
        ],
    }

    updated = client.put("/api/v1/settings/llm", json=payload)

    assert updated.status_code == 200
    body = updated.json()
    assert body["model"] == "lead-qwen-ru"
    assert body["routes"][0]["conditions"]["exclude_signal_types"] == ["operator_noise"]
    assert repository.saved is not None
    assert repository.saved.routes[0].conditions.exclude_fact_types == ["operator_noise_fact"]


class InMemoryLlmSettingsRepository:
    def __init__(self) -> None:
        self.saved: LlmSettings | None = None

    async def get_settings(self) -> LlmSettings:
        from app.domain.llm_settings import default_llm_settings

        return self.saved or default_llm_settings(
            model="lead-qwen-ru",
            endpoint="http://host.docker.internal:11434/api/chat",
            timeout_seconds=240,
        )

    async def save_settings(self, settings: LlmSettings) -> LlmSettings:
        self.saved = settings
        return settings
