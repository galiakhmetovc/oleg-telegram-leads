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
    feedback_events_table,
    lead_cluster_actions_table,
    lead_cluster_members_table,
    lead_clusters_table,
    lead_events_table,
    lead_matches_table,
)
from pur_leads.models.telegram_sources import monitored_sources_table, source_messages_table
from pur_leads.services.leads import LeadDetectionResult, LeadMatchInput, LeadService


@pytest.fixture
def feedback_session(tmp_path):
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


def test_record_feedback_requires_reason_and_supports_narrow_targets(feedback_session):
    session, source_id, category_id, classifier_version_id, snapshot_entry_id = feedback_session
    event, cluster = _create_clustered_event(
        session,
        source_id,
        category_id,
        classifier_version_id,
        snapshot_entry_id,
        telegram_message_id=200,
    )
    match_id = session.execute(
        select(lead_matches_table.c.id).where(lead_matches_table.c.lead_event_id == event.id)
    ).scalar_one()
    service = LeadService(session)

    with pytest.raises(ValueError, match="reason_code"):
        service.record_feedback(
            target_type="lead_cluster",
            target_id=cluster.id,
            action="not_lead",
            created_by="oleg",
        )

    feedback = service.record_feedback(
        target_type="lead_match",
        target_id=match_id,
        action="wrong_product_or_term",
        reason_code="wrong_product_or_term",
        feedback_scope="classifier",
        learning_effect="match_correction",
        created_by="oleg",
        comment="Matched term is too broad here",
    )
    commercial = service.record_feedback(
        target_type="lead_cluster",
        target_id=cluster.id,
        action="commercial_too_expensive",
        created_by="oleg",
    )

    feedback_row = (
        session.execute(
            select(feedback_events_table).where(feedback_events_table.c.id == feedback.id)
        )
        .mappings()
        .one()
    )
    commercial_row = (
        session.execute(
            select(feedback_events_table).where(feedback_events_table.c.id == commercial.id)
        )
        .mappings()
        .one()
    )
    assert feedback_row["target_type"] == "lead_match"
    assert feedback_row["target_id"] == match_id
    assert feedback_row["feedback_scope"] == "classifier"
    assert feedback_row["learning_effect"] == "match_correction"
    assert feedback_row["application_status"] == "recorded"
    assert feedback_row["comment"] == "Matched term is too broad here"
    assert commercial_row["feedback_scope"] == "crm_outcome"
    assert commercial_row["learning_effect"] == "no_classifier_learning"


def test_apply_cluster_review_actions_updates_state_and_feedback(feedback_session):
    session, source_id, category_id, classifier_version_id, snapshot_entry_id = feedback_session
    service = LeadService(session)
    confirmed_event, confirmed_cluster = _create_clustered_event(
        session,
        source_id,
        category_id,
        classifier_version_id,
        snapshot_entry_id,
        telegram_message_id=210,
    )
    not_lead_event, not_lead_cluster = _create_clustered_event(
        session,
        source_id,
        category_id,
        classifier_version_id,
        snapshot_entry_id,
        telegram_message_id=211,
    )
    maybe_event, maybe_cluster = _create_clustered_event(
        session,
        source_id,
        category_id,
        classifier_version_id,
        snapshot_entry_id,
        telegram_message_id=212,
    )

    confirmed_feedback = service.apply_cluster_action(
        confirmed_cluster.id,
        action="lead_confirmed",
        actor="oleg",
    )
    with pytest.raises(ValueError, match="reason_code"):
        service.apply_cluster_action(
            not_lead_cluster.id,
            action="not_lead",
            actor="oleg",
        )
    not_lead_feedback = service.apply_cluster_action(
        not_lead_cluster.id,
        action="not_lead",
        actor="oleg",
        reason_code="no_buying_intent",
    )
    maybe_feedback = service.apply_cluster_action(
        maybe_cluster.id,
        action="maybe",
        actor="oleg",
    )

    clusters = {
        row["id"]: row for row in session.execute(select(lead_clusters_table)).mappings().all()
    }
    feedback_rows = {
        row["id"]: row for row in session.execute(select(feedback_events_table)).mappings().all()
    }
    assert clusters[confirmed_cluster.id]["cluster_status"] == "in_work"
    assert clusters[confirmed_cluster.id]["review_status"] == "confirmed"
    assert feedback_rows[confirmed_feedback.id]["action"] == "lead_confirmed"
    assert feedback_rows[confirmed_feedback.id]["feedback_scope"] == "classifier"
    assert feedback_rows[confirmed_feedback.id]["learning_effect"] == "positive_example"
    assert feedback_rows[confirmed_feedback.id]["application_status"] == "applied"
    assert clusters[not_lead_cluster.id]["cluster_status"] == "not_lead"
    assert clusters[not_lead_cluster.id]["review_status"] == "rejected"
    assert feedback_rows[not_lead_feedback.id]["reason_code"] == "no_buying_intent"
    assert feedback_rows[not_lead_feedback.id]["learning_effect"] == "negative_example"
    assert clusters[maybe_cluster.id]["cluster_status"] == "maybe"
    assert clusters[maybe_cluster.id]["review_status"] == "needs_more_info"
    assert feedback_rows[maybe_feedback.id]["feedback_scope"] == "none"
    assert feedback_rows[maybe_feedback.id]["learning_effect"] == "no_classifier_learning"
    assert confirmed_event.id != not_lead_event.id
    assert maybe_event.id != confirmed_event.id


