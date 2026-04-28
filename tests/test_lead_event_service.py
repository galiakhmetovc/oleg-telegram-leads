from datetime import datetime

import pytest
from sqlalchemy import insert, select

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.catalog import classifier_snapshot_entries_table, classifier_versions_table
from pur_leads.models.leads import lead_events_table, lead_matches_table
from pur_leads.models.telegram_sources import monitored_sources_table, source_messages_table
from pur_leads.services.leads import LeadDetectionResult, LeadMatchInput, LeadService


@pytest.fixture
def lead_session(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        source_id = _insert_monitored_source(session)
        message_id = _insert_source_message(session, source_id)
        classifier_version_id = _insert_classifier_version(session)
        snapshot_entry_id = _insert_snapshot_entry(session, classifier_version_id)
        session.commit()
        yield session, source_id, message_id, classifier_version_id, snapshot_entry_id


def test_record_lead_event_with_match_evidence(lead_session):
    session, source_id, message_id, classifier_version_id, snapshot_entry_id = lead_session
    service = LeadService(session)

    event = service.record_detection(
        source_message_id=message_id,
        classifier_version_id=classifier_version_id,
        result=LeadDetectionResult(
            decision="lead",
            detection_mode="live",
            confidence=0.91,
            commercial_value_score=0.7,
            negative_score=0.05,
            reason="User asks for a camera",
            matches=[
                LeadMatchInput(
                    classifier_snapshot_entry_id=snapshot_entry_id,
                    catalog_term_id="term-1",
                    category_id="category-1",
                    match_type="term",
                    matched_text="камера",
                    score=0.9,
                )
            ],
        ),
    )

    event_row = session.execute(select(lead_events_table)).mappings().one()
    match_row = session.execute(select(lead_matches_table)).mappings().one()
    assert event.id == event_row["id"]
    assert event_row["source_message_id"] == message_id
    assert event_row["monitored_source_id"] == source_id
    assert event_row["telegram_message_id"] == 100
    assert event_row["message_text"] == "нужна камера на дачу"
    assert event_row["decision"] == "lead"
    assert event_row["event_status"] == "active"
    assert match_row["lead_event_id"] == event.id
    assert match_row["classifier_snapshot_entry_id"] == snapshot_entry_id
    assert match_row["term_status_at_detection"] == "auto_pending"
    assert match_row["matched_weight"] == 1.5
    assert match_row["matched_status_snapshot"] == {
        "entry_type": "term",
        "status_at_build": "auto_pending",
    }


def test_record_detection_deduplicates_same_message_classifier_and_mode(lead_session):
    session, _, message_id, classifier_version_id, snapshot_entry_id = lead_session
    service = LeadService(session)
    result = LeadDetectionResult(
        decision="maybe",
        detection_mode="live",
        confidence=0.55,
        matches=[
            LeadMatchInput(
                classifier_snapshot_entry_id=snapshot_entry_id,
                match_type="term",
                matched_text="камера",
                score=0.5,
            )
        ],
    )

    first = service.record_detection(
        source_message_id=message_id,
        classifier_version_id=classifier_version_id,
        result=result,
    )
    second = service.record_detection(
        source_message_id=message_id,
        classifier_version_id=classifier_version_id,
        result=result,
    )

    assert second.id == first.id
    assert len(session.execute(select(lead_events_table)).all()) == 1
    assert len(session.execute(select(lead_matches_table)).all()) == 1


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


def _insert_snapshot_entry(session, classifier_version_id: str) -> str:
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
            metadata_json={"category_id": "category-1"},
            content_hash="hash",
            created_at=utc_now(),
        )
    )
    return row_id
