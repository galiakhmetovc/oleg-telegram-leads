"""SQLite FTS5 index for normalized Telegram text."""

from datetime import UTC, datetime

from sqlalchemy import select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.integrations.telegram.types import ResolvedTelegramSource, TelegramMessage
from pur_leads.models.telegram_sources import telegram_raw_export_runs_table
from pur_leads.services.telegram_fts_index import TelegramFtsIndexService
from pur_leads.services.telegram_raw_export import TelegramRawExportService
from pur_leads.services.telegram_sources import TelegramSourceService
from pur_leads.services.telegram_text_normalization import TelegramTextNormalizationService


def test_telegram_fts_index_matches_russian_stemmed_query_and_updates_metadata(tmp_path):
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
                _message(1, "Отдаю безмешковый пылесос, самовывоз"),
                _message(2, "Аренда машиноместа, парковка, аренда"),
                _message(3, None),
            ],
        )
        TelegramTextNormalizationService(
            session,
            processed_root=tmp_path / "processed",
        ).write_texts(export.run_id)

        service = TelegramFtsIndexService(session, search_root=tmp_path / "search")
        result = service.write_index(export.run_id)

        assert result.search_db_path.exists()
        assert result.summary_path.exists()
        assert result.metrics["indexed_documents"] == 2
        assert result.metrics["skipped_empty_text_rows"] == 1

        matches = service.query(
            search_db_path=result.search_db_path,
            query_text="кто отдавал пылесоса",
            limit=5,
        )
        assert matches[0]["telegram_message_id"] == 1
        assert "пылесос" in matches[0]["clean_text"]
        assert matches[0]["rarity_score"] > 0
        assert matches[0]["score"] > 0

        run = (
            session.execute(
                select(telegram_raw_export_runs_table).where(
                    telegram_raw_export_runs_table.c.id == export.run_id
                )
            )
            .mappings()
            .one()
        )
        metadata = run["metadata_json"]["fts_index"]
        assert metadata["search_db_path"] == str(result.search_db_path)
        assert metadata["indexed_documents"] == 2


def _message(message_id: int, text: str | None) -> TelegramMessage:
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
        reply_to_message_id=None,
        thread_id=None,
        forward_metadata_json=None,
        raw_metadata_json={},
    )