def test_apply_operational_cluster_actions_snooze_duplicate_and_context(feedback_session):
    session, source_id, category_id, classifier_version_id, snapshot_entry_id = feedback_session
    service = LeadService(session)
    _, target_cluster = _create_clustered_event(
        session,
        source_id,
        category_id,
        classifier_version_id,
        snapshot_entry_id,
        telegram_message_id=220,
    )
    _, snoozed_cluster = _create_clustered_event(
        session,
        source_id,
        category_id,
        classifier_version_id,
        snapshot_entry_id,
        telegram_message_id=221,
    )
    _, duplicate_cluster = _create_clustered_event(
        session,
        source_id,
        category_id,
        classifier_version_id,
        snapshot_entry_id,
        telegram_message_id=222,
    )
    context_event, context_cluster = _create_clustered_event(
        session,
        source_id,
        category_id,
        classifier_version_id,
        snapshot_entry_id,
        telegram_message_id=223,
    )
    snoozed_until = datetime(2026, 5, 1, 9, 30, 0)

    snooze_feedback = service.apply_cluster_action(
        snoozed_cluster.id,
        action="snooze",
        actor="oleg",
        snoozed_until=snoozed_until,
    )
    duplicate_feedback = service.apply_cluster_action(
        duplicate_cluster.id,
        action="duplicate",
        actor="oleg",
        duplicate_of_cluster_id=target_cluster.id,
    )
    context_feedback = service.apply_cluster_action(
        context_cluster.id,
        action="mark_context_only",
        actor="oleg",
        lead_event_id=context_event.id,
        reason_code="context_only",
    )

    clusters = {
        row["id"]: row for row in session.execute(select(lead_clusters_table)).mappings().all()
    }
    action_rows = session.execute(select(lead_cluster_actions_table)).mappings().all()
    feedback_rows = {
        row["id"]: row for row in session.execute(select(feedback_events_table)).mappings().all()
    }
    context_event_row = (
        session.execute(select(lead_events_table).where(lead_events_table.c.id == context_event.id))
        .mappings()
        .one()
    )
    context_member_row = (
        session.execute(
            select(lead_cluster_members_table).where(
                lead_cluster_members_table.c.lead_event_id == context_event.id
            )
        )
        .mappings()
        .one()
    )

    assert clusters[snoozed_cluster.id]["cluster_status"] == "snoozed"
    assert clusters[snoozed_cluster.id]["snoozed_until"] == snoozed_until
    assert feedback_rows[snooze_feedback.id]["feedback_scope"] == "none"
    assert clusters[duplicate_cluster.id]["cluster_status"] == "duplicate"
    assert clusters[duplicate_cluster.id]["duplicate_of_cluster_id"] == target_cluster.id
    assert feedback_rows[duplicate_feedback.id]["feedback_scope"] == "clustering"
    assert context_event_row["event_status"] == "context_only"
    assert context_member_row["member_role"] == "context"
    assert feedback_rows[context_feedback.id]["feedback_scope"] == "clustering"
    assert feedback_rows[context_feedback.id]["learning_effect"] == "cluster_training"
    assert {(row["action_type"], row["to_cluster_id"]) for row in action_rows} == {
        ("mark_duplicate", target_cluster.id),
        ("mark_context_only", context_cluster.id),
    }


def _create_clustered_event(
    session,
    source_id: str,
    category_id: str,
    classifier_version_id: str,
    snapshot_entry_id: str,
    *,
    telegram_message_id: int,
):
    message_id = _insert_source_message(
        session,
        source_id,
        telegram_message_id=telegram_message_id,
        sender_id=f"sender-{telegram_message_id}",
        message_date=datetime(2026, 4, 28, 12, telegram_message_id % 50, 0),
    )
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
