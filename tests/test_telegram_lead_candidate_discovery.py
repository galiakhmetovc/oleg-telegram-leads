"""Archive lead candidate discovery over prepared Telegram search indexes."""

from datetime import UTC, datetime
import json

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.integrations.telegram.types import ResolvedTelegramSource, TelegramMessage
from pur_leads.services.telegram_fts_index import TelegramFtsIndexService
from pur_leads.services.telegram_lead_candidate_discovery import (
    TelegramLeadCandidateDiscoveryService,
)
from pur_leads.services.telegram_raw_export import TelegramRawExportService
from pur_leads.services.telegram_sources import TelegramSourceService
from pur_leads.services.telegram_text_normalization import TelegramTextNormalizationService


def test_telegram_lead_candidate_discovery_finds_intent_topic_candidates(tmp_path):
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
                _message(1, "Нужна камера Dahua для квартиры"),
                _message(2, "Камерный дом и спокойный двор"),
                _message(3, "Продаю камеру после ремонта"),
                _message(4, "Подскажите видеодомофон с приложением"),
            ],
        )
        TelegramTextNormalizationService(
            session,
            processed_root=tmp_path / "processed",
        ).write_texts(export.run_id)
        TelegramFtsIndexService(session, search_root=tmp_path / "search").write_index(
            export.run_id
        )

        result = TelegramLeadCandidateDiscoveryService(
            session,
            output_root=tmp_path / "lead_candidates",
        ).write_candidates(export.run_id, limit=10)

        assert result.candidates_json_path.exists()
        assert result.summary_path.exists()
        assert result.metrics["scanned_documents"] == 4
        assert result.metrics["candidate_count"] == 2
        candidate_ids = [candidate["telegram_message_id"] for candidate in result.candidates]
        assert candidate_ids == [1, 4]

        first = result.candidates[0]
        assert first["status"] == "needs_review"
        assert first["message_url"] == "https://t.me/chat_mila_kolpakova/1"
        assert "нужна" in first["matched_intents"]
        assert "камера" in first["matched_topics"]
        assert "intent_and_topic" in first["reason_codes"]
        assert "fts_intent_scan" in first["sources"]

        payload = json.loads(result.candidates_json_path.read_text(encoding="utf-8"))
        assert payload["candidates"][0]["telegram_message_id"] == 1


def _message(message_id: int, text: str | None) -> TelegramMessage:
    return TelegramMessage(
        monitored_source_ref="https://t.me/chat_mila_kolpakova",
        telegram_message_id=message_id,
        message_date=datetime(2026, 1, 31, 10, 15, message_id, tzinfo=UTC),
        sender_id=f"user-{message_id}",
        sender_display=f"User {message_id}",
        text=text,
        caption=None,
        has_media=False,
        media_metadata_json=None,
        reply_to_message_id=None,
        thread_id=None,
        forward_metadata_json=None,
        raw_metadata_json={},
    )
