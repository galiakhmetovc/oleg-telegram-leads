"""Telegram external page/document text extraction behavior."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import asyncio

import pyarrow.parquet as pq
from sqlalchemy import select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.integrations.catalog.external_page import FetchedExternalPage
from pur_leads.integrations.documents.pdf_parser import PdfArtifactParser
from pur_leads.integrations.telegram.types import ResolvedTelegramSource, TelegramMessage
from pur_leads.models.telegram_sources import telegram_raw_export_runs_table
from pur_leads.services.telegram_artifact_texts import TelegramArtifactTextExtractionService
from pur_leads.services.telegram_chroma_index import TelegramChromaIndexService
from pur_leads.services.telegram_fts_index import TelegramFtsIndexService
from pur_leads.services.telegram_raw_export import TelegramRawExportService
from pur_leads.services.telegram_search import TelegramSearchService
from pur_leads.services.telegram_sources import TelegramSourceService
from pur_leads.services.telegram_text_normalization import TelegramTextNormalizationService
from pur_leads.workers.runtime import ParsedArtifact


def test_telegram_artifact_texts_writes_parquet_summary_and_updates_metadata(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        export = _write_export_with_page_and_document(session, tmp_path)

        result = TelegramArtifactTextExtractionService(
            session,
            processed_root=tmp_path / "processed",
            external_page_fetcher=FakeExternalPageFetcher(
                {
                    "https://telegra.ph/pur-home": FetchedExternalPage(
                        url="https://telegra.ph/pur-home",
                        final_url="https://telegra.ph/pur-home",
                        title="ПУР умный дом",
                        text="Инженерный умный дом: автоматы, реле, счетчики и защита протечки.",
                        status_code=200,
                        content_type="text/html",
                    )
                }
            ),
            document_parser=PdfArtifactParser(reader_factory=lambda path: FakeReader([])),
        ).write_texts(export.run_id)

        assert result.texts_parquet_path.exists()
        assert result.summary_path.exists()

        rows = pq.read_table(result.texts_parquet_path).to_pylist()
        assert {row["artifact_kind"] for row in rows} == {"external_page", "document"}
        assert all(row["export_run_id"] == export.run_id for row in rows)
        assert all(row["telegram_message_id"] == 10 for row in rows)
        assert all(row["message_url"] == "https://t.me/purmaster/10" for row in rows)
        assert all(row["extraction_status"] == "extracted" for row in rows)

        page = next(row for row in rows if row["artifact_kind"] == "external_page")
        assert page["source_url"] == "https://telegra.ph/pur-home"
        assert page["final_url"] == "https://telegra.ph/pur-home"
        assert page["title"] == "ПУР умный дом"
        assert "защита протечки" in page["clean_text"]
        assert json.loads(page["tokens_json"])
        assert len(json.loads(page["tokens_json"])) == len(json.loads(page["pos_tags_json"]))

        document = next(row for row in rows if row["artifact_kind"] == "document")
        assert document["file_name"] == "catalog.txt"
        assert document["date"] == "2026-01-31T10:15:00+00:00"
        assert "датчики протечки" in document["clean_text"]
        assert document["parser_name"] == "plain-text"

        summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
        assert summary["metrics"]["candidate_external_urls"] == 1
        assert summary["metrics"]["candidate_documents"] == 1
        assert summary["metrics"]["extracted_rows"] == 2
        assert summary["metrics"]["rows_with_text"] == 2

        run = (
            session.execute(
                select(telegram_raw_export_runs_table).where(
                    telegram_raw_export_runs_table.c.id == export.run_id
                )
            )
            .mappings()
            .one()
        )
        metadata = run["metadata_json"]["artifact_texts"]
        assert metadata["texts_parquet_path"] == str(result.texts_parquet_path)
        assert metadata["summary_path"] == str(result.summary_path)
        assert metadata["extracted_rows"] == 2


def test_search_indexes_artifact_texts_alongside_message_texts(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        export = _write_export_with_page_and_document(session, tmp_path)
        TelegramTextNormalizationService(
            session,
            processed_root=tmp_path / "processed",
        ).write_texts(export.run_id)
        TelegramArtifactTextExtractionService(
            session,
            processed_root=tmp_path / "processed",
            external_page_fetcher=FakeExternalPageFetcher({}),
            document_parser=PdfArtifactParser(reader_factory=lambda path: FakeReader([])),
            fetch_external_pages=False,
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
            query_text="датчики протечки",
            limit=5,
            embedding_profile="local_hashing_v1",
        )

        assert payload["metrics"]["artifact_results"] >= 1
        artifact = next(item for item in payload["results"] if item["entity_type"] == "telegram_artifact")
        assert artifact["artifact_kind"] == "document"
        assert artifact["file_name"] == "catalog.txt"
        assert artifact["telegram_message_id"] == 10
        assert artifact["message_url"] == "https://t.me/purmaster/10"
        assert "датчики протечки" in artifact["clean_text"]
        assert payload["rag_context"][0]["entity_type"] in {"telegram_message", "telegram_artifact"}


def test_artifact_text_extraction_runs_external_pages_and_documents_concurrently(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        export = _write_export_with_many_pages_and_documents(session, tmp_path)
        page_fetcher = DelayedExternalPageFetcher()
        document_parser = DelayedDocumentParser()

        result = TelegramArtifactTextExtractionService(
            session,
            processed_root=tmp_path / "processed",
            external_page_fetcher=page_fetcher,
            document_parser=document_parser,
            external_fetch_concurrency=3,
            document_parse_concurrency=2,
            external_fetch_timeout_seconds=5,
            document_parse_timeout_seconds=5,
        ).write_texts(export.run_id)

        rows = pq.read_table(result.texts_parquet_path).to_pylist()
        assert len(rows) == 6
        assert page_fetcher.max_active >= 2
        assert document_parser.max_active >= 2
        assert result.metrics["external_fetch_concurrency"] == 3
        assert result.metrics["document_parse_concurrency"] == 2


def test_external_page_timeout_marks_failed_row_without_stopping_run(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        export = _write_export_with_many_pages_and_documents(session, tmp_path)

        result = TelegramArtifactTextExtractionService(
            session,
            processed_root=tmp_path / "processed",
            external_page_fetcher=DelayedExternalPageFetcher(delay_seconds=0.05),
            document_parser=DelayedDocumentParser(delay_seconds=0.0),
            parse_documents=False,
            external_fetch_concurrency=3,
            external_fetch_timeout_seconds=0.01,
        ).write_texts(export.run_id)

        rows = pq.read_table(result.texts_parquet_path).to_pylist()
        assert len(rows) == 3
        assert {row["extraction_status"] for row in rows} == {"failed"}
        assert all(row["artifact_kind"] == "external_page" for row in rows)
        assert result.metrics["status_distribution"]["failed"] == 3


def _write_export_with_page_and_document(session, tmp_path):
    source = TelegramSourceService(session).create_draft(
        "https://t.me/purmaster",
        added_by="admin",
        purpose="catalog_ingestion",
        start_mode="from_beginning",
    )
    document_path = tmp_path / "catalog.txt"
    document_path.write_text(
        "Каталог ПУР\n\nДатчики протечки, реле защиты и Wi-Fi камеры для квартиры.",
        encoding="utf-8",
    )
    return TelegramRawExportService(session, raw_root=tmp_path / "raw").write_export(
        source=source,
        resolved_source=ResolvedTelegramSource(
            input_ref="https://t.me/purmaster",
            source_kind="telegram_channel",
            telegram_id="-10042",
            username="purmaster",
            title="ПУР",
        ),
        messages=[
            TelegramMessage(
                monitored_source_ref="https://t.me/purmaster",
                telegram_message_id=1,
                message_date=datetime(2026, 1, 31, 10, 14, 0, tzinfo=UTC),
                sender_id="channel-1",
                sender_display="ПУР",
                text=None,
                caption=None,
                has_media=False,
                media_metadata_json=None,
                reply_to_message_id=None,
                thread_id=None,
                forward_metadata_json=None,
                raw_metadata_json={},
            ),
            TelegramMessage(
                monitored_source_ref="https://t.me/purmaster",
                telegram_message_id=10,
                message_date=datetime(2026, 1, 31, 10, 15, 0, tzinfo=UTC),
                sender_id="channel-1",
                sender_display="ПУР",
                text="Материалы по умному дому https://telegra.ph/pur-home",
                caption=None,
                has_media=True,
                media_metadata_json={
                    "type": "MessageMediaDocument",
                    "document": {
                        "file_name": "catalog.txt",
                        "mime_type": "text/plain",
                        "file_size": document_path.stat().st_size,
                        "downloadable": True,
                    },
                    "raw_export_download": {
                        "status": "downloaded",
                        "local_path": str(document_path),
                    },
                },
                reply_to_message_id=None,
                thread_id=None,
                forward_metadata_json=None,
                raw_metadata_json={},
            )
        ],
    )


def _write_export_with_many_pages_and_documents(session, tmp_path):
    source = TelegramSourceService(session).create_draft(
        "https://t.me/purmaster",
        added_by="admin",
        purpose="catalog_ingestion",
        start_mode="from_beginning",
    )
    messages = []
    for message_id in range(1, 4):
        document_path = tmp_path / f"catalog-{message_id}.txt"
        document_path.write_text(f"Документ {message_id}: датчики и камеры", encoding="utf-8")
        messages.append(
            TelegramMessage(
                monitored_source_ref="https://t.me/purmaster",
                telegram_message_id=message_id,
                message_date=datetime(2026, 1, 31, 10, 15, message_id, tzinfo=UTC),
                sender_id="channel-1",
                sender_display="ПУР",
                text=f"Материал {message_id} https://example.com/page-{message_id}",
                caption=None,
                has_media=True,
                media_metadata_json={
                    "type": "MessageMediaDocument",
                    "document": {
                        "file_name": document_path.name,
                        "mime_type": "text/plain",
                        "file_size": document_path.stat().st_size,
                        "downloadable": True,
                    },
                    "raw_export_download": {
                        "status": "downloaded",
                        "local_path": str(document_path),
                    },
                },
                reply_to_message_id=None,
                thread_id=None,
                forward_metadata_json=None,
                raw_metadata_json={},
            )
        )
    return TelegramRawExportService(session, raw_root=tmp_path / "raw").write_export(
        source=source,
        resolved_source=ResolvedTelegramSource(
            input_ref="https://t.me/purmaster",
            source_kind="telegram_channel",
            telegram_id="-10042",
            username="purmaster",
            title="ПУР",
        ),
        messages=messages,
    )


class FakeExternalPageFetcher:
    def __init__(self, pages: dict[str, FetchedExternalPage]) -> None:
        self.pages = pages

    async def fetch_page(self, *, url: str, payload: dict[str, object]) -> FetchedExternalPage:
        if url not in self.pages:
            raise ValueError(f"unexpected url: {url}")
        return self.pages[url]


class DelayedExternalPageFetcher:
    def __init__(self, *, delay_seconds: float = 0.02) -> None:
        self.delay_seconds = delay_seconds
        self.active = 0
        self.max_active = 0

    async def fetch_page(self, *, url: str, payload: dict[str, object]) -> FetchedExternalPage:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(self.delay_seconds)
            return FetchedExternalPage(
                url=url,
                final_url=url,
                title=url.rsplit("/", 1)[-1],
                text=f"Страница {url}: умный дом, реле, датчики",
                status_code=200,
                content_type="text/html",
            )
        finally:
            self.active -= 1


class DelayedDocumentParser:
    def __init__(self, *, delay_seconds: float = 0.02) -> None:
        self.delay_seconds = delay_seconds
        self.active = 0
        self.max_active = 0

    async def parse_artifact(
        self,
        *,
        source_id: str,
        artifact_id: str | None,
        payload: dict[str, object],
    ) -> ParsedArtifact:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(self.delay_seconds)
            return ParsedArtifact(
                source_id=source_id,
                artifact_id=artifact_id,
                chunks=["Документ: датчики протечки, камеры и реле"],
                parser_name="delayed-test",
                parser_version="1",
            )
        finally:
            self.active -= 1


class FakeReader:
    def __init__(self, pages):
        self.pages = pages
