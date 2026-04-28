import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database


EXPECTED_TABLES = {
    "lead_events",
    "lead_clusters",
    "lead_cluster_members",
    "lead_cluster_actions",
    "lead_matches",
    "feedback_events",
    "crm_conversion_candidates",
    "crm_conversion_actions",
}


@pytest.fixture
def engine(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    return engine


def test_lead_inbox_tables_and_indexes_exist(engine):
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert EXPECTED_TABLES.issubset(tables)

    lead_event_indexes = {index["name"] for index in inspector.get_indexes("lead_events")}
    cluster_indexes = {index["name"] for index in inspector.get_indexes("lead_clusters")}
    assert "uq_lead_events_detection_identity" in lead_event_indexes
    assert "ix_lead_clusters_queue" in cluster_indexes


def test_lead_event_constraints_and_unique_identity(engine):
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO monitored_sources (
                    id, source_kind, input_ref, source_purpose, priority, status,
                    lead_detection_enabled, catalog_ingestion_enabled, phase_enabled,
                    start_mode, historical_backfill_policy, poll_interval_seconds,
                    added_by, created_at, updated_at
                )
                VALUES (
                    'source-1', 'telegram_supergroup', '@test', 'lead_monitoring',
                    'normal', 'active', 1, 0, 1, 'from_now', 'retro_web_only',
                    60, 'test', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO source_messages (
                    id, monitored_source_id, telegram_message_id, message_date,
                    text, has_media, fetched_at, classification_status,
                    is_archived_stub, text_archived, caption_archived, metadata_archived,
                    created_at, updated_at
                )
                VALUES (
                    'message-1', 'source-1', 100, CURRENT_TIMESTAMP,
                    'нужна камера', 0, CURRENT_TIMESTAMP, 'pending',
                    0, 0, 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO classifier_versions (
                    id, version, created_at, created_by, included_statuses_json,
                    catalog_hash, example_hash, prompt_hash, keyword_index_hash, settings_hash
                )
                VALUES (
                    'classifier-1', 1, CURRENT_TIMESTAMP, 'test', '[]',
                    'a', 'b', 'c', 'd', 'e'
                )
                """
            )
        )

        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    """
                    INSERT INTO lead_events (
                        id, source_message_id, monitored_source_id, telegram_message_id,
                        detected_at, classifier_version_id, decision, detection_mode,
                        confidence, event_status, event_review_status, is_retro, created_at
                    )
                    VALUES (
                        'lead-bad', 'message-1', 'source-1', 100, CURRENT_TIMESTAMP,
                        'classifier-1', 'bad_decision', 'live', 0.9, 'active',
                        'unreviewed', 0, CURRENT_TIMESTAMP
                    )
                    """
                )
            )

        conn.execute(
            text(
                """
                INSERT INTO lead_events (
                    id, source_message_id, monitored_source_id, telegram_message_id,
                    detected_at, classifier_version_id, decision, detection_mode,
                    confidence, event_status, event_review_status, is_retro, created_at
                )
                VALUES (
                    'lead-1', 'message-1', 'source-1', 100, CURRENT_TIMESTAMP,
                    'classifier-1', 'lead', 'live', 0.9, 'active',
                    'unreviewed', 0, CURRENT_TIMESTAMP
                )
                """
            )
        )

        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    """
                    INSERT INTO lead_events (
                        id, source_message_id, monitored_source_id, telegram_message_id,
                        detected_at, classifier_version_id, decision, detection_mode,
                        confidence, event_status, event_review_status, is_retro, created_at
                    )
                    VALUES (
                        'lead-duplicate', 'message-1', 'source-1', 100, CURRENT_TIMESTAMP,
                        'classifier-1', 'maybe', 'live', 0.4, 'active',
                        'unreviewed', 0, CURRENT_TIMESTAMP
                    )
                    """
                )
            )
