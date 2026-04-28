import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database


EXPECTED_TABLES = {
    "sources",
    "artifacts",
    "parsed_chunks",
    "parsed_chunks_fts",
    "extraction_runs",
    "catalog_versions",
    "extracted_facts",
    "catalog_candidates",
    "catalog_candidate_facts",
    "catalog_categories",
    "catalog_items",
    "catalog_terms",
    "catalog_attributes",
    "catalog_offers",
    "catalog_relations",
    "catalog_evidence",
    "manual_inputs",
    "classifier_examples",
    "classifier_versions",
    "classifier_snapshot_entries",
    "classifier_version_artifacts",
}


@pytest.fixture
def engine(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    return engine


def test_catalog_source_tables_and_indexes_exist(engine):
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert EXPECTED_TABLES.issubset(tables)

    source_indexes = {index["name"] for index in inspector.get_indexes("sources")}
    term_indexes = {index["name"] for index in inspector.get_indexes("catalog_terms")}
    evidence_indexes = {index["name"] for index in inspector.get_indexes("catalog_evidence")}
    assert "uq_sources_identity" in source_indexes
    assert "uq_catalog_terms_identity" in term_indexes
    assert "uq_catalog_evidence_identity" in evidence_indexes


def test_catalog_source_constraints_reject_invalid_values(engine):
    with engine.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    """
                    INSERT INTO sources (
                        id, source_type, origin, external_id, content_hash, created_at
                    )
                    VALUES (
                        'source-1', 'bad_type', 'manual', '1', 'hash', CURRENT_TIMESTAMP
                    )
                    """
                )
            )

        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    """
                    INSERT INTO catalog_candidates (
                        id, candidate_type, proposed_action, canonical_name,
                        normalized_value_json, source_count, evidence_count, confidence,
                        status, first_seen_at, last_seen_at, created_by, created_at, updated_at
                    )
                    VALUES (
                        'candidate-1', 'item', 'create', 'Camera',
                        '{}', 1, 1, 0.9, 'bad_status',
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'system',
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                )
            )


def test_source_identity_and_chunk_fts(engine):
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO sources (
                    id, source_type, origin, external_id, raw_text,
                    normalized_text, content_hash, created_at
                )
                VALUES (
                    'source-1', 'manual_text', 'manual', 'manual-1',
                    'Wi-Fi camera for a dacha', 'wi-fi camera for a dacha',
                    'hash-1', CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO parsed_chunks (
                    id, source_id, artifact_id, chunk_index, text,
                    token_estimate, parser_name, parser_version, created_at
                )
                VALUES (
                    'chunk-1', 'source-1', NULL, 0,
                    'Dahua Hero A1 Wi-Fi camera for dacha',
                    8, 'test', '1', CURRENT_TIMESTAMP
                )
                """
            )
        )

        fts_rows = conn.execute(
            text(
                """
                SELECT parsed_chunks_fts.text
                FROM parsed_chunks_fts
                WHERE parsed_chunks_fts MATCH 'Dahua'
                """
            )
        ).all()
        assert fts_rows == [("Dahua Hero A1 Wi-Fi camera for dacha",)]

        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    """
                    INSERT INTO sources (
                        id, source_type, origin, external_id, content_hash, created_at
                    )
                    VALUES (
                        'source-duplicate', 'manual_text', 'manual', 'manual-1',
                        'hash-2', CURRENT_TIMESTAMP
                    )
                    """
                )
            )
