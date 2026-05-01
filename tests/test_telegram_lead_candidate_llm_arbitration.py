"""LLM arbitration over review-only Telegram lead candidates."""

from datetime import UTC, datetime
import json

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.integrations.ai.chat import AiChatCompletion
from pur_leads.integrations.telegram.types import ResolvedTelegramSource, TelegramMessage
from pur_leads.services.telegram_fts_index import TelegramFtsIndexService
from pur_leads.services.telegram_lead_candidate_discovery import (
    TelegramLeadCandidateDiscoveryService,
)
from pur_leads.services.telegram_lead_candidate_llm_arbitration import (
    TelegramLeadCandidateLlmArbitrationService,
)
from pur_leads.services.telegram_raw_export import TelegramRawExportService
from pur_leads.services.telegram_sources import TelegramSourceService
from pur_leads.services.telegram_text_normalization import TelegramTextNormalizationService


def test_llm_arbitration_writes_prompt_response_trace_and_structured_decisions(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        source = TelegramSourceService(session).create_draft(
            "https://t.me/chat_mila_kolpakova",
            added_by="admin",
            purpose="lead_monitoring",
            start_mode="from_beginning",
        )
        export = TelegramRawExportService(session, raw_root=tmp_path / "raw").write_export(
            source=source,
            resolved_source=ResolvedTelegramSource(
                input_ref="https://t.me/chat_mila_kolpakova",
                source_kind="telegram_supergroup",
                telegram_id="-10042",
                username="chat_mila_kolpakova",
                title="Чат лидов",
            ),
            messages=[
                _message(10, "Посоветуйте камеру Dahua для квартиры"),
                _message(11, "Нужен выключатель Aqara в спальню", reply_to=10),
            ],
        )
        TelegramTextNormalizationService(
            session,
            processed_root=tmp_path / "processed",
        ).write_texts(export.run_id)
        TelegramFtsIndexService(session, search_root=tmp_path / "search").write_index(
            export.run_id
        )
        TelegramLeadCandidateDiscoveryService(
            session,
            output_root=tmp_path / "lead_candidates",
        ).write_candidates(export.run_id, limit=10)

        result = TelegramLeadCandidateLlmArbitrationService(
            session,
            output_root=tmp_path / "arbitration",
        ).write_arbitration(
            export.run_id,
            client=FakeLeadArbitrationClient(),
            provider="zai",
            model="GLM-5.1",
            model_profile="lead-arbitrator-strong",
            limit=10,
        )

        assert result.metrics["processed_candidates"] == 2
        assert result.metrics["lead_count"] == 1
        assert result.metrics["not_lead_count"] == 1
        assert result.arbitration_json_path.exists()
        assert result.traces_jsonl_path.exists()

        payload = json.loads(result.arbitration_json_path.read_text(encoding="utf-8"))
        assert payload["provider"] == "zai"
        assert payload["model"] == "GLM-5.1"
        assert payload["model_profile"] == "lead-arbitrator-strong"
        assert [item["decision"]["decision"] for item in payload["results"]] == [
            "lead",
            "not_lead",
        ]
        assert "Соседний контекст" in payload["results"][0]["prompt_text"]
        assert "нужен выключатель aqara" in payload["results"][0]["prompt_text"].casefold()
        assert payload["results"][0]["response_json"]["request_id"] == "fake-arbitration"

        trace_lines = result.traces_jsonl_path.read_text(encoding="utf-8").splitlines()
        assert len(trace_lines) == 2
        first_trace = json.loads(trace_lines[0])
        assert first_trace["prompt_text"] == payload["results"][0]["prompt_text"]
        assert first_trace["raw_response"] == payload["results"][0]["raw_response"]


def test_llm_arbitration_keeps_response_metadata_when_json_parse_fails(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        source = TelegramSourceService(session).create_draft(
            "https://t.me/chat_mila_kolpakova",
            added_by="admin",
            purpose="lead_monitoring",
            start_mode="from_beginning",
        )
        export = TelegramRawExportService(session, raw_root=tmp_path / "raw").write_export(
            source=source,
            resolved_source=ResolvedTelegramSource(
                input_ref="https://t.me/chat_mila_kolpakova",
                source_kind="telegram_supergroup",
                telegram_id="-10042",
                username="chat_mila_kolpakova",
                title="Чат лидов",
            ),
            messages=[_message(10, "Посоветуйте камеру Dahua для квартиры")],
        )
        TelegramTextNormalizationService(
            session,
            processed_root=tmp_path / "processed",
        ).write_texts(export.run_id)
        TelegramFtsIndexService(session, search_root=tmp_path / "search").write_index(
            export.run_id
        )
        TelegramLeadCandidateDiscoveryService(
            session,
            output_root=tmp_path / "lead_candidates",
        ).write_candidates(export.run_id, limit=10)

        result = TelegramLeadCandidateLlmArbitrationService(
            session,
            output_root=tmp_path / "arbitration",
        ).write_arbitration(
            export.run_id,
            client=InvalidJsonLeadArbitrationClient(),
            provider="zai",
            model="GLM-5.1",
            limit=1,
        )

        payload = json.loads(result.arbitration_json_path.read_text(encoding="utf-8"))
        item = payload["results"][0]
        assert item["decision"]["decision"] == "maybe"
        assert item["decision"]["error"] == "LLM arbitration expected valid JSON object"
        assert item["response_json"]["request_id"] == "invalid-json-request"
        assert item["response_json"]["usage"]["total_tokens"] == 3
        assert item["response_json"]["error"] == "LLM arbitration expected valid JSON object"


class FakeLeadArbitrationClient:
    async def complete(self, *, messages, model, temperature, max_tokens):  # noqa: ANN001
        user_prompt = str(messages[1].content)
        candidate_block = user_prompt.split('"neighbor_context"', 1)[0]
        decision = "not_lead" if '"telegram_message_id": 11' in candidate_block else "lead"
        return AiChatCompletion(
            content=json.dumps(
                {
                    "decision": decision,
                    "confidence": 0.91,
                    "need_operator": decision != "not_lead",
                    "why": "structured fake decision",
                    "matched_need": "проверка классификации",
                    "relevant_catalog_items": [],
                    "false_positive_reason": (
                        "это проверочный пример нецелевого обращения"
                        if decision == "not_lead"
                        else None
                    ),
                },
                ensure_ascii=False,
            ),
            model=model,
            request_id="fake-arbitration",
            usage={"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130},
            raw_response={"fake": True},
        )


class InvalidJsonLeadArbitrationClient:
    async def complete(self, *, messages, model, temperature, max_tokens):  # noqa: ANN001
        return AiChatCompletion(
            content="",
            model=model,
            request_id="invalid-json-request",
            usage={"total_tokens": 3},
            raw_response={"empty": True},
        )


def _message(message_id: int, text: str, *, reply_to: int | None = None) -> TelegramMessage:
    return TelegramMessage(
        monitored_source_ref="https://t.me/chat_mila_kolpakova",
        telegram_message_id=message_id,
        message_date=datetime(2026, 1, 31, 10, message_id, 0, tzinfo=UTC),
        sender_id=f"user-{message_id}",
        sender_display=f"User {message_id}",
        text=text,
        caption=None,
        has_media=False,
        media_metadata_json=None,
        reply_to_message_id=reply_to,
        thread_id=None,
        forward_metadata_json=None,
        raw_metadata_json={},
    )
