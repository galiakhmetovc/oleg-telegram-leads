import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database


EXPECTED_TABLES = {
    "web_users",
    "web_auth_sessions",
    "tasks",
}


@pytest.fixture
def engine(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    return engine


def test_web_auth_and_task_tables_and_indexes_exist(engine):
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert EXPECTED_TABLES.issubset(tables)

    user_indexes = {index["name"] for index in inspector.get_indexes("web_users")}
    session_indexes = {index["name"] for index in inspector.get_indexes("web_auth_sessions")}
    task_indexes = {index["name"] for index in inspector.get_indexes("tasks")}
    assert "uq_web_users_local_username" in user_indexes
    assert "uq_web_users_telegram_user_id" in user_indexes
    assert "uq_web_auth_sessions_token_hash" in session_indexes
    assert "ix_web_auth_sessions_user_active" in session_indexes
    assert "ix_tasks_lead_cluster_status_due" in task_indexes


def test_web_user_constraints_and_unique_identities(engine):
    with engine.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    """
                    INSERT INTO web_users (
                        id, auth_type, local_username, role, status,
                        must_change_password, created_at, updated_at
                    )
                    VALUES (
                        'bad-role', 'local', 'bad', 'viewer', 'active',
                        1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                )
            )

        conn.execute(
            text(
                """
                INSERT INTO web_users (
                    id, telegram_user_id, telegram_username, display_name,
                    auth_type, local_username, password_hash, must_change_password,
                    role, status, created_at, updated_at
                )
                VALUES (
                    'admin-1', '100', 'oleg', 'Oleg',
                    'local', 'admin', 'hash', 1,
                    'admin', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )

        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    """
                    INSERT INTO web_users (
                        id, auth_type, local_username, role, status,
                        must_change_password, created_at, updated_at
                    )
                    VALUES (
                        'duplicate-local', 'local', 'admin', 'admin', 'active',
                        0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                )
            )

        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    """
                    INSERT INTO web_users (
                        id, telegram_user_id, auth_type, role, status,
                        must_change_password, created_at, updated_at
                    )
                    VALUES (
                        'duplicate-telegram', '100', 'telegram', 'admin', 'active',
                        0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                )
            )


def test_session_and_task_constraints(engine):
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO web_users (
                    id, auth_type, local_username, password_hash, must_change_password,
                    role, status, created_at, updated_at
                )
                VALUES (
                    'admin-1', 'local', 'admin', 'hash', 1,
                    'admin', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO web_auth_sessions (
                    id, user_id, auth_method, session_token_hash,
                    created_at, expires_at, last_seen_at
                )
                VALUES (
                    'session-1', 'admin-1', 'local', 'token-hash',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )

        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    """
                    INSERT INTO web_auth_sessions (
                        id, user_id, auth_method, session_token_hash,
                        created_at, expires_at, last_seen_at
                    )
                    VALUES (
                        'session-duplicate', 'admin-1', 'telegram', 'token-hash',
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                )
            )

        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    """
                    INSERT INTO tasks (
                        id, title, status, priority, created_at, updated_at
                    )
                    VALUES (
                        'bad-task', 'Contact lead', 'waiting', 'normal',
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                )
            )

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
                    'нужна камера', 0, CURRENT_TIMESTAMP, 'unclassified',
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
        conn.execute(
            text(
                """
                INSERT INTO lead_clusters (
                    id, monitored_source_id, primary_source_message_id,
                    cluster_status, review_status, work_outcome,
                    message_count, lead_event_count, merge_strategy,
                    notify_update_count, crm_candidate_count, created_at, updated_at
                )
                VALUES (
                    'cluster-1', 'source-1', 'message-1',
                    'new', 'unreviewed', 'none',
                    1, 0, 'none', 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO lead_events (
                    id, source_message_id, monitored_source_id, telegram_message_id,
                    lead_cluster_id, detected_at, classifier_version_id, decision,
                    detection_mode, confidence, event_status, event_review_status,
                    is_retro, created_at
                )
                VALUES (
                    'event-1', 'message-1', 'source-1', 100,
                    'cluster-1', CURRENT_TIMESTAMP, 'classifier-1', 'lead',
                    'live', 0.9, 'active', 'unreviewed',
                    0, CURRENT_TIMESTAMP
                )
                """
            )
        )

        conn.execute(
            text(
                """
                INSERT INTO tasks (
                    id, lead_cluster_id, lead_event_id, title, description,
                    status, priority, due_at, owner_user_id, assignee_user_id,
                    created_at, updated_at
                )
                VALUES (
                    'task-1', 'cluster-1', 'event-1', 'Contact lead', 'Call today',
                    'open', 'high', CURRENT_TIMESTAMP, 'admin-1', 'admin-1',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )

        task = conn.execute(text("SELECT * FROM tasks WHERE id = 'task-1'")).mappings().one()
        assert task["lead_cluster_id"] == "cluster-1"
        assert task["lead_event_id"] == "event-1"
        assert task["status"] == "open"
