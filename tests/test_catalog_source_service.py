import pytest
from sqlalchemy import select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.audit import audit_log_table
from pur_leads.models.catalog import (
    artifacts_table,
    manual_inputs_table,
    parsed_chunks_table,
    sources_table,
)
from pur_leads.services.catalog_sources import CatalogSourceService


@pytest.fixture
def source_session(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        yield session


def test_upsert_source_by_identity_keeps_identity_and_updates_content(source_session):
    service = CatalogSourceService(source_session)

    first = service.upsert_source(
        source_type="manual_text",
        origin="manual",
        external_id="manual-1",
        raw_text="Wi-Fi camera for a dacha",
        title="Initial title",
        metadata_json={"source": "test"},
    )
    second = service.upsert_source(
        source_type="manual_text",
        origin="manual",
        external_id="manual-1",
        raw_text="Wi-Fi camera for a country house",
        title="Updated title",
        metadata_json={"source": "test", "version": 2},
    )

    rows = source_session.execute(select(sources_table)).mappings().all()
    assert first.id == second.id
    assert len(rows) == 1
    assert rows[0]["title"] == "Updated title"
    assert rows[0]["normalized_text"] == "wi-fi camera for a country house"
    assert len(rows[0]["content_hash"]) == 64


def test_add_chunks_and_artifact_metadata(source_session):
    service = CatalogSourceService(source_session)
    source = service.upsert_source(
        source_type="telegraph_page",
        origin="telegra.ph",
        external_id="https://telegra.ph/example",
        raw_text="First chunk. Second chunk.",
    )
    artifact = service.record_artifact(
        source.id,
        artifact_type="document",
        file_name="catalog.pdf",
        mime_type="application/pdf",
        file_size=1234,
        sha256="a" * 64,
        local_path="artifacts/catalog.pdf",
        download_status="downloaded",
    )

    chunks = service.replace_parsed_chunks(
        source.id,
        artifact_id=artifact.id,
        chunks=["First chunk text", "Second chunk text with more words"],
        parser_name="test-parser",
        parser_version="1",
    )

    artifact_row = source_session.execute(select(artifacts_table)).mappings().one()
    chunk_rows = (
        source_session.execute(
            select(parsed_chunks_table).order_by(parsed_chunks_table.c.chunk_index)
        )
        .mappings()
        .all()
    )
    assert artifact_row["file_name"] == "catalog.pdf"
    assert artifact_row["download_status"] == "downloaded"
    assert [chunk.id for chunk in chunks] == [row["id"] for row in chunk_rows]
    assert [row["chunk_index"] for row in chunk_rows] == [0, 1]
    assert [row["token_estimate"] for row in chunk_rows] == [3, 6]


def test_submit_manual_text_creates_input_source_and_audit(source_session):
    service = CatalogSourceService(source_session)

    result = service.submit_manual_input(
        input_type="manual_text",
        submitted_by="oleg",
        text="Добавить термин: камера на дачу",
        evidence_note="Олег добавил вручную",
        metadata_json={"intent": "catalog_term"},
    )

    manual_input = source_session.execute(select(manual_inputs_table)).mappings().one()
    source = source_session.execute(select(sources_table)).mappings().one()
    audit_rows = source_session.execute(select(audit_log_table)).mappings().all()
    assert result.manual_input.id == manual_input["id"]
    assert result.source is not None
    assert result.source.id == source["id"]
    assert manual_input["processing_status"] == "processed"
    assert source["source_type"] == "manual_text"
    assert source["raw_text"] == "Добавить термин: камера на дачу"
    assert source["metadata_json"]["evidence_note"] == "Олег добавил вручную"
    assert [row["action"] for row in audit_rows] == [
        "manual_input.create",
        "manual_input.process_source",
    ]


def test_manual_link_creates_manual_link_source(source_session):
    service = CatalogSourceService(source_session)

    result = service.submit_manual_input(
        input_type="telegram_link",
        submitted_by="admin",
        url="https://t.me/purmaster/42",
        chat_ref="purmaster",
        message_id=42,
        evidence_note="Source link from Oleg",
    )

    assert result.source is not None
    assert result.source.source_type == "manual_link"
    assert result.source.origin == "purmaster"
    assert result.source.external_id == "42"
    assert result.source.url == "https://t.me/purmaster/42"
