from datetime import datetime

import pytest
from sqlalchemy import func, insert, select

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
from pur_leads.models.crm import client_interests_table, clients_table, contacts_table
from pur_leads.models.leads import crm_conversion_actions_table, lead_clusters_table
from pur_leads.models.tasks import tasks_table
from pur_leads.models.telegram_sources import monitored_sources_table, source_messages_table
from pur_leads.services.crm import CrmService
from pur_leads.services.leads import LeadDetectionResult, LeadMatchInput, LeadService


@pytest.fixture
def conversion_session(tmp_path):
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


def test_convert_lead_cluster_creates_crm_memory_task_and_action(conversion_session):
    session, source_id, category_id, classifier_version_id, snapshot_entry_id = conversion_session
    event, cluster = _create_clustered_event(
        session,
        source_id,
        category_id,
        classifier_version_id,
        snapshot_entry_id,
    )

    result = CrmService(session).convert_lead_cluster(
        cluster.id,
        actor="admin",
        client={"display_name": "Иван с дачей", "client_type": "person"},
        contact={
            "contact_name": "Иван",
            "telegram_user_id": "sender-1",
            "telegram_username": "ivan_camera",
        },
        client_object={
            "object_type": "dacha",
            "name": "Дача",
            "location_text": "Ногинск",
            "project_stage": "operation",
        },
        interest={"interest_text": "Нужна камера на дачу", "interest_status": "interested"},
        task={"title": "Связаться по камере", "description": "Уточнить объект и бюджет"},
    )

    cluster_row = (
        session.execute(select(lead_clusters_table).where(lead_clusters_table.c.id == cluster.id))
        .mappings()
        .one()
    )
    client_row = session.execute(select(clients_table)).mappings().one()
    contact_row = session.execute(select(contacts_table)).mappings().one()
    interest_row = session.execute(select(client_interests_table)).mappings().one()
    task_row = session.execute(select(tasks_table)).mappings().one()
    action_row = session.execute(select(crm_conversion_actions_table)).mappings().one()

    assert result.client.id == client_row["id"]
    assert result.primary_entity_type == "client_interest"
    assert result.primary_entity_id == interest_row["id"]
    assert result.task.id == task_row["id"]
    assert result.action.id == action_row["id"]
    assert contact_row["client_id"] == client_row["id"]
    assert interest_row["client_id"] == client_row["id"]
    assert interest_row["source_type"] == "lead"
    assert interest_row["source_id"] == cluster.id
    assert task_row["client_id"] == client_row["id"]
    assert task_row["lead_cluster_id"] == cluster.id
    assert task_row["lead_event_id"] == event.id
    assert cluster_row["cluster_status"] == "converted"
    assert cluster_row["review_status"] == "confirmed"
    assert cluster_row["work_outcome"] == "client_interest_created"
    assert cluster_row["converted_entity_type"] == "client_interest"
    assert cluster_row["converted_entity_id"] == interest_row["id"]
    assert cluster_row["crm_conversion_action_id"] == action_row["id"]
    assert cluster_row["primary_task_id"] == task_row["id"]
    assert action_row["action_type"] == "create_interest"
    assert action_row["created_entity_type"] == "client_interest"
    assert action_row["created_entity_id"] == interest_row["id"]
    assert action_row["linked_client_id"] == client_row["id"]


def test_convert_lead_cluster_blocks_duplicate_contact_unless_linked(conversion_session):
    session, source_id, category_id, classifier_version_id, snapshot_entry_id = conversion_session
    existing = CrmService(session).create_client_profile(
        actor="admin",
        display_name="Существующий клиент",
        contacts=[{"telegram_user_id": "sender-1"}],
    )
    _event, cluster = _create_clustered_event(
        session,
        source_id,
        category_id,
        classifier_version_id,
        snapshot_entry_id,
        telegram_message_id=101,
    )
    service = CrmService(session)

    with pytest.raises(ValueError, match="duplicate"):
        service.convert_lead_cluster(
            cluster.id,
            actor="admin",
            client={"display_name": "Новый клиент"},
            contact={"telegram_user_id": "sender-1"},
            interest={"interest_text": "Камера"},
        )

    result = service.convert_lead_cluster(
        cluster.id,
        actor="admin",
        link_existing_client_id=existing.client.id,
        contact={"telegram_user_id": "sender-1"},
        interest={"interest_text": "Камера"},
    )

    assert result.client.id == existing.client.id
    assert session.scalar(select(func.count()).select_from(clients_table)) == 1
    assert session.scalar(select(func.count()).select_from(contacts_table)) == 1
    assert session.scalar(select(func.count()).select_from(client_interests_table)) == 1
    assert result.primary_entity_type == "client_interest"


def _create_clustered_event(
    session,
    source_id: str,
    category_id: str,
    classifier_version_id: str,
    snapshot_entry_id: str,
    *,
    telegram_message_id: int = 100,
):
    message_id = _insert_source_message(session, source_id, telegram_message_id)
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


def _insert_source_message(session, source_id: str, telegram_message_id: int) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(source_messages_table).values(
            id=row_id,
            monitored_source_id=source_id,
            telegram_message_id=telegram_message_id,
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
            raw_metadata_json={"sender_name": "Иван"},
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
