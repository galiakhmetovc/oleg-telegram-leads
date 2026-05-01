"""Telegram raw export JSON/parquet behavior."""

from datetime import UTC, datetime
import json

import pyarrow.parquet as pq
import pytest
from sqlalchemy import select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.integrations.telegram.types import ResolvedTelegramSource, TelegramMessage
from pur_leads.models.telegram_sources import telegram_raw_export_runs_table
from pur_leads.services.telegram_raw_export import TelegramRawExportService
from pur_leads.services.telegram_sources import TelegramSourceService


@pytest.fixture
def raw_export_session(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        yield session


def test_telegram_raw_export_writes_json_jsonl_parquet_and_run_record(
    raw_export_session,
    tmp_path,
):
    source = TelegramSourceService(raw_export_session).create_draft(
        "https://t.me/purmaster",
        added_by="admin",
        purpose="catalog_ingestion",
        start_mode="from_beginning",
    )
    resolved = ResolvedTelegramSource(
        input_ref="https://t.me/purmaster",
        source_kind="telegram_channel",
        telegram_id="-10042",
        username="purmaster",
        title="ПУР",
    )
    messages = [
        TelegramMessage(
            monitored_source_ref="https://t.me/purmaster",
            telegram_message_id=39,
            message_date=datetime(2026, 1, 31, 10, 15, 30, tzinfo=UTC),
            sender_id="channel-10042",
            sender_display="ПУР",
            text="Каталог решений",
            caption="PDF",
            has_media=True,
            media_metadata_json={
                "type": "MessageMediaDocument",
                "document": {
                    "file_name": "catalog.pdf",
                    "mime_type": "application/pdf",
                    "file_size": 1234,
                    "downloadable": True,
                },
            },
            reply_to_message_id=None,
            thread_id=None,
            forward_metadata_json=None,
            raw_metadata_json={
                "telethon_id": 39,
                "grouped_id": None,
                "telethon": {
                    "message": {"_": "Message", "id": 39, "restriction_reason": []},
                    "sender": {"_": "Channel", "title": "ПУР"},
                    "document": {"_": "Document", "size": 1234},
                },
            },
        )
    ]

    result = TelegramRawExportService(
        raw_export_session,
        raw_root=tmp_path / "raw",
    ).write_export(source=source, resolved_source=resolved, messages=messages)

    assert result.message_count == 1
    assert result.attachment_count == 1
    assert result.result_json_path.exists()
    assert result.messages_jsonl_path.exists()
    assert result.attachments_jsonl_path.exists()
    assert result.messages_parquet_path.exists()
    assert result.attachments_parquet_path.exists()

    payload = json.loads(result.result_json_path.read_text(encoding="utf-8"))
    assert payload["name"] == "ПУР"
    assert payload["type"] == "telegram_channel"
    assert payload["messages"][0]["id"] == 39
    assert payload["messages"][0]["message_url"] == "https://t.me/purmaster/39"
    assert payload["messages"][0]["text"] == "Каталог решений"
    assert payload["messages"][0]["caption"] == "PDF"
    assert payload["messages"][0]["raw_media_json"]["telegram_media_ref"] == {
        "kind": "telegram_message_media",
        "monitored_source_id": source.id,
        "source_ref": "https://t.me/purmaster",
        "source_username": "purmaster",
        "source_telegram_id": "-10042",
        "telegram_message_id": 39,
        "message_url": "https://t.me/purmaster/39",
    }
    assert payload["messages"][0]["raw_telethon_json"] == {
        "telethon_id": 39,
        "grouped_id": None,
        "telethon": {
            "message": {"_": "Message", "id": 39, "restriction_reason": []},
            "sender": {"_": "Channel", "title": "ПУР"},
            "document": {"_": "Document", "size": 1234},
        },
    }

    jsonl_rows = [
        json.loads(line)
        for line in result.messages_jsonl_path.read_text(encoding="utf-8").splitlines()
    ]
    assert jsonl_rows == payload["messages"]

    message_rows = pq.read_table(result.messages_parquet_path).to_pylist()
    assert message_rows[0]["telegram_message_id"] == 39
    assert message_rows[0]["text_plain"] == "Каталог решений"
    assert json.loads(message_rows[0]["raw_message_json"]) == payload["messages"][0]
    assert json.loads(message_rows[0]["raw_message_json"])["raw_telethon_json"]["telethon"][
        "document"
    ] == {"_": "Document", "size": 1234}

    attachment_rows = pq.read_table(result.attachments_parquet_path).to_pylist()
    assert attachment_rows[0]["telegram_message_id"] == 39
    assert attachment_rows[0]["file_name"] == "catalog.pdf"
    assert attachment_rows[0]["mime_type"] == "application/pdf"
    assert (
        json.loads(attachment_rows[0]["raw_attachment_json"])["telegram_media_ref"]["message_url"]
        == "https://t.me/purmaster/39"
    )

    run_row = (
        raw_export_session.execute(
            select(telegram_raw_export_runs_table).where(
                telegram_raw_export_runs_table.c.id == result.run_id
            )
        )
        .mappings()
        .one()
    )
    assert run_row["status"] == "succeeded"
    assert run_row["message_count"] == 1
    assert run_row["attachment_count"] == 1
