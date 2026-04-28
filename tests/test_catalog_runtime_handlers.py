from datetime import UTC, datetime
import hashlib
from pathlib import Path

import pytest
from sqlalchemy import insert
from sqlalchemy import select

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.integrations.telegram.types import (
    MessageContext,
    ResolvedTelegramSource,
    SourceAccessResult,
    TelegramDocumentDownload,
    TelegramMessage,
)
from pur_leads.models.audit import operational_events_table
from pur_leads.models.catalog import (
    artifacts_table,
    catalog_candidates_table,
    parsed_chunks_table,
)
from pur_leads.models.scheduler import scheduler_jobs_table
from pur_leads.models.telegram_sources import source_messages_table
from pur_leads.services.catalog_sources import CatalogSourceService
from pur_leads.services.scheduler import SchedulerService
from pur_leads.services.telegram_sources import TelegramSourceService
from pur_leads.workers.runtime import (
    CatalogExtractedFact,
    ParsedArtifact,
    WorkerRuntime,
    build_catalog_handler_registry,
    build_telegram_handler_registry,
)


class FakeParser:
    async def parse_artifact(self, *, source_id: str, artifact_id: str | None, payload: dict):
        return ParsedArtifact(
            source_id=source_id,
            artifact_id=artifact_id,
            chunks=["Dahua Hero A1", "Wi-Fi camera for dacha"],
            parser_name="fake-parser",
            parser_version="1",
        )


class FakeExtractor:
    async def extract_catalog_facts(
        self, *, source_id: str | None, chunk_id: str | None, payload: dict
    ):
        return [
            CatalogExtractedFact(
                fact_type="product",
                canonical_name="Dahua Hero A1",
                value_json={"item_type": "product", "terms": ["Hero A1"]},
                confidence=0.91,
                source_id=source_id,
                chunk_id=chunk_id,
                candidate_type="item",
                evidence_quote="Dahua Hero A1",
            )
        ]


