import pytest
from sqlalchemy import select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.audit import operational_events_table
from pur_leads.models.catalog import (
    catalog_candidates_table,
    parsed_chunks_table,
)
from pur_leads.services.catalog_sources import CatalogSourceService
from pur_leads.services.scheduler import SchedulerService
from pur_leads.workers.runtime import (
    CatalogExtractedFact,
    ParsedArtifact,
    WorkerRuntime,
    build_catalog_handler_registry,
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
