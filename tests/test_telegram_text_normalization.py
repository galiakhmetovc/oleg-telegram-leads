"""Telegram Stage 2 text normalization behavior."""

from datetime import UTC, datetime
import json

import pyarrow.parquet as pq
from sqlalchemy import select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.integrations.telegram.types import ResolvedTelegramSource, TelegramMessage
from pur_leads.models.telegram_sources import telegram_raw_export_runs_table
from pur_leads.services.telegram_raw_export import TelegramRawExportService
from pur_leads.services.telegram_sources import TelegramSourceService
from pur_leads.services.telegram_text_normalization import TelegramTextNormalizationService


def test_telegram_text_normalization_writes_parquet_summary_and_updates_metadata(tmp_path):
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
                _message(
                    1,
                    text="Умный дом и Wi-Fi камера https://example.com/catalog",
                ),
                _message(
                    2,
                    text=None,
                    caption="Smart home camera setup",
                ),
                _message(3, text=None),
            ],
        )

        result = TelegramTextNormalizationService(
            session,
            processed_root=tmp_path / "processed",
        ).write_texts(export.run_id)

        assert result.texts_parquet_path.exists()
        assert result.summary_path.exists()
        assert result.texts_parquet_path.parent == (
            tmp_path
            / "processed"
            / "telegram_texts"
            / f"source_id={source.id}"
            / f"run_id={export.run_id}"
        )

        rows = pq.ParquetFile(result.texts_parquet_path).read().to_pylist()
        assert len(rows) == 3
        first = rows[0]
        assert first["raw_text"] == "Умный дом и Wi-Fi камера https://example.com/catalog"
        assert first["clean_text"] == "умный дом и wi-fi камера [URL]"
        assert first["normalization_lang"] in {"ru", "mixed"}
        assert first["normalization_status"] == "normalized"
        tokens = json.loads(first["tokens_json"])
        lemmas = json.loads(first["lemmas_json"])
        pos_tags = json.loads(first["pos_tags_json"])
        token_map = json.loads(first["token_map_json"])
        assert "умный" in tokens
        assert "камера" in tokens
        assert len(tokens) == len(lemmas) == len(pos_tags) == len(token_map)
        assert all({"token", "lemma", "pos"} <= set(item) for item in token_map)

        empty = rows[2]
        assert empty["raw_text"] == ""
        assert empty["clean_text"] == ""
        assert empty["normalization_lang"] == "unknown"
        assert empty["normalization_status"] == "empty_text"
        assert json.loads(empty["tokens_json"]) == []
        assert json.loads(empty["pos_tags_json"]) == []

        summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
        assert summary["stage"] == "telegram_text_normalization"
        assert summary["input"]["raw_export_run_id"] == export.run_id
        assert summary["outputs"]["texts_parquet_path"] == str(result.texts_parquet_path)
        assert summary["metrics"]["total_messages"] == 3
        assert summary["metrics"]["rows_with_text"] == 2
        assert summary["metrics"]["empty_text_rows"] == 1
        assert summary["metrics"]["tokenizer_error_rows"] == 0
        assert summary["metrics"]["total_tokens"] >= len(tokens)
        assert summary["validation_sample"]

        run = (
            session.execute(
                select(telegram_raw_export_runs_table).where(
                    telegram_raw_export_runs_table.c.id == export.run_id
                )
            )
            .mappings()
            .one()
        )
        metadata = run["metadata_json"]["text_normalization"]
        assert metadata["texts_parquet_path"] == str(result.texts_parquet_path)
        assert metadata["summary_path"] == str(result.summary_path)
        assert metadata["total_messages"] == 3


def _message(
    message_id: int,
    *,
    text: str | None,
    caption: str | None = None,
) -> TelegramMessage:
    return TelegramMessage(
        monitored_source_ref="https://t.me/purmaster",
        telegram_message_id=message_id,
        message_date=datetime(2026, 1, 31, 10, 15, message_id, tzinfo=UTC),
        sender_id="channel-1",
        sender_display="ПУР",
        text=text,
        caption=caption,
        has_media=False,
        media_metadata_json=None,
        reply_to_message_id=None,
        thread_id=None,
        forward_metadata_json=None,
        raw_metadata_json={},
    )