@pytest.fixture
def runtime_session(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        yield session


@pytest.mark.asyncio
async def test_parse_artifact_handler_stores_chunks(runtime_session):
    source = CatalogSourceService(runtime_session).upsert_source(
        source_type="manual_text",
        origin="manual",
        external_id="parse-source",
        raw_text="raw",
    )
    artifact = CatalogSourceService(runtime_session).record_artifact(
        source.id,
        artifact_type="document",
        file_name="catalog.pdf",
        download_status="downloaded",
    )
    job = SchedulerService(runtime_session).enqueue(
        job_type="parse_artifact",
        scope_type="parser",
        payload_json={"source_id": source.id, "artifact_id": artifact.id},
    )
    runtime = WorkerRuntime(
        runtime_session,
        handlers=build_catalog_handler_registry(runtime_session, parser=FakeParser()),
    )

    result = await runtime.run_once()

    stored = SchedulerService(runtime_session).repository.get(job.id)
    chunks = runtime_session.execute(select(parsed_chunks_table)).mappings().all()
    assert stored is not None
    assert result.status == "succeeded"
    assert stored.status == "succeeded"
    assert stored.result_summary_json == {"chunk_count": 2, "parser_name": "fake-parser"}
    assert [chunk["text"] for chunk in chunks] == ["Dahua Hero A1", "Wi-Fi camera for dacha"]
    extract_jobs = (
        runtime_session.execute(
            select(scheduler_jobs_table)
            .where(scheduler_jobs_table.c.job_type == "extract_catalog_facts")
            .order_by(scheduler_jobs_table.c.created_at)
        )
        .mappings()
        .all()
    )
    assert [job["payload_json"]["chunk_id"] for job in extract_jobs] == [
        chunk["id"] for chunk in chunks
    ]


@pytest.mark.asyncio
async def test_extract_catalog_facts_handler_creates_candidates(runtime_session):
    source = CatalogSourceService(runtime_session).upsert_source(
        source_type="manual_text",
        origin="manual",
        external_id="extract-source",
        raw_text="Dahua Hero A1",
    )
    chunk = CatalogSourceService(runtime_session).replace_parsed_chunks(
        source.id,
        chunks=["Dahua Hero A1"],
        parser_name="test",
        parser_version="1",
    )[0]
    job = SchedulerService(runtime_session).enqueue(
        job_type="extract_catalog_facts",
        scope_type="parser",
        payload_json={"source_id": source.id, "chunk_id": chunk.id},
    )
    runtime = WorkerRuntime(
        runtime_session,
        handlers=build_catalog_handler_registry(runtime_session, extractor=FakeExtractor()),
    )

    result = await runtime.run_once()

    stored = SchedulerService(runtime_session).repository.get(job.id)
    candidates = runtime_session.execute(select(catalog_candidates_table)).mappings().all()
    assert stored is not None
    assert result.status == "succeeded"
    assert stored.status == "succeeded"
    assert stored.result_summary_json == {"fact_count": 1, "candidate_count": 1}
    assert candidates[0]["canonical_name"] == "Dahua Hero A1"
    assert candidates[0]["status"] == "auto_pending"


@pytest.mark.asyncio
async def test_catalog_handler_without_adapter_fails_visibly(runtime_session):
    job = SchedulerService(runtime_session).enqueue(job_type="parse_artifact", scope_type="parser")
    runtime = WorkerRuntime(
        runtime_session,
        handlers=build_catalog_handler_registry(runtime_session),
    )

    result = await runtime.run_once()

    stored = SchedulerService(runtime_session).repository.get(job.id)
    event = runtime_session.execute(select(operational_events_table)).mappings().one()
    assert stored is not None
    assert result.status == "failed"
    assert stored.last_error == "parse_artifact adapter is not configured"
    assert event["event_type"] == "scheduler"
    assert event["details_json"]["reason"] == "handler_exception"


@pytest.mark.asyncio
async def test_download_artifact_handler_records_downloaded_document(runtime_session, tmp_path):
    telegram_source, raw_source, source_message_id = _create_download_scope(runtime_session)
    job = SchedulerService(runtime_session).enqueue(
        job_type="download_artifact",
        scope_type="telegram_source",
        monitored_source_id=telegram_source.id,
        source_message_id=source_message_id,
        payload_json={
            "source_id": raw_source.id,
            "telegram_message_id": 42,
        },
    )
    client = FakeDownloadTelegramClient(download_bytes=b"catalog")
    runtime = WorkerRuntime(
        runtime_session,
        handlers=build_telegram_handler_registry(
            runtime_session,
            client,
            artifact_storage_path=tmp_path / "artifacts",
        ),
    )

    result = await runtime.run_once()

    stored = SchedulerService(runtime_session).repository.get(job.id)
    artifact = runtime_session.execute(select(artifacts_table)).mappings().one()
    parse_job = (
        runtime_session.execute(
            select(scheduler_jobs_table)
            .where(scheduler_jobs_table.c.job_type == "parse_artifact")
            .where(scheduler_jobs_table.c.status == "queued")
        )
        .mappings()
        .one()
    )
    assert stored is not None
    assert result.status == "succeeded"
    assert stored.result_summary_json == {
        "download_status": "downloaded",
        "artifact_id": artifact["id"],
        "file_name": "catalog.pdf",
    }
    assert artifact["source_id"] == raw_source.id
    assert artifact["artifact_type"] == "document"
    assert artifact["file_name"] == "catalog.pdf"
    assert artifact["mime_type"] == "application/pdf"
    assert artifact["file_size"] == 7
    assert artifact["sha256"] == hashlib.sha256(b"catalog").hexdigest()
    assert Path(artifact["local_path"]).read_bytes() == b"catalog"
    assert parse_job["payload_json"]["source_id"] == raw_source.id
    assert parse_job["payload_json"]["artifact_id"] == artifact["id"]
    assert parse_job["payload_json"]["local_path"] == artifact["local_path"]


@pytest.mark.asyncio
async def test_download_artifact_handler_records_skipped_document(runtime_session, tmp_path):
    telegram_source, raw_source, source_message_id = _create_download_scope(runtime_session)
    job = SchedulerService(runtime_session).enqueue(
        job_type="download_artifact",
        scope_type="telegram_source",
        monitored_source_id=telegram_source.id,
        source_message_id=source_message_id,
        payload_json={
            "source_id": raw_source.id,
            "telegram_message_id": 42,
        },
    )
    client = FakeDownloadTelegramClient(skip_reason="video")
    runtime = WorkerRuntime(
        runtime_session,
        handlers=build_telegram_handler_registry(
            runtime_session,
            client,
            artifact_storage_path=tmp_path / "artifacts",
        ),
    )

    result = await runtime.run_once()

    stored = SchedulerService(runtime_session).repository.get(job.id)
    artifact = runtime_session.execute(select(artifacts_table)).mappings().one()
    parse_job_count = runtime_session.execute(
        select(scheduler_jobs_table.c.id).where(scheduler_jobs_table.c.job_type == "parse_artifact")
    ).all()
    assert stored is not None
    assert result.status == "succeeded"
    assert stored.result_summary_json == {
        "download_status": "skipped",
        "artifact_id": artifact["id"],
        "file_name": "catalog.pdf",
    }
    assert artifact["download_status"] == "skipped"
    assert artifact["skip_reason"] == "video"
    assert artifact["local_path"] is None
    assert parse_job_count == []


class FakeDownloadTelegramClient:
    def __init__(
        self,
        *,
        download_bytes: bytes | None = None,
        skip_reason: str | None = None,
    ) -> None:
        self.download_bytes = download_bytes
        self.skip_reason = skip_reason

    async def resolve_source(self, input_ref: str) -> ResolvedTelegramSource:
        return _resolved_source()

    async def check_access(self, source: ResolvedTelegramSource) -> SourceAccessResult:
        return SourceAccessResult(
            status="succeeded",
            can_read_messages=True,
            can_read_history=True,
            resolved_source=source,
        )

    async def fetch_preview_messages(
        self,
        source: ResolvedTelegramSource,
        *,
        limit: int,
    ) -> list[TelegramMessage]:
        return []

    async def fetch_message_batch(
        self,
        source: ResolvedTelegramSource,
        *,
        after_message_id: int | None,
        limit: int,
    ) -> list[TelegramMessage]:
        return []

    async def fetch_context(
        self,
        source: ResolvedTelegramSource,
        *,
        message_id: int,
        before: int,
        after: int,
        reply_depth: int,
    ) -> MessageContext:
        return MessageContext(message_id, [], [], [])

    async def download_message_document(
        self,
        source: ResolvedTelegramSource,
        *,
        message_id: int,
        destination_dir: str | Path,
    ) -> TelegramDocumentDownload:
        if self.skip_reason:
            return TelegramDocumentDownload(
                status="skipped",
                file_name="catalog.pdf",
                mime_type="application/pdf",
                file_size=7,
                local_path=None,
                skip_reason=self.skip_reason,
            )
        destination = Path(destination_dir) / "catalog.pdf"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.download_bytes or b"")
        return TelegramDocumentDownload(
            status="downloaded",
            file_name="catalog.pdf",
            mime_type="application/pdf",
            file_size=7,
            local_path=str(destination),
        )


