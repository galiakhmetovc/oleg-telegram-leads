"""Unified Telegram FTS + Chroma search/RAG context."""

from datetime import UTC, datetime

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.integrations.telegram.types import ResolvedTelegramSource, TelegramMessage
from pur_leads.services.telegram_chroma_index import TelegramChromaIndexService
from pur_leads.services.telegram_fts_index import TelegramFtsIndexService
from pur_leads.services.telegram_raw_export import TelegramRawExportService
from pur_leads.services.telegram_search import TelegramSearchService
from pur_leads.services.telegram_sources import TelegramSourceService
from pur_leads.services.telegram_text_normalization import TelegramTextNormalizationService


def test_telegram_search_merges_fts_chroma_and_groups_thread_context(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        source = TelegramSourceService(session).create_draft(
            "https://t.me/purmaster",
            added_by="admin",
            purpose="catalog_ingestion",
            start_mode="from_beginning",
        )
        export = TelegramRawExportService(session, raw_root=tmp_path / "raw").write_export(
            source=source,
            resolved_source=ResolvedTelegramSource(
                input_ref="https://t.me/purmaster",
                source_kind="telegram_channel",
                telegram_id="-10042",
                username="purmaster",
                title="ПУР",
            ),
            messages=[
                _message(1, "Ищу камеру для дома"),
                _message(2, "Dahua Hero A1 Wi-Fi камера подходит для дома", reply_to=1),
                _message(3, "Насос отопления и реле давления"),
            ],
        )
        TelegramTextNormalizationService(
            session,
            processed_root=tmp_path / "processed",
        ).write_texts(export.run_id)
        TelegramFtsIndexService(session, search_root=tmp_path / "search").write_index(export.run_id)
        TelegramChromaIndexService(session, chroma_root=tmp_path / "chroma").write_index(
            export.run_id,
            embedding_profile="local_hashing_v1",
        )

        payload = TelegramSearchService(
            session,
            search_root=tmp_path / "search",
            chroma_root=tmp_path / "chroma",
        ).query(
            export.run_id,
            query_text="камеру dahua для дома",
            limit=5,
            embedding_profile="local_hashing_v1",
        )

        result_ids = [item["telegram_message_id"] for item in payload["results"]]
        assert 2 in result_ids
        dahua = next(item for item in payload["results"] if item["telegram_message_id"] == 2)
        assert dahua["message_url"] == "https://t.me/purmaster/2"
        assert dahua["thread_key"] == "1"
        assert dahua["sources"][0] == "fts"
        assert "chroma" in dahua["sources"]

        group = next(item for item in payload["groups"] if item["thread_key"] == "1")
        assert {item["telegram_message_id"] for item in group["items"]} >= {1, 2}
        assert group["top_message_url"] in {
            "https://t.me/purmaster/1",
            "https://t.me/purmaster/2",
        }

        assert payload["rag_context"][0]["citation"] == "[1]"
        assert payload["rag_context"][0]["message_url"].startswith("https://t.me/purmaster/")
        assert payload["metrics"]["fts_hits"] >= 1
        assert payload["metrics"]["chroma_hits"] >= 1
        assert payload["metrics"]["merged_results"] == len(payload["results"])
        assert payload["metrics"]["thread_groups"] == len(payload["groups"])


def _message(message_id: int, text: str, *, reply_to: int | None = None) -> TelegramMessage:
    return TelegramMessage(
        monitored_source_ref="https://t.me/purmaster",
        telegram_message_id=message_id,
        message_date=datetime(2026, 1, 31, 10, 15, message_id, tzinfo=UTC),
        sender_id="channel-1",
        sender_display="ПУР",
        text=text,
        caption=None,
        has_media=False,
        media_metadata_json=None,
        reply_to_message_id=reply_to,
        thread_id=None,
        forward_metadata_json=None,
        raw_metadata_json={},
    )
