"""Telegram Desktop archive import behavior."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import zipfile

import pyarrow.parquet as pq
from sqlalchemy import func, select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.telegram_sources import source_messages_table, telegram_raw_export_runs_table
from pur_leads.services.telegram_desktop_import import TelegramDesktopArchiveImportService


def test_telegram_desktop_archive_import_writes_raw_export_and_source_messages(tmp_path):
    archive_path = _write_desktop_archive(tmp_path)
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        result = TelegramDesktopArchiveImportService(
            session,
            raw_root=tmp_path / "raw",
        ).import_archive(
            archive_path,
            input_ref="https://t.me/chat_mila_kolpakova",
            purpose="lead_monitoring",
            added_by="test",
            sync_source_messages=True,
        )

        assert result.message_count == 3
        assert result.attachment_count == 1
        assert result.created_source_messages == 2
        assert result.raw_export.messages_parquet_path.exists()
        assert result.raw_export.attachments_parquet_path.exists()

        message_rows = pq.read_table(result.raw_export.messages_parquet_path).to_pylist()
        assert [row["telegram_message_id"] for row in message_rows] == [1, 2, 3]
        assert message_rows[1]["text_plain"] == "Нужна камера Dahua A1"
        assert message_rows[1]["message_url"] == "https://t.me/chat_mila_kolpakova/2"
        assert json.loads(message_rows[1]["raw_message_json"])["raw_tdesktop_json"]["id"] == 2

        attachment_rows = pq.read_table(result.raw_export.attachments_parquet_path).to_pylist()
        assert attachment_rows[0]["telegram_message_id"] == 3
        assert attachment_rows[0]["file_name"] == "photo.jpg"
        assert attachment_rows[0]["downloadable"] is False

        source_rows = session.execute(
            select(source_messages_table).order_by(source_messages_table.c.telegram_message_id)
        ).mappings().all()
        assert len(source_rows) == 2
        assert source_rows[0]["telegram_message_id"] == 2
        assert source_rows[0]["text"] == "Нужна камера Dahua A1"
        assert source_rows[0]["message_date"].replace(tzinfo=UTC) == datetime(
            2026, 4, 30, 10, 0, tzinfo=UTC
        )
        assert source_rows[0]["classification_status"] == "unclassified"
        assert source_rows[0]["archive_pointer_id"] == result.raw_export.run_id

        run = session.execute(select(telegram_raw_export_runs_table)).mappings().one()
        assert run["export_format"] == "telegram_desktop_json_v1"
        assert run["message_count"] == 3
        assert run["metadata_json"]["desktop_import"]["archive_name"] == archive_path.name
        assert (
            session.execute(select(func.count()).select_from(source_messages_table)).scalar_one()
            == 2
        )


def _write_desktop_archive(tmp_path):
    archive_path = tmp_path / "ChatExport.zip"
    payload = {
        "name": "Чат лидов",
        "type": "public_supergroup",
        "id": 1292716582,
        "messages": [
            {
                "id": 1,
                "type": "service",
                "date": "2026-04-30T12:59:00",
                "date_unixtime": "1777543140",
                "text": "",
                "text_entities": [],
            },
            {
                "id": 2,
                "type": "message",
                "date": "2026-04-30T13:00:00",
                "date_unixtime": "1777543200",
                "from": "Анна",
                "from_id": "user1",
                "text": [
                    {"type": "plain", "text": "Нужна камера "},
                    {"type": "bold", "text": "Dahua A1"},
                ],
                "text_entities": [],
            },
            {
                "id": 3,
                "type": "message",
                "date": "2026-04-30T13:01:00",
                "date_unixtime": "1777543260",
                "from": "Анна",
                "from_id": "user1",
                "reply_to_message_id": 2,
                "photo": "(File not included. Change data exporting settings to download.)",
                "photo_file_size": 1234,
                "width": 100,
                "height": 100,
                "text": "Фото помещения",
                "text_entities": [],
            },
        ],
    }
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "ChatExport_2026-04-30/result.json",
            json.dumps(payload, ensure_ascii=False),
        )
    return archive_path
