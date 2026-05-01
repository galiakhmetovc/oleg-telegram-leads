"""CLI behavior for raw archive commands."""

from datetime import UTC, datetime
import json

from sqlalchemy import insert

from pur_leads.cli import main
from pur_leads.core.time import utc_now
from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.telegram_sources import source_messages_table
from pur_leads.services.catalog_sources import CatalogSourceService
from pur_leads.services.telegram_sources import TelegramSourceService


def test_cli_archive_catalog_raw_writes_parquet_and_prints_result(tmp_path, capsys):
    db_path = tmp_path / "test.db"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        telegram_source = TelegramSourceService(session).create_draft(
            "https://t.me/purmaster",
            added_by="admin",
            purpose="catalog_ingestion",
            start_mode="from_beginning",
        )
        raw_source = CatalogSourceService(session).upsert_source(
            source_type="telegram_message",
            origin="telegram:purmaster",
            external_id="7",
            raw_text="ПУР каталог",
        )
        now = utc_now()
        session.execute(
            insert(source_messages_table).values(
                id="message-cli-1",
                monitored_source_id=telegram_source.id,
                raw_source_id=raw_source.id,
                telegram_message_id=7,
                sender_id=None,
                message_date=datetime(2026, 1, 1, tzinfo=UTC),
                text="ПУР каталог",
                caption=None,
                normalized_text="пур каталог",
                has_media=False,
                media_metadata_json=None,
                reply_to_message_id=None,
                thread_id=None,
                forward_metadata_json=None,
                raw_metadata_json=None,
                fetched_at=now,
                classification_status="unclassified",
                archive_pointer_id=None,
                is_archived_stub=False,
                text_archived=False,
                caption_archived=False,
                metadata_archived=False,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    main(
        [
            "--database-path",
            str(db_path),
            "archive",
            "catalog-raw",
            "--archive-root",
            str(tmp_path / "archive"),
            "--monitored-source-id",
            telegram_source.id,
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["row_counts"]["source_messages"] == 1
    assert payload["row_counts"]["sources"] == 1
    assert payload["files"]["source_messages"].endswith("source_messages.parquet")