def _create_download_scope(runtime_session):
    service = TelegramSourceService(runtime_session)
    telegram_source = service.create_draft(
        "https://t.me/purmaster",
        purpose="catalog_ingestion",
        added_by="admin",
    )
    telegram_source = service.activate(telegram_source.id, actor="admin")
    raw_source = CatalogSourceService(runtime_session).upsert_source(
        source_type="telegram_message",
        origin="telegram:purmaster",
        external_id="42",
        raw_text="catalog.pdf",
    )
    source_message_id = new_id()
    now = utc_now()
    runtime_session.execute(
        insert(source_messages_table).values(
            id=source_message_id,
            monitored_source_id=telegram_source.id,
            raw_source_id=raw_source.id,
            telegram_message_id=42,
            sender_id=None,
            message_date=datetime(2026, 4, 28, 12, 0, tzinfo=UTC),
            text=None,
            caption="catalog.pdf",
            normalized_text="catalog.pdf",
            has_media=True,
            media_metadata_json={
                "type": "MessageMediaDocument",
                "document": {
                    "file_name": "catalog.pdf",
                    "mime_type": "application/pdf",
                    "file_size": 7,
                    "downloadable": True,
                },
            },
            reply_to_message_id=None,
            thread_id=None,
            forward_metadata_json=None,
            raw_metadata_json={},
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
    return telegram_source, raw_source, source_message_id


def _resolved_source() -> ResolvedTelegramSource:
    return ResolvedTelegramSource(
        input_ref="https://t.me/purmaster",
        source_kind="telegram_channel",
        telegram_id="-1001",
        username="purmaster",
        title="PUR",
    )
