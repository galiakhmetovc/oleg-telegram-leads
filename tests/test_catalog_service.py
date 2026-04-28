import pytest
from sqlalchemy import select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.catalog import (
    catalog_categories_table,
    catalog_evidence_table,
    catalog_items_table,
    catalog_terms_table,
    catalog_versions_table,
)
from pur_leads.services.catalog import CatalogService, INITIAL_CATEGORY_SLUGS
from pur_leads.services.catalog_candidates import CatalogCandidateService
from pur_leads.services.catalog_sources import CatalogSourceService


@pytest.fixture
def catalog_session(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        source = CatalogSourceService(session).upsert_source(
            source_type="manual_text",
            origin="manual",
            external_id="seed",
            raw_text="Dahua Hero A1 Wi-Fi camera",
        )
        chunk = CatalogSourceService(session).replace_parsed_chunks(
            source.id,
            chunks=["Dahua Hero A1 Wi-Fi camera"],
            parser_name="test",
            parser_version="1",
        )[0]
        run = CatalogCandidateService(session).start_extraction_run(
            run_type="catalog_extraction",
            extractor_version="test-extractor",
        )
        yield session, source, chunk, run


def test_seed_initial_categories_is_idempotent(catalog_session):
    session, *_ = catalog_session
    service = CatalogService(session)

    first = service.seed_initial_categories()
    second = service.seed_initial_categories()

    rows = session.execute(select(catalog_categories_table)).mappings().all()
    assert len(first) == len(INITIAL_CATEGORY_SLUGS)
    assert len(second) == len(INITIAL_CATEGORY_SLUGS)
    assert len(rows) == len(INITIAL_CATEGORY_SLUGS)
    assert rows[0]["status"] == "approved"


def test_promote_item_candidate_creates_item_terms_and_evidence(catalog_session):
    session, source, chunk, run = catalog_session
    candidate_service = CatalogCandidateService(session)
    fact = candidate_service.create_extracted_fact(
        extraction_run_id=run.id,
        fact_type="product",
        canonical_name="Dahua Hero A1",
        value_json={
            "item_type": "product",
            "category_slug": "video_surveillance",
            "terms": ["Hero A1", "wi-fi камера"],
            "description": "Wi-Fi camera for a dacha",
        },
        confidence=0.92,
        source_id=source.id,
        chunk_id=chunk.id,
    )
    candidate = candidate_service.create_or_update_candidate_from_fact(
        fact.id,
        candidate_type="item",
        evidence_quote="Dahua Hero A1 Wi-Fi camera",
    )

    promoted = CatalogService(session).promote_candidate(candidate.id, actor="system")

    item = session.execute(select(catalog_items_table)).mappings().one()
    terms = session.execute(select(catalog_terms_table)).mappings().all()
    evidence = session.execute(select(catalog_evidence_table)).mappings().all()
    assert promoted.entity_type == "item"
    assert promoted.entity_id == item["id"]
    assert item["name"] == "Dahua Hero A1"
    assert item["status"] == "auto_pending"
    assert item["first_seen_source_id"] == source.id
    assert {term["normalized_term"] for term in terms} == {"hero a1", "wi-fi камера"}
    assert all(term["status"] == "auto_pending" for term in terms)
    assert {"catalog_candidate", "extracted_fact", "item", "term"}.issubset(
        {row["entity_type"] for row in evidence}
    )


def test_promote_lead_phrase_candidate_creates_term_without_item(catalog_session):
    session, source, chunk, run = catalog_session
    candidate_service = CatalogCandidateService(session)
    fact = candidate_service.create_extracted_fact(
        extraction_run_id=run.id,
        fact_type="lead_intent",
        canonical_name="нужна камера на дачу",
        value_json={"term": "нужна камера на дачу", "term_type": "lead_phrase"},
        confidence=0.86,
        source_id=source.id,
        chunk_id=chunk.id,
    )
    candidate = candidate_service.create_or_update_candidate_from_fact(
        fact.id,
        candidate_type="lead_phrase",
    )

    promoted = CatalogService(session).promote_candidate(candidate.id, actor="system")

    term = session.execute(select(catalog_terms_table)).mappings().one()
    assert promoted.entity_type == "term"
    assert term["item_id"] is None
    assert term["term_type"] == "lead_phrase"
    assert term["normalized_term"] == "нужна камера на дачу"


def test_create_catalog_version_counts_and_hashes(catalog_session):
    session, source, chunk, run = catalog_session
    candidate_service = CatalogCandidateService(session)
    fact = candidate_service.create_extracted_fact(
        extraction_run_id=run.id,
        fact_type="product",
        canonical_name="Dahua Hero A1",
        value_json={"item_type": "product", "terms": ["Hero A1"]},
        confidence=0.92,
        source_id=source.id,
        chunk_id=chunk.id,
    )
    candidate = candidate_service.create_or_update_candidate_from_fact(
        fact.id, candidate_type="item"
    )
    service = CatalogService(session)
    service.seed_initial_categories()
    service.promote_candidate(candidate.id, actor="system")

    version = service.create_catalog_version(created_by="system")

    row = session.execute(select(catalog_versions_table)).mappings().one()
    assert version.version == 1
    assert row["item_count"] == 1
    assert row["term_count"] == 1
    assert row["included_statuses_json"] == ["approved", "auto_pending"]
    assert len(row["catalog_hash"]) == 64
