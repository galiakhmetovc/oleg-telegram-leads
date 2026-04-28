from datetime import datetime

import pytest
from sqlalchemy import insert, select

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.catalog import (
    catalog_categories_table,
    classifier_snapshot_entries_table,
    classifier_versions_table,
)
from pur_leads.models.leads import (
    crm_conversion_actions_table,
    feedback_events_table,
    lead_clusters_table,
)
from pur_leads.models.tasks import tasks_table
from pur_leads.models.telegram_sources import monitored_sources_table, source_messages_table
from pur_leads.services.leads import LeadDetectionResult, LeadMatchInput, LeadService
from pur_leads.services.web_auth import WebAuthService


@pytest.fixture
def work_session(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        source_id = _insert_monitored_source(session)
        category_id = _insert_category(session)
        classifier_version_id = _insert_classifier_version(session)
        snapshot_entry_id = _insert_snapshot_entry(session, classifier_version_id, category_id)
        session.commit()
        yield session, source_id, category_id, classifier_version_id, snapshot_entry_id


def test_take_into_work_creates_contact_task_and_does_not_convert_crm(work_session):
    session, source_id, category_id, classifier_version_id, snapshot_entry_id = work_session
    admin = WebAuthService(session, telegram_bot_token="bot-token").ensure_bootstrap_admin(
        username="admin",
        password="initial-secret",
    )
    event, cluster = _create_clustered_event(
        session,
        source_id,
        category_id,
        classifier_version_id,
        snapshot_entry_id,
    )

    result = LeadService(session).take_into_work(
        cluster.id,
        actor="admin",
        owner_user_id=admin.id,
    )

    cluster_row = (
        session.execute(select(lead_clusters_table).where(lead_clusters_table.c.id == cluster.id))
        .mappings()
        .one()
    )
    task_row = session.execute(select(tasks_table)).mappings().one()
    feedback_row = session.execute(select(feedback_events_table)).mappings().one()
    crm_actions = session.execute(select(crm_conversion_actions_table)).mappings().all()
    assert result.task.id == task_row["id"]
    assert result.feedback.id == feedback_row["id"]
    assert cluster_row["cluster_status"] == "in_work"
    assert cluster_row["review_status"] == "confirmed"
    assert cluster_row["work_outcome"] == "contact_task_created"
    assert cluster_row["primary_task_id"] == task_row["id"]
    assert cluster_row["converted_entity_type"] is None
    assert task_row["lead_cluster_id"] == cluster.id
    assert task_row["lead_event_id"] == event.id
    assert task_row["status"] == "open"
    assert task_row["priority"] == "normal"
    assert task_row["owner_user_id"] == admin.id
    assert task_row["assignee_user_id"] == admin.id
    assert task_row["due_at"] is not None
    assert feedback_row["action"] == "lead_confirmed"
    assert crm_actions == []


def _create_clustered_event(
    session,
    source_id: str,
    category_id: str,
    classifier_version_id: str,
    snapshot_entry_id: str,
):
    message_id = _insert_source_message(session, source_id)
    service = LeadService(session)
    event = service.record_detection(
        source_message_id=message_id,
        classifier_version_id=classifier_version_id,
        result=LeadDetectionResult(
            decision="lead",
            detection_mode="live",
            confidence=0.9,
            commercial_value_score=0.7,
            negative_score=0.05,
            reason="User asks for a camera",
            matches=[
                LeadMatchInput(
                    classifier_snapshot_entry_id=snapshot_entry_id,
                    catalog_term_id="term-1",
                    category_id=category_id,
                    match_type="term",
                    matched_text="камера",
                    score=0.9,
                )
            ],
        ),
    )
    cluster = service.assign_event_to_cluster(event.id, window_minutes=60)
    return event, cluster


def _insert_monitored_source(session) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(monitored_sources_table).values(
            id=row_id,
            source_kind="telegram_supergroup",
            input_ref="@test",
            source_purpose="lead_monitoring",
            priority="normal",
            status="active",
            lead_detection_enabled=True,
            catalog_ingestion_enabled=False,
            phase_enabled=True,
            start_mode="from_now",
            historical_backfill_policy="retro_web_only",
            poll_interval_seconds=60,
            added_by="test",
            created_at=now,
            updated_at=now,
        )
    )
    return row_id


def _insert_category(session) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(catalog_categories_table).values(
            id=row_id,
            parent_id=None,
            slug="video",
            name="Video",
            description=None,
            status="approved",
            sort_order=1,
            created_at=now,
            updated_at=now,
        )
    )
    return row_id


def _insert_source_message(session, source_id: str) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(source_messages_table).values(
            id=row_id,
            monitored_source_id=source_id,
            telegram_message_id=100,
            sender_id="sender-1",
            message_date=datetime(2026, 4, 28, 12, 0, 0),
            text="нужна камера на дачу",
            caption=None,
            normalized_text="нужна камера на дачу",
            has_media=False,
            media_metadata_json=None,
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
    return row_id


def _insert_classifier_version(session) -> str:
    row_id = new_id()
    session.execute(
        insert(classifier_versions_table).values(
            id=row_id,
            version=1,
            created_at=utc_now(),
            created_by="test",
            included_statuses_json=["approved", "auto_pending"],
            catalog_hash="catalog",
            example_hash="example",
            prompt_hash="prompt",
            keyword_index_hash="keyword",
            settings_hash="settings",
        )
    )
    return row_id


def _insert_snapshot_entry(session, classifier_version_id: str, category_id: str) -> str:
    row_id = new_id()
    session.execute(
        insert(classifier_snapshot_entries_table).values(
            id=row_id,
            classifier_version_id=classifier_version_id,
            entry_type="term",
            entity_type="term",
            entity_id="term-1",
            status_at_build="auto_pending",
            weight=1.5,
            text_value="камера",
            normalized_value="камера",
            metadata_json={"category_id": category_id},
            content_hash="hash",
            created_at=utc_now(),
        )
    )
    return row_id
