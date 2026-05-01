"""Telegram raw export EDA / data quality behavior."""

from datetime import UTC, datetime, timedelta
import json

from sqlalchemy import select

from pur_leads.core.time import utc_now
from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.integrations.telegram.types import ResolvedTelegramSource, TelegramMessage
from pur_leads.models.telegram_sources import telegram_raw_export_runs_table
from pur_leads.services.telegram_eda import TelegramEdaService, _analyze_rows
from pur_leads.services.telegram_raw_export import TelegramRawExportService
from pur_leads.services.telegram_sources import TelegramSourceService


def test_telegram_eda_writes_summary_report_and_updates_run_metadata(tmp_path):
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
        resolved = ResolvedTelegramSource(
            input_ref="https://t.me/purmaster",
            source_kind="telegram_channel",
            telegram_id="-10042",
            username="purmaster",
            title="ПУР",
        )
        future = utc_now() + timedelta(days=1)
        export = TelegramRawExportService(session, raw_root=tmp_path / "raw").write_export(
            source=source,
            resolved_source=resolved,
            messages=[
                _message(
                    1,
                    sender_id="channel-1",
                    text="Каталог https://example.com test@example.com",
                    raw_metadata={"telethon": {"reactions": {"results": [{"count": 2}]}}},
                ),
                _message(
                    1,
                    sender_id="channel-1",
                    text=None,
                    caption="PDF +7 999 123-45-67",
                    media_metadata={
                        "type": "MessageMediaDocument",
                        "document": {
                            "file_name": "catalog.pdf",
                            "mime_type": "application/pdf",
                            "file_size": 7,
                            "downloadable": True,
                        },
                    },
                ),
                _message(2, sender_id="channel-1", text=None, message_date=future),
            ],
        )

        summary = TelegramEdaService(session).write_summary(export.run_id)

        assert summary.report_path == export.output_dir / "reports" / "eda_summary.json"
        payload = json.loads(summary.report_path.read_text(encoding="utf-8"))
        assert payload["stage"] == "telegram_eda"
        assert payload["input"]["raw_export_run_id"] == export.run_id
        assert payload["metrics"]["total_messages"] == 3
        assert payload["metrics"]["unique_authors"] == 1
        assert payload["metrics"]["has_text_ratio"] == 2 / 3
        assert payload["metrics"]["has_url_ratio"] == 1 / 3
        assert payload["metrics"]["has_reactions_ratio"] == 1 / 3
        assert payload["metrics"]["pii_ratio"] == 2 / 3
        assert payload["metrics"]["message_type_distribution"] == {
            "media": 1,
            "other": 1,
            "text": 1,
        }
        assert payload["anomalies"]["duplicate_message_ids"] == [1]
        assert payload["anomalies"]["future_dates_count"] == 1
        assert {warning["code"] for warning in payload["warnings"]} == {
            "single_author_not_dialogue",
            "duplicate_message_ids",
            "future_dates",
            "pii_detected",
        }
        assert payload["recommended_decision"] == "go_with_warnings"

        run = (
            session.execute(
                select(telegram_raw_export_runs_table).where(
                    telegram_raw_export_runs_table.c.id == export.run_id
                )
            )
            .mappings()
            .one()
        )
        assert run["metadata_json"]["eda"]["report_path"] == str(summary.report_path)
        assert run["metadata_json"]["eda"]["recommended_decision"] == "go_with_warnings"


def test_telegram_eda_counts_desktop_service_messages_and_reactions():
    metrics, anomalies = _analyze_rows(
        [
            {
                "telegram_message_id": 1,
                "sender_id": None,
                "sender_display": None,
                "date": "2026-04-30T10:00:00",
                "text_plain": "",
                "caption": None,
                "media_type": None,
                "mime_type": None,
                "reply_to_message_id": None,
                "raw_message_json": json.dumps(
                    {"raw_tdesktop_json": {"id": 1, "type": "service"}},
                    ensure_ascii=False,
                ),
            },
            {
                "telegram_message_id": 2,
                "sender_id": "user1",
                "sender_display": "Анна",
                "date": "2026-04-30T10:01:00",
                "text_plain": "Нужна камера",
                "caption": None,
                "media_type": None,
                "mime_type": None,
                "reply_to_message_id": 1,
                "raw_message_json": json.dumps(
                    {
                        "raw_tdesktop_json": {
                            "id": 2,
                            "type": "message",
                            "reactions": [{"type": "emoji", "count": 1}],
                        }
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        datetime(2026, 5, 1, tzinfo=UTC),
    )

    assert anomalies["duplicate_message_count"] == 0
    assert metrics["total_messages"] == 2
    assert metrics["service_message_ratio"] == 0.5
    assert metrics["has_reactions_ratio"] == 0.5
    assert metrics["message_type_distribution"] == {"service": 1, "text": 1}


def _message(
    message_id: int,
    *,
    sender_id: str,
    text: str | None,
    caption: str | None = None,
    media_metadata: dict | None = None,
    raw_metadata: dict | None = None,
    message_date: datetime | None = None,
) -> TelegramMessage:
    return TelegramMessage(
        monitored_source_ref="https://t.me/purmaster",
        telegram_message_id=message_id,
        message_date=message_date or datetime(2026, 1, 31, 10, 15, message_id, tzinfo=UTC),
        sender_id=sender_id,
        sender_display="ПУР",
        text=text,
        caption=caption,
        has_media=media_metadata is not None,
        media_metadata_json=media_metadata,
        reply_to_message_id=None,
        thread_id=None,
        forward_metadata_json=None,
        raw_metadata_json=raw_metadata or {},
    )
