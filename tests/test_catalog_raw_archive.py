"""Catalog raw ingest parquet archive behavior."""

from datetime import UTC, datetime
import json

import pytest
from sqlalchemy import insert, select

from pur_leads.core.time import utc_now
from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.telegram_sources import source_messages_table
from pur_leads.services.catalog_raw_archive import CatalogRawArchiveService
from pur_leads.services.catalog_sources import CatalogSourceService
from pur_leads.services.telegram_sources import TelegramSourceService


@pytest.fixture
def runtime_session(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        yield session


def test_catalog_raw_archive_writes_stage0_parquet_and_marks_messages(
    runtime_session,
    tmp_path,
):
    telegram_source = TelegramSourceService(runtime_session).create_draft(
        "https://t.me/purmaster",
        added_by="admin",
        purpose="catalog_ingestion",
        start_mode="from_beginning",
    )
    catalog_sources = CatalogSourceService(runtime_session)
    raw_source = catalog_sources.upsert_source(
        source_type="telegram_message",
        origin="telegram:purmaster",
        external_id="42",
        raw_text="Каталог ПУР: Dahua Hero A1",
        url="https://t.me/purmaster/42",
        title="PUR message 42",
        author="Олег",
        published_at=datetime(2026, 1, 31, 12, 0, tzinfo=UTC),
        fetched_at=datetime(2026, 1, 31, 12, 5, tzinfo=UTC),
        metadata_json={"telegram_message_id": 42, "media_metadata": {"mime_type": "pdf"}},
    )
    artifact = catalog_sources.record_artifact(
        raw_source.id,
        artifact_type="document",
        file_name="catalog.pdf",
        mime_type="application/pdf",
        file_size=1024,
        sha256="a" * 64,
        local_path="/tmp/catalog.pdf",
        download_status="downloaded",
    )
    chunks = catalog_sources.replace_parsed_chunks(
        raw_source.id,
        artifact_id=artifact.id,
        chunks=["Dahua Hero A1", "Умный дом ПУР"],
        parser_name="pdf-text",
        parser_version="1",
    )
    now = utc_now()
    runtime_session.execute(
        insert(source_messages_table).values(
            id="message-1",
            monitored_source_id=telegram_source.id,
            raw_source_id=raw_source.id,
            telegram_message_id=42,
            sender_id="oleg",
            message_date=datetime(2026, 1, 31, 12, 0, tzinfo=UTC),
            text="Каталог ПУР: Dahua Hero A1",
            caption=None,
            normalized_text="каталог пур: dahua hero a1",
            has_media=True,
            media_metadata_json={"mime_type": "application/pdf", "file_name": "catalog.pdf"},
            reply_to_message_id=None,
            thread_id=None,
            forward_metadata_json=None,
            raw_metadata_json={"raw": {"id": 42}},
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
    runtime_session.commit()

    result = CatalogRawArchiveService(
        runtime_session,
        archive_root=tmp_path / "archive",
    ).write_stage0_archive(monitored_source_id=telegram_source.id)

    assert result.row_counts == {
        "monitored_sources": 1,
        "source_messages": 1,
        "sources": 1,
        "artifacts": 1,
        "parsed_chunks": 2,
    }
    assert set(result.files) == set(result.row_counts)
    assert (result.output_dir / "manifest.json").exists()
    for file_path in result.files.values():
        assert file_path.exists()
        assert file_path.suffix == ".parquet"

    import pyarrow.parquet as pq

    message_rows = pq.read_table(result.files["source_messages"]).to_pylist()
    assert message_rows[0]["telegram_message_id"] == 42
    assert json.loads(message_rows[0]["raw_metadata_json"]) == {"raw": {"id": 42}}

    chunk_rows = pq.read_table(result.files["parsed_chunks"]).to_pylist()
    assert [row["id"] for row in chunk_rows] == [chunk.id for chunk in chunks]
    assert [row["text"] for row in chunk_rows] == ["Dahua Hero A1", "Умный дом ПУР"]

    stored_message = runtime_session.execute(
        select(source_messages_table.c.archive_pointer_id).where(
            source_messages_table.c.id == "message-1"
        )
    ).scalar_one()
    assert stored_message == result.run_id
