from datetime import datetime

import pytest
from sqlalchemy import event, insert, select

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.catalog import (
    catalog_categories_table,
    catalog_items_table,
    catalog_terms_table,
    classifier_snapshot_entries_table,
    classifier_versions_table,
)
from pur_leads.models.leads import feedback_events_table, lead_clusters_table
from pur_leads.models.telegram_sources import monitored_sources_table, source_messages_table
from pur_leads.services.lead_inbox import LeadInboxFilters, LeadInboxService, _limit
from pur_leads.services.leads import LeadDetectionResult, LeadMatchInput, LeadService


@pytest.fixture
def inbox_session(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        source_id = _insert_monitored_source(session, input_ref="@roof-chat")
        other_source_id = _insert_monitored_source(session, input_ref="@other-chat")
        camera_category_id = _insert_category(session, slug="video", name="Video")
        alarm_category_id = _insert_category(session, slug="alarm", name="Alarm")
        camera_item_id = _insert_item(session, camera_category_id, name="Camera Kit")
        alarm_item_id = _insert_item(session, alarm_category_id, name="Alarm Kit")
        camera_term_id = _insert_term(session, camera_category_id, camera_item_id, term="камера")
        alarm_term_id = _insert_term(session, alarm_category_id, alarm_item_id, term="сигнализация")
        classifier_version_id = _insert_classifier_version(session)
        camera_snapshot_id = _insert_snapshot_entry(
            session,
            classifier_version_id,
            entity_id=camera_term_id,
            category_id=camera_category_id,
            text_value="камера",
            status_at_build="auto_pending",
        )
        alarm_snapshot_id = _insert_snapshot_entry(
            session,
            classifier_version_id,
            entity_id=alarm_term_id,
            category_id=alarm_category_id,
            text_value="сигнализация",
            status_at_build="approved",
        )
        session.commit()
        yield {
            "session": session,
            "source_id": source_id,
            "other_source_id": other_source_id,
            "camera_category_id": camera_category_id,
            "alarm_category_id": alarm_category_id,
            "camera_item_id": camera_item_id,
            "alarm_item_id": alarm_item_id,
            "camera_term_id": camera_term_id,
            "alarm_term_id": alarm_term_id,
            "classifier_version_id": classifier_version_id,
            "camera_snapshot_id": camera_snapshot_id,
            "alarm_snapshot_id": alarm_snapshot_id,
        }


def test_list_cluster_queue_returns_rows_with_primary_message_evidence_and_flags(inbox_session):
    session = inbox_session["session"]
    cluster_id = _record_cluster(
        session,
        source_id=inbox_session["source_id"],
        classifier_version_id=inbox_session["classifier_version_id"],
        snapshot_entry_id=inbox_session["camera_snapshot_id"],
        category_id=inbox_session["camera_category_id"],
        item_id=inbox_session["camera_item_id"],
        term_id=inbox_session["camera_term_id"],
        telegram_message_id=100,
        sender_id="sender-1",
        text="нужна камера на дачу",
        message_date=datetime(2026, 4, 28, 12, 0, 0),
        confidence=0.91,
    )
    _record_event_into_cluster(
        session,
        source_id=inbox_session["source_id"],
        classifier_version_id=inbox_session["classifier_version_id"],
        snapshot_entry_id=inbox_session["camera_snapshot_id"],
        category_id=inbox_session["camera_category_id"],
        item_id=inbox_session["camera_item_id"],
        term_id=inbox_session["camera_term_id"],
        telegram_message_id=101,
        sender_id="sender-1",
        text="это ретро-проверка по камерам",
        message_date=datetime(2026, 4, 28, 12, 20, 0),
        detection_mode="retro_research",
    )
    _insert_feedback(session, target_type="lead_cluster", target_id=cluster_id)
    session.commit()

    rows = LeadInboxService(session).list_cluster_queue()

    assert len(rows) == 1
    row = rows[0]
    assert row.cluster_id == cluster_id
    assert row.status == "new"
    assert row.confidence == 0.91
    assert row.category == {"id": inbox_session["camera_category_id"], "name": "Video"}
    assert row.primary_message["text"] == "нужна камера на дачу"
    assert row.primary_message["telegram_message_id"] == 100
    assert row.matched_terms == [
        {
            "id": inbox_session["camera_term_id"],
            "text": "камера",
            "matched_text": "камера",
            "status_at_detection": "auto_pending",
        }
    ]
    assert row.matched_items == [
        {
            "id": inbox_session["camera_item_id"],
            "name": "Camera Kit",
            "status_at_detection": None,
        }
    ]
    assert row.is_retro is True
    assert row.is_maybe is False
    assert row.has_auto_pending is True
    assert row.has_auto_merge_pending is True
    assert row.event_count == 2
    assert row.feedback_count == 1


def test_list_cluster_queue_filters_status_source_category_retro_maybe_and_confidence(
    inbox_session,
):
    session = inbox_session["session"]
    _record_cluster(
        session,
        source_id=inbox_session["source_id"],
        classifier_version_id=inbox_session["classifier_version_id"],
        snapshot_entry_id=inbox_session["camera_snapshot_id"],
        category_id=inbox_session["camera_category_id"],
        item_id=inbox_session["camera_item_id"],
        term_id=inbox_session["camera_term_id"],
        telegram_message_id=200,
        sender_id="sender-1",
        text="нужна камера",
        message_date=datetime(2026, 4, 28, 12, 0, 0),
        confidence=0.91,
    )
    maybe_cluster_id = _record_cluster(
        session,
        source_id=inbox_session["other_source_id"],
        classifier_version_id=inbox_session["classifier_version_id"],
        snapshot_entry_id=inbox_session["alarm_snapshot_id"],
        category_id=inbox_session["alarm_category_id"],
        item_id=inbox_session["alarm_item_id"],
        term_id=inbox_session["alarm_term_id"],
        telegram_message_id=201,
        sender_id="sender-2",
        text="возможно нужна сигнализация",
        message_date=datetime(2026, 4, 28, 13, 0, 0),
        confidence=0.62,
        decision="maybe",
        detection_mode="retro_research",
    )
    session.commit()

    rows = LeadInboxService(session).list_cluster_queue(
        LeadInboxFilters(
            status="maybe",
            source_id=inbox_session["other_source_id"],
            category_id=inbox_session["alarm_category_id"],
            retro=True,
            maybe=True,
            min_confidence=0.6,
        )
    )

    assert [row.cluster_id for row in rows] == [maybe_cluster_id]


def test_list_cluster_queue_limits_latest_rows_before_expensive_row_mapping(inbox_session):
    session = inbox_session["session"]
    first_cluster_id = _record_cluster(
        session,
        source_id=inbox_session["source_id"],
        classifier_version_id=inbox_session["classifier_version_id"],
        snapshot_entry_id=inbox_session["camera_snapshot_id"],
        category_id=inbox_session["camera_category_id"],
        item_id=inbox_session["camera_item_id"],
        term_id=inbox_session["camera_term_id"],
        telegram_message_id=210,
        sender_id="sender-1",
        text="нужна камера первая",
        message_date=datetime(2026, 4, 28, 10, 0, 0),
        confidence=0.91,
    )
    second_cluster_id = _record_cluster(
        session,
        source_id=inbox_session["source_id"],
        classifier_version_id=inbox_session["classifier_version_id"],
        snapshot_entry_id=inbox_session["camera_snapshot_id"],
        category_id=inbox_session["camera_category_id"],
        item_id=inbox_session["camera_item_id"],
        term_id=inbox_session["camera_term_id"],
        telegram_message_id=211,
        sender_id="sender-2",
        text="нужна камера вторая",
        message_date=datetime(2026, 4, 28, 11, 0, 0),
        confidence=0.91,
    )
    third_cluster_id = _record_cluster(
        session,
        source_id=inbox_session["source_id"],
        classifier_version_id=inbox_session["classifier_version_id"],
        snapshot_entry_id=inbox_session["camera_snapshot_id"],
        category_id=inbox_session["camera_category_id"],
        item_id=inbox_session["camera_item_id"],
        term_id=inbox_session["camera_term_id"],
        telegram_message_id=212,
        sender_id="sender-3",
        text="нужна камера третья",
        message_date=datetime(2026, 4, 28, 12, 0, 0),
        confidence=0.91,
    )
    session.commit()

    rows = LeadInboxService(session).list_cluster_queue(LeadInboxFilters(limit=2))

    assert [row.cluster_id for row in rows] == [third_cluster_id, second_cluster_id]
    assert first_cluster_id not in {row.cluster_id for row in rows}


def test_list_cluster_queue_applies_expensive_filters_before_limit(inbox_session):
    session = inbox_session["session"]
    auto_pending_cluster_id = _record_cluster(
        session,
        source_id=inbox_session["source_id"],
        classifier_version_id=inbox_session["classifier_version_id"],
        snapshot_entry_id=inbox_session["camera_snapshot_id"],
        category_id=inbox_session["camera_category_id"],
        item_id=inbox_session["camera_item_id"],
        term_id=inbox_session["camera_term_id"],
        telegram_message_id=216,
        sender_id="sender-auto",
        text="нужна камера",
        message_date=datetime(2026, 4, 28, 10, 0, 0),
        confidence=0.91,
    )
    _record_cluster(
        session,
        source_id=inbox_session["source_id"],
        classifier_version_id=inbox_session["classifier_version_id"],
        snapshot_entry_id=inbox_session["alarm_snapshot_id"],
        category_id=inbox_session["alarm_category_id"],
        item_id=inbox_session["alarm_item_id"],
        term_id=inbox_session["alarm_term_id"],
        telegram_message_id=217,
        sender_id="sender-approved",
        text="нужна сигнализация",
        message_date=datetime(2026, 4, 28, 11, 0, 0),
        confidence=0.91,
    )
    session.commit()

    rows = LeadInboxService(session).list_cluster_queue(
        LeadInboxFilters(auto_pending=True, limit=1)
    )

    assert [row.cluster_id for row in rows] == [auto_pending_cluster_id]


def test_list_cluster_queue_supports_offset_pagination(inbox_session):
    session = inbox_session["session"]
    cluster_ids = [
        _record_cluster(
            session,
            source_id=inbox_session["source_id"],
            classifier_version_id=inbox_session["classifier_version_id"],
            snapshot_entry_id=inbox_session["camera_snapshot_id"],
            category_id=inbox_session["camera_category_id"],
            item_id=inbox_session["camera_item_id"],
            term_id=inbox_session["camera_term_id"],
            telegram_message_id=220 + index,
            sender_id=f"sender-{index}",
            text=f"нужна камера {index}",
            message_date=datetime(2026, 4, 28, 10 + index, 0, 0),
            confidence=0.91,
        )
        for index in range(4)
    ]
    session.commit()

    rows = LeadInboxService(session).list_cluster_queue(LeadInboxFilters(limit=2, offset=1))

    assert [row.cluster_id for row in rows] == [cluster_ids[2], cluster_ids[1]]


def test_list_cluster_queue_batches_page_enrichment_queries(inbox_session):
    session = inbox_session["session"]
    for index in range(5):
        cluster_id = _record_cluster(
            session,
            source_id=inbox_session["source_id"],
            classifier_version_id=inbox_session["classifier_version_id"],
            snapshot_entry_id=inbox_session["camera_snapshot_id"],
            category_id=inbox_session["camera_category_id"],
            item_id=inbox_session["camera_item_id"],
            term_id=inbox_session["camera_term_id"],
            telegram_message_id=240 + index,
            sender_id=f"sender-{index}",
            text=f"нужна камера {index}",
            message_date=datetime(2026, 4, 28, 10 + index, 0, 0),
            confidence=0.91,
        )
        _insert_feedback(session, target_type="lead_cluster", target_id=cluster_id)
    session.commit()

    statements: list[str] = []
    engine = session.get_bind()

    def capture_selects(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture_selects)
    try:
        rows = LeadInboxService(session).list_cluster_queue(LeadInboxFilters(limit=4))
    finally:
        event.remove(engine, "before_cursor_execute", capture_selects)

    assert len(rows) == 4
    assert len(statements) <= 8


def test_lead_inbox_limit_caps_large_client_requests():
    assert _limit(0) == 1
    assert _limit(100) == 100
    assert _limit(1000) == 100


def test_get_cluster_detail_returns_timeline_events_matches_and_feedback(inbox_session):
    session = inbox_session["session"]
    cluster_id = _record_cluster(
        session,
        source_id=inbox_session["source_id"],
        classifier_version_id=inbox_session["classifier_version_id"],
        snapshot_entry_id=inbox_session["camera_snapshot_id"],
        category_id=inbox_session["camera_category_id"],
        item_id=inbox_session["camera_item_id"],
        term_id=inbox_session["camera_term_id"],
        telegram_message_id=300,
        sender_id="sender-1",
        text="нужна камера",
        message_date=datetime(2026, 4, 28, 12, 0, 0),
        confidence=0.91,
    )
    feedback_id = _insert_feedback(session, target_type="lead_cluster", target_id=cluster_id)
    session.commit()

    detail = LeadInboxService(session).get_cluster_detail(cluster_id)

    assert detail.cluster.cluster_id == cluster_id
    assert [entry["kind"] for entry in detail.timeline] == ["message", "event", "feedback"]
    assert detail.timeline[0]["message"]["text"] == "нужна камера"
    assert len(detail.events) == 1
    assert detail.events[0]["decision"] == "lead"
    assert detail.matches == [
        {
            "event_id": detail.events[0]["id"],
            "match_type": "term",
            "matched_text": "камера",
            "score": 0.9,
            "catalog_item_id": inbox_session["camera_item_id"],
            "catalog_item_name": "Camera Kit",
            "catalog_term_id": inbox_session["camera_term_id"],
            "catalog_term_text": "камера",
            "category_id": inbox_session["camera_category_id"],
            "category_name": "Video",
            "status_at_detection": "auto_pending",
        }
    ]
    assert [feedback["id"] for feedback in detail.feedback] == [feedback_id]


def _record_cluster(
    session,
    *,
    source_id: str,
    classifier_version_id: str,
    snapshot_entry_id: str,
    category_id: str,
    item_id: str,
    term_id: str,
    telegram_message_id: int,
    sender_id: str,
    text: str,
    message_date: datetime,
    confidence: float,
    decision: str = "lead",
    detection_mode: str = "live",
) -> str:
    event = _record_event_into_cluster(
        session,
        source_id=source_id,
        classifier_version_id=classifier_version_id,
        snapshot_entry_id=snapshot_entry_id,
        category_id=category_id,
        item_id=item_id,
        term_id=term_id,
        telegram_message_id=telegram_message_id,
        sender_id=sender_id,
        text=text,
        message_date=message_date,
        confidence=confidence,
        decision=decision,
        detection_mode=detection_mode,
    )
    row = (
        session.execute(
            select(lead_clusters_table.c.id).where(
                lead_clusters_table.c.primary_lead_event_id == event.id
            )
        )
        .mappings()
        .one()
    )
    return row["id"]


def _record_event_into_cluster(
    session,
    *,
    source_id: str,
    classifier_version_id: str,
    snapshot_entry_id: str,
    category_id: str,
    item_id: str,
    term_id: str,
    telegram_message_id: int,
    sender_id: str,
    text: str,
    message_date: datetime,
    confidence: float = 0.77,
    decision: str = "lead",
    detection_mode: str = "live",
):
    message_id = _insert_source_message(
        session,
        source_id,
        telegram_message_id=telegram_message_id,
        sender_id=sender_id,
        text=text,
        message_date=message_date,
    )
    event = LeadService(session).record_detection(
        source_message_id=message_id,
        classifier_version_id=classifier_version_id,
        result=LeadDetectionResult(
            decision=decision,
            detection_mode=detection_mode,
            confidence=confidence,
            commercial_value_score=0.7,
            negative_score=0.05,
            reason="User asks for equipment",
            matches=[
                LeadMatchInput(
                    classifier_snapshot_entry_id=snapshot_entry_id,
                    catalog_item_id=item_id,
                    catalog_term_id=term_id,
                    category_id=category_id,
                    match_type="term",
                    matched_text="камера" if term_id else None,
                    score=0.9,
                )
            ],
        ),
    )
    LeadService(session).assign_event_to_cluster(event.id, window_minutes=60)
    return event


def _insert_monitored_source(session, *, input_ref: str) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(monitored_sources_table).values(
            id=row_id,
            source_kind="telegram_supergroup",
            input_ref=input_ref,
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


def _insert_category(session, *, slug: str, name: str) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(catalog_categories_table).values(
            id=row_id,
            parent_id=None,
            slug=slug,
            name=name,
            description=None,
            status="approved",
            sort_order=1,
            created_at=now,
            updated_at=now,
        )
    )
    return row_id


def _insert_item(session, category_id: str, *, name: str) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(catalog_items_table).values(
            id=row_id,
            category_id=category_id,
            item_type="product",
            name=name,
            canonical_name=name,
            description=None,
            status="approved",
            confidence=0.9,
            first_seen_source_id=None,
            first_seen_at=None,
            last_seen_at=None,
            created_by="test",
            created_at=now,
            updated_at=now,
        )
    )
    return row_id


