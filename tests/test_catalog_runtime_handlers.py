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
    catalog_quality_reviews_table,
    classifier_snapshot_entries_table,
    classifier_versions_table,
    extraction_runs_table,
    parsed_chunks_table,
)
from pur_leads.models.scheduler import scheduler_jobs_table
from pur_leads.models.telegram_sources import source_messages_table
from pur_leads.services.catalog_candidates import CatalogCandidateService
from pur_leads.services.catalog_sources import CatalogSourceService
from pur_leads.services.scheduler import SchedulerService
from pur_leads.services.telegram_sources import TelegramSourceService
from pur_leads.workers.runtime import (
    CatalogExtractedFact,
    CatalogCandidateValidationResult,
    FetchedExternalPage,
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
    extractor_version = "fake-extractor-v1"
    model = "fake-model"
    prompt_version = "fake-prompt-v1"
    last_token_usage_json = {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
    }

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


class FakeExternalPageFetcher:
    async def fetch_page(self, *, url: str, payload: dict):
        return FetchedExternalPage(
            url=url,
            final_url=url,
            title="PUR smart home",
            text="Dahua Hero A1 и умные реле для дома",
            status_code=200,
            content_type="text/html; charset=utf-8",
        )


class FakeCandidateValidator:
    model = "GLM-5.1"
    model_profile = "catalog-validator-strong"
    prompt_version = "catalog-candidate-validation-v1"
    last_token_usage_json = {"total_tokens": 321}

    async def validate_catalog_candidate(self, *, candidate_id: str, payload: dict):
        return CatalogCandidateValidationResult(
            decision="confirm",
            confidence=0.96,
            reason=f"{candidate_id} is supported by evidence",
            proposed_changes_json={},
            evidence_json={"quotes": ["Dahua Hero A1"]},
            raw_output_json={"decision": "confirm"},
        )


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
async def test_extract_catalog_facts_handler_stores_llm_metadata_and_rebuilds_snapshot(
    runtime_session,
):
    source = CatalogSourceService(runtime_session).upsert_source(
        source_type="manual_text",
        origin="manual",
        external_id="llm-extract-source",
        raw_text="Dahua Hero A1",
    )
    chunk = CatalogSourceService(runtime_session).replace_parsed_chunks(
        source.id,
        chunks=["Dahua Hero A1"],
        parser_name="test",
        parser_version="1",
    )[0]
    SchedulerService(runtime_session).enqueue(
        job_type="extract_catalog_facts",
        scope_type="parser",
        payload_json={"source_id": source.id, "chunk_id": chunk.id},
    )
    runtime = WorkerRuntime(
        runtime_session,
        handlers=build_catalog_handler_registry(runtime_session, extractor=FakeExtractor()),
    )

    result = await runtime.run_once()

    run = runtime_session.execute(select(extraction_runs_table)).mappings().one()
    version = runtime_session.execute(select(classifier_versions_table)).mappings().one()
    entries = runtime_session.execute(select(classifier_snapshot_entries_table)).mappings().all()
    assert result.status == "succeeded"
    assert run["extractor_version"] == "fake-extractor-v1"
    assert run["model"] == "fake-model"
    assert run["prompt_version"] == "fake-prompt-v1"
    assert run["token_usage_json"] == {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
    }
    assert version["model"] == "builtin-fuzzy"
    assert any(row["normalized_value"] == "dahua hero a1" for row in entries)


@pytest.mark.asyncio
async def test_fetch_external_page_handler_stores_page_chunk_and_extract_job(runtime_session):
    parent_source = CatalogSourceService(runtime_session).upsert_source(
        source_type="telegram_message",
        origin="telegram:purmaster",
        external_id="41",
        raw_text="source link",
    )
    job = SchedulerService(runtime_session).enqueue(
        job_type="fetch_external_page",
        scope_type="parser",
        payload_json={
            "url": "https://telegra.ph/PUR-Umnyj-Dom-glazami-inzhenera-01-31",
            "parent_source_id": parent_source.id,
        },
    )
    runtime = WorkerRuntime(
        runtime_session,
        handlers=build_catalog_handler_registry(
            runtime_session,
            external_page_fetcher=FakeExternalPageFetcher(),
        ),
    )

    result = await runtime.run_once()

    stored = SchedulerService(runtime_session).repository.get(job.id)
    chunks = runtime_session.execute(select(parsed_chunks_table)).mappings().all()
    extract_job = (
        runtime_session.execute(
            select(scheduler_jobs_table).where(
                scheduler_jobs_table.c.job_type == "extract_catalog_facts"
            )
        )
        .mappings()
        .one()
    )
    assert stored is not None
    assert result.status == "succeeded"
    assert stored.result_summary_json == {
        "source_id": chunks[0]["source_id"],
        "chunk_count": 1,
        "status_code": 200,
    }
    assert chunks[0]["text"] == "Dahua Hero A1 и умные реле для дома"
    assert chunks[0]["parser_name"] == "external-page-text"
    assert extract_job["payload_json"]["source_id"] == chunks[0]["source_id"]
    assert extract_job["payload_json"]["chunk_id"] == chunks[0]["id"]


@pytest.mark.asyncio
async def test_catalog_candidate_validation_handler_stores_quality_review(runtime_session):
    candidate = _create_catalog_candidate(runtime_session)
    job = SchedulerService(runtime_session).enqueue(
        job_type="catalog_candidate_validation",
        priority="low",
        scope_type="parser",
        scope_id=candidate.id,
        payload_json={
            "candidate_id": candidate.id,
            "validator_model": "GLM-5.1",
            "validator_profile": "catalog-validator-strong",
        },
    )
    runtime = WorkerRuntime(
        runtime_session,
        handlers=build_catalog_handler_registry(
            runtime_session,
            candidate_validator=FakeCandidateValidator(),
        ),
    )

    result = await runtime.run_once()

    stored = SchedulerService(runtime_session).repository.get(job.id)
    review = runtime_session.execute(select(catalog_quality_reviews_table)).mappings().one()
    assert stored is not None
    assert result.status == "succeeded"
    assert stored.result_summary_json == {
        "candidate_id": candidate.id,
        "decision": "confirm",
        "validator_model": "GLM-5.1",
    }
    assert review["catalog_candidate_id"] == candidate.id
    assert review["scheduler_job_id"] == job.id
    assert review["validator_model"] == "GLM-5.1"
    assert review["validator_profile"] == "catalog-validator-strong"
    assert review["decision"] == "confirm"
    assert review["confidence"] == 0.96
    assert review["token_usage_json"] == {"total_tokens": 321}


@pytest.mark.asyncio
async def test_worker_enqueues_idle_quality_validation_only_without_active_normal_work(
    runtime_session,
):
    candidate = _create_catalog_candidate(runtime_session)
    normal_job = SchedulerService(runtime_session).enqueue(
        job_type="parse_artifact",
        priority="normal",
        scope_type="parser",
        payload_json={"source_id": "source"},
    )
    runtime = WorkerRuntime(
        runtime_session,
        handlers=build_catalog_handler_registry(
            runtime_session,
            candidate_validator=FakeCandidateValidator(),
        ),
    )

    first = await runtime.run_once()

    assert first.status == "failed"
    assert SchedulerService(runtime_session).repository.get(normal_job.id).last_error == (
        "parse_artifact adapter is not configured"
    )
    assert (
        runtime_session.execute(
            select(scheduler_jobs_table).where(
                scheduler_jobs_table.c.job_type == "catalog_candidate_validation"
            )
        )
        .mappings()
        .all()
        == []
    )

    second = await runtime.run_once()

    quality_job = (
        runtime_session.execute(
            select(scheduler_jobs_table).where(
                scheduler_jobs_table.c.job_type == "catalog_candidate_validation"
            )
        )
        .mappings()
        .one()
    )
    assert second.status == "succeeded"
    assert quality_job["scope_id"] == candidate.id


@pytest.mark.asyncio
async def test_idle_quality_validation_respects_active_job_cap(runtime_session):
    candidate = _create_catalog_candidate(runtime_session)
    scheduler = SchedulerService(runtime_session)
    active_job = scheduler.enqueue(
        job_type="catalog_candidate_validation",
        priority="low",
        scope_type="parser",
        scope_id=candidate.id,
        idempotency_key=f"catalog-quality-review:{candidate.id}:GLM-5.1:catalog-validator-strong",
        payload_json={
            "candidate_id": candidate.id,
            "validator_model": "GLM-5.1",
            "validator_profile": "catalog-validator-strong",
        },
    )
    acquired = scheduler.acquire_next("already-running", now=utc_now())
    assert acquired is not None
    assert acquired.id == active_job.id

    runtime = WorkerRuntime(
        runtime_session,
        handlers=build_catalog_handler_registry(
            runtime_session,
            candidate_validator=FakeCandidateValidator(),
        ),
    )

    result = await runtime.run_once()

    quality_jobs = (
        runtime_session.execute(
            select(scheduler_jobs_table).where(
                scheduler_jobs_table.c.job_type == "catalog_candidate_validation"
            )
        )
        .mappings()
        .all()
    )
    assert result.status == "idle"
    assert len(quality_jobs) == 1
    assert quality_jobs[0]["status"] == "running"


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
        after_date: object | None = None,
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


def _create_catalog_candidate(runtime_session):
    source = CatalogSourceService(runtime_session).upsert_source(
        source_type="manual_text",
        origin="manual",
        external_id=f"candidate-{new_id()}",
        raw_text="Dahua Hero A1 Wi-Fi camera",
    )
    chunk = CatalogSourceService(runtime_session).replace_parsed_chunks(
        source.id,
        chunks=["Dahua Hero A1 Wi-Fi camera"],
        parser_name="test",
        parser_version="1",
    )[0]
    service = CatalogCandidateService(runtime_session)
    run = service.start_extraction_run(
        run_type="catalog_extraction",
        extractor_version="test-extractor",
        model="GLM-4.5-Flash",
    )
    fact = service.create_extracted_fact(
        extraction_run_id=run.id,
        fact_type="product",
        canonical_name="Dahua Hero A1",
        value_json={"item_type": "product", "terms": ["Hero A1"]},
        confidence=0.91,
        source_id=source.id,
        chunk_id=chunk.id,
    )
    return service.create_or_update_candidate_from_fact(
        fact.id,
        candidate_type="item",
        evidence_quote="Dahua Hero A1 Wi-Fi camera",
    )


def _resolved_source() -> ResolvedTelegramSource:
    return ResolvedTelegramSource(
        input_ref="https://t.me/purmaster",
        source_kind="telegram_channel",
        telegram_id="-1001",
        username="purmaster",
        title="PUR",
    )
