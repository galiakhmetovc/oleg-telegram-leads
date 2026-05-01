"""Telegram normalized text embedding into Chroma."""

from datetime import UTC, datetime

from sqlalchemy import select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.integrations.telegram.types import ResolvedTelegramSource, TelegramMessage
from pur_leads.models.telegram_sources import telegram_raw_export_runs_table
from pur_leads.services.telegram_chroma_index import TelegramChromaIndexService
from pur_leads.services.telegram_raw_export import TelegramRawExportService
from pur_leads.services.telegram_sources import TelegramSourceService
from pur_leads.services.telegram_text_normalization import TelegramTextNormalizationService


def test_telegram_chroma_index_writes_collection_summary_and_updates_metadata(tmp_path):
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
                _message(1, "Умная камера Dahua для дома и дачи"),
                _message(2, "Насос отопления и реле давления"),
                _message(3, None),
            ],
        )
        TelegramTextNormalizationService(
            session,
            processed_root=tmp_path / "processed",
        ).write_texts(export.run_id)

        service = TelegramChromaIndexService(session, chroma_root=tmp_path / "chroma")
        result = service.write_index(export.run_id, embedding_profile="local_hashing_v1")

        assert result.chroma_path.exists()
        assert result.summary_path.exists()
        assert result.collection_name == "telegram_texts"
        assert result.metrics["total_text_rows"] == 3
        assert result.metrics["indexed_documents"] == 2
        assert result.metrics["skipped_empty_text_rows"] == 1
        assert result.metrics["embedding_profile"] == "local_hashing_v1"
        assert result.metrics["embedding_dimensions"] == 384

        matches = service.query(
            chroma_path=result.chroma_path,
            collection_name=result.collection_name,
            query_text="камеру для дома",
            n_results=1,
            embedding_profile="local_hashing_v1",
        )
        assert matches[0]["metadata"]["telegram_message_id"] == 1
        assert "камера" in matches[0]["document"]

        run = (
            session.execute(
                select(telegram_raw_export_runs_table).where(
                    telegram_raw_export_runs_table.c.id == export.run_id
                )
            )
            .mappings()
            .one()
        )
        metadata = run["metadata_json"]["chroma_index"]
        assert metadata["chroma_path"] == str(result.chroma_path)
        assert metadata["collection_name"] == "telegram_texts"
        assert metadata["indexed_documents"] == 2


def test_telegram_chroma_index_streams_text_parquet_batches(tmp_path, monkeypatch):
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
                _message(1, "Нужна камера Dahua"),
                _message(2, "Нужен видеодомофон"),
            ],
        )
        TelegramTextNormalizationService(
            session,
            processed_root=tmp_path / "processed",
        ).write_texts(export.run_id)

        original_parquet_file = TelegramChromaIndexService.__module__
        import pur_leads.services.telegram_chroma_index as chroma_module

        real_parquet_file = chroma_module.pq.ParquetFile

        class NoReadParquetFile:
            def __init__(self, *args, **kwargs):
                self._inner = real_parquet_file(*args, **kwargs)

            def read(self):
                raise AssertionError("Chroma index must stream parquet batches")

            def iter_batches(self, *args, **kwargs):
                return self._inner.iter_batches(*args, **kwargs)

        assert original_parquet_file == "pur_leads.services.telegram_chroma_index"
        monkeypatch.setattr(chroma_module.pq, "ParquetFile", NoReadParquetFile)

        result = TelegramChromaIndexService(
            session,
            chroma_root=tmp_path / "chroma",
        ).write_index(export.run_id, embedding_profile="local_hashing_v1", batch_size=1)

        assert result.metrics["indexed_documents"] == 2


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
