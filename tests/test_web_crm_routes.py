from datetime import datetime

from fastapi.testclient import TestClient
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
from pur_leads.models.leads import lead_clusters_table
from pur_leads.models.telegram_sources import monitored_sources_table, source_messages_table
from pur_leads.services.leads import LeadDetectionResult, LeadMatchInput, LeadService
from pur_leads.services.web_auth import WebAuthService
from pur_leads.web.app import create_app


def test_crm_client_routes_require_auth_and_manage_profiles(tmp_path):
    fixture = _setup_app(tmp_path)
    client = fixture["client"]

    denied_response = client.get("/api/crm/clients")
    _login(client)
    create_response = client.post(
        "/api/crm/clients",
        json={
            "display_name": "Иван Петров",
            "client_type": "person",
            "notes": "Дача",
            "contacts": [{"telegram_user_id": "42", "telegram_username": "@ivan"}],
            "objects": [{"object_type": "dacha", "name": "Дача"}],
            "interests": [{"interest_text": "Камера на дачу", "interest_status": "not_found"}],
            "contact_reasons": [
                {
                    "reason_type": "manual",
                    "title": "Проверить новые камеры",
                    "reason_text": "Вернуться, когда появится подходящая модель",
                }
            ],
        },
    )
    list_response = client.get("/api/crm/clients")
    client_id = create_response.json()["client"]["id"]
    detail_response = client.get(f"/api/crm/clients/{client_id}")

    assert denied_response.status_code == 401
    assert create_response.status_code == 200
    assert create_response.json()["client"]["display_name"] == "Иван Петров"
    assert create_response.json()["contacts"][0]["telegram_username"] == "ivan"
    assert list_response.status_code == 200
    assert [row["id"] for row in list_response.json()["items"]] == [client_id]
    assert detail_response.status_code == 200
    assert detail_response.json()["interests"][0]["interest_status"] == "not_found"
    assert detail_response.json()["contact_reasons"][0]["status"] == "new"


def test_lead_cluster_crm_conversion_route(tmp_path):
    fixture = _setup_app(tmp_path)
    client = fixture["client"]
    _login(client)

    convert_response = client.post(
        f"/api/leads/{fixture['cluster_id']}/crm/convert",
        json={
            "client": {"display_name": "Клиент из лида", "client_type": "person"},
            "contact": {"telegram_user_id": "sender-1"},
            "client_object": {"object_type": "dacha", "name": "Дача"},
            "interest": {"interest_text": "Нужна камера на дачу"},
            "task": {"title": "Связаться по камере"},
        },
    )

    assert convert_response.status_code == 200
    payload = convert_response.json()
    assert payload["primary_entity_type"] == "client_interest"
    assert payload["client"]["display_name"] == "Клиент из лида"
    assert payload["task"]["status"] == "open"

    with fixture["session_factory"]() as session:
        cluster = (
            session.execute(
                select(lead_clusters_table).where(lead_clusters_table.c.id == fixture["cluster_id"])
            )
            .mappings()
            .one()
        )
    assert cluster["cluster_status"] == "converted"
    assert cluster["converted_entity_type"] == "client_interest"


def _setup_app(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        WebAuthService(session, telegram_bot_token="telegram-token").ensure_bootstrap_admin(
            username="admin",
            password="initial-secret",
        )
        source_id = _insert_monitored_source(session)
        category_id = _insert_category(session)
        classifier_version_id = _insert_classifier_version(session)
        snapshot_entry_id = _insert_snapshot_entry(session, classifier_version_id, category_id)
        _event, cluster = _create_clustered_event(
            session,
            source_id,
            category_id,
            classifier_version_id,
            snapshot_entry_id,
        )
        session.commit()
    return {
        "client": TestClient(
            create_app(
                database_path=db_path,
                bootstrap_admin_password="initial-secret",
                bootstrap_admin_password_file=tmp_path / "bootstrap-admin-password.txt",
                telegram_bot_token="telegram-token",
            )
        ),
        "session_factory": session_factory,
        "cluster_id": cluster.id,
    }


def _login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/local",
        json={"username": "admin", "password": "initial-secret"},
    )
    assert response.status_code == 200


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
