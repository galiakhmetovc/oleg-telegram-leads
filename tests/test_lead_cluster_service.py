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
    lead_cluster_actions_table,
    lead_cluster_members_table,
    lead_clusters_table,
    lead_events_table,
)
from pur_leads.models.telegram_sources import monitored_sources_table, source_messages_table
from pur_leads.services.leads import LeadDetectionResult, LeadMatchInput, LeadService


@pytest.fixture
def cluster_session(tmp_path):
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


def test_assign_event_to_cluster_creates_new_cluster(cluster_session):
    session, source_id, category_id, classifier_version_id, snapshot_entry_id = cluster_session
    message_id = _insert_source_message(
        session,
        source_id,
        telegram_message_id=100,
        sender_id="sender-1",
        message_date=datetime(2026, 4, 28, 12, 0, 0),
    )
    event = _record_event(
        session, message_id, classifier_version_id, snapshot_entry_id, category_id
    )

    cluster = LeadService(session).assign_event_to_cluster(event.id, window_minutes=60)

    cluster_row = session.execute(select(lead_clusters_table)).mappings().one()
    member_row = session.execute(select(lead_cluster_members_table)).mappings().one()
    event_row = session.execute(select(lead_events_table)).mappings().one()
    assert cluster.id == cluster_row["id"]
    assert cluster_row["cluster_status"] == "new"
    assert cluster_row["review_status"] == "unreviewed"
    assert cluster_row["primary_lead_event_id"] == event.id
    assert cluster_row["primary_source_message_id"] == message_id
    assert cluster_row["primary_sender_id"] == "sender-1"
    assert cluster_row["category_id"] == category_id
    assert cluster_row["message_count"] == 1
    assert cluster_row["lead_event_count"] == 1
    assert cluster_row["confidence_max"] == 0.91
    assert member_row["member_role"] == "primary"
    assert member_row["lead_event_id"] == event.id
    assert event_row["lead_cluster_id"] == cluster.id


def test_assign_event_to_cluster_auto_merges_same_sender_category_in_window(cluster_session):
    session, source_id, category_id, classifier_version_id, snapshot_entry_id = cluster_session
    first_message_id = _insert_source_message(
        session,
        source_id,
        telegram_message_id=100,
        sender_id="sender-1",
        message_date=datetime(2026, 4, 28, 12, 0, 0),
    )
    second_message_id = _insert_source_message(
        session,
        source_id,
        telegram_message_id=101,
        sender_id="sender-1",
        message_date=datetime(2026, 4, 28, 12, 20, 0),
    )
    first_event = _record_event(
        session,
        first_message_id,
        classifier_version_id,
        snapshot_entry_id,
        category_id,
        confidence=0.71,
    )
    second_event = _record_event(
        session,
        second_message_id,
        classifier_version_id,
        snapshot_entry_id,
        category_id,
        confidence=0.94,
    )
    service = LeadService(session)

    first_cluster = service.assign_event_to_cluster(first_event.id, window_minutes=60)
    second_cluster = service.assign_event_to_cluster(second_event.id, window_minutes=60)

    cluster_row = session.execute(select(lead_clusters_table)).mappings().one()
    member_rows = (
        session.execute(
            select(lead_cluster_members_table).order_by(lead_cluster_members_table.c.created_at)
        )
        .mappings()
        .all()
    )
    action_row = session.execute(select(lead_cluster_actions_table)).mappings().one()
    events = session.execute(select(lead_events_table)).mappings().all()
    assert second_cluster.id == first_cluster.id
    assert cluster_row["message_count"] == 2
    assert cluster_row["lead_event_count"] == 2
    assert cluster_row["confidence_max"] == 0.94
    assert cluster_row["last_message_at"] == datetime(2026, 4, 28, 12, 20, 0)
    assert [row["member_role"] for row in member_rows] == ["primary", "trigger"]
    assert action_row["action_type"] == "auto_merge"
    assert action_row["to_cluster_id"] == first_cluster.id
    assert action_row["lead_event_id"] == second_event.id
    assert {row["lead_cluster_id"] for row in events} == {first_cluster.id}


def _record_event(
    session,
    message_id: str,
    classifier_version_id: str,
    snapshot_entry_id: str,
    category_id: str,
    *,
    confidence: float = 0.91,
):
    return LeadService(session).record_detection(
        source_message_id=message_id,
        classifier_version_id=classifier_version_id,
        result=LeadDetectionResult(
            decision="lead",
            detection_mode="live",
            confidence=confidence,
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
            slug="video_surveillance",
            name="Video Surveillance",
            description=None,
            status="approved",
            sort_order=1,
            created_at=now,
            updated_at=now,
        )
    )
    return row_id


def _insert_source_message(
    session,
    source_id: str,
    *,
    telegram_message_id: int,
    sender_id: str,
    message_date: datetime,
) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(source_messages_table).values(
            id=row_id,
            monitored_source_id=source_id,
            telegram_message_id=telegram_message_id,
            sender_id=sender_id,
            message_date=message_date,
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
            classification_status="pending",
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