def _insert_term(session, category_id: str, item_id: str, *, term: str) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(catalog_terms_table).values(
            id=row_id,
            item_id=item_id,
            category_id=category_id,
            term=term,
            normalized_term=term,
            term_type="keyword",
            language="ru",
            status="approved",
            weight=1.0,
            created_by="test",
            first_seen_source_id=None,
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
    text: str,
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
            text=text,
            caption=None,
            normalized_text=text,
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


def _insert_snapshot_entry(
    session,
    classifier_version_id: str,
    *,
    entity_id: str,
    category_id: str,
    text_value: str,
    status_at_build: str,
) -> str:
    row_id = new_id()
    session.execute(
        insert(classifier_snapshot_entries_table).values(
            id=row_id,
            classifier_version_id=classifier_version_id,
            entry_type="term",
            entity_type="term",
            entity_id=entity_id,
            status_at_build=status_at_build,
            weight=1.5,
            text_value=text_value,
            normalized_value=text_value,
            metadata_json={"category_id": category_id},
            content_hash=f"hash-{row_id}",
            created_at=utc_now(),
        )
    )
    return row_id


def _insert_feedback(session, *, target_type: str, target_id: str) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(feedback_events_table).values(
            id=row_id,
            target_type=target_type,
            target_id=target_id,
            action="lead_confirmed",
            reason_code=None,
            feedback_scope="classifier",
            learning_effect="positive_example",
            application_status="recorded",
            applied_entity_type=None,
            applied_entity_id=None,
            applied_at=None,
            comment="confirmed",
            created_by="test",
            created_at=now,
            metadata_json={},
        )
    )
    return row_id
