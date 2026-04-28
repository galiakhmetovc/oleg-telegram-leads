import pytest
from sqlalchemy import select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.catalog import (
    catalog_candidate_facts_table,
    catalog_candidates_table,
    catalog_evidence_table,
    extracted_facts_table,
    extraction_runs_table,
)
from pur_leads.services.catalog_candidates import CatalogCandidateService
from pur_leads.services.catalog_sources import CatalogSourceService


@pytest.fixture
def candidate_session(tmp_path):
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
        yield session, source, chunk


def test_extraction_run_lifecycle(candidate_session):
    session, source, _ = candidate_session
    service = CatalogCandidateService(session)

    run = service.start_extraction_run(
        run_type="catalog_extraction",
        extractor_version="test-extractor",
        model="glm-test",
        prompt_version="p1",
        source_scope_json={"source_ids": [source.id]},
    )
    finished = service.finish_extraction_run(
        run.id,
        status="succeeded",
        stats_json={"ok": True},
        token_usage_json={"total_tokens": 123},
    )

    row = session.execute(select(extraction_runs_table)).mappings().one()
    assert row["id"] == run.id
    assert row["status"] == "succeeded"
    assert row["finished_at"] is not None
    assert row["token_usage_json"] == {"total_tokens": 123}
    assert finished.status == "succeeded"


def test_create_fact_candidate_evidence_and_dedupe(candidate_session):
    session, source, chunk = candidate_session
    service = CatalogCandidateService(session)
    run = service.start_extraction_run(
        run_type="catalog_extraction",
        extractor_version="test-extractor",
    )

    fact = service.create_extracted_fact(
        extraction_run_id=run.id,
        fact_type="product",
        canonical_name="Dahua Hero A1",
        value_json={"item_type": "product", "category_slug": "video_surveillance"},
        confidence=0.92,
        source_id=source.id,
        chunk_id=chunk.id,
    )
    first = service.create_or_update_candidate_from_fact(
        fact.id,
        candidate_type="item",
        proposed_action="create",
        evidence_quote="Dahua Hero A1 Wi-Fi camera",
        created_by="system",
    )
    second = service.create_or_update_candidate_from_fact(
        fact.id,
        candidate_type="item",
        proposed_action="create",
        evidence_quote="Dahua Hero A1 Wi-Fi camera",
        created_by="system",
    )

    candidates = session.execute(select(catalog_candidates_table)).mappings().all()
    links = session.execute(select(catalog_candidate_facts_table)).mappings().all()
    evidence = session.execute(select(catalog_evidence_table)).mappings().all()
    assert first.id == second.id
    assert len(candidates) == 1
    assert candidates[0]["status"] == "auto_pending"
    assert candidates[0]["source_count"] == 1
    assert candidates[0]["evidence_count"] == 1
    assert len(links) == 1
    assert len(evidence) == 2
    assert {row["entity_type"] for row in evidence} == {"catalog_candidate", "extracted_fact"}


def test_candidate_status_policy_marks_low_confidence_and_offers(candidate_session):
    session, source, chunk = candidate_session
    service = CatalogCandidateService(session)
    run = service.start_extraction_run(
        run_type="catalog_extraction",
        extractor_version="test-extractor",
    )
    low_confidence = service.create_extracted_fact(
        extraction_run_id=run.id,
        fact_type="term",
        canonical_name="камера",
        value_json={"term_type": "keyword", "too_broad": True},
        confidence=0.42,
        source_id=source.id,
        chunk_id=chunk.id,
    )
    offer_without_ttl = service.create_extracted_fact(
        extraction_run_id=run.id,
        fact_type="offer",
        canonical_name="Hero A1 price",
        value_json={"price_text": "по акции", "ttl_source": "none"},
        confidence=0.9,
        source_id=source.id,
        chunk_id=chunk.id,
    )
    offer_with_ttl = service.create_extracted_fact(
        extraction_run_id=run.id,
        fact_type="offer",
        canonical_name="Hero A1 fixed price",
        value_json={"price_text": "2500 RUB", "ttl_days": 30, "ttl_source": "default_setting"},
        confidence=0.9,
        source_id=source.id,
        chunk_id=chunk.id,
    )

    broad = service.create_or_update_candidate_from_fact(low_confidence.id, candidate_type="term")
    review_offer = service.create_or_update_candidate_from_fact(
        offer_without_ttl.id, candidate_type="offer"
    )
    auto_offer = service.create_or_update_candidate_from_fact(
        offer_with_ttl.id, candidate_type="offer"
    )

    assert broad.status == "needs_review"
    assert review_offer.status == "needs_review"
    assert auto_offer.status == "auto_pending"
    assert session.execute(select(extracted_facts_table)).mappings().all()
