from datetime import timedelta

import pytest
from sqlalchemy import select

from pur_leads.core.time import utc_now
from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.audit import audit_log_table
from pur_leads.models.crm import (
    client_assets_table,
    client_interests_table,
    client_objects_table,
    clients_table,
    contact_reasons_table,
    contacts_table,
    touchpoints_table,
)
from pur_leads.services.crm import CrmService


@pytest.fixture
def crm_session(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        yield session


def test_create_client_profile_stores_crm_memory_and_audit(crm_session):
    due_at = utc_now() + timedelta(days=7)

    profile = CrmService(crm_session).create_client_profile(
        actor="admin",
        display_name="Иван Петров",
        client_type="person",
        notes="Ищет камеру для дачи",
        contacts=[
            {
                "contact_name": "Иван",
                "telegram_user_id": "100500",
                "telegram_username": "ivan_p",
                "phone": "+79990000000",
                "preferred_channel": "telegram",
                "is_primary": True,
            }
        ],
        objects=[
            {
                "object_type": "dacha",
                "name": "Дача",
                "location_text": "Ногинск",
                "project_stage": "operation",
            }
        ],
        interests=[
            {
                "interest_text": "Wi-Fi камера на дачу",
                "interest_status": "not_found",
                "next_check_at": due_at,
            }
        ],
        assets=[
            {
                "asset_name": "Старый роутер",
                "asset_status": "active",
                "service_due_at": due_at,
            }
        ],
        contact_reasons=[
            {
                "reason_type": "manual",
                "title": "Вернуться к камере",
                "reason_text": "Проверить, появилась ли подходящая камера",
                "priority": "normal",
                "due_at": due_at,
            }
        ],
        touchpoints=[
            {
                "channel": "telegram",
                "direction": "internal_note",
                "summary": "Создан вручную после разговора",
            }
        ],
    )

    client_row = crm_session.execute(select(clients_table)).mappings().one()
    contact_row = crm_session.execute(select(contacts_table)).mappings().one()
    object_row = crm_session.execute(select(client_objects_table)).mappings().one()
    interest_row = crm_session.execute(select(client_interests_table)).mappings().one()
    asset_row = crm_session.execute(select(client_assets_table)).mappings().one()
    reason_row = crm_session.execute(select(contact_reasons_table)).mappings().one()
    touchpoint_row = crm_session.execute(select(touchpoints_table)).mappings().one()
    audit_row = crm_session.execute(select(audit_log_table)).mappings().one()

    assert profile.client.id == client_row["id"]
    assert profile.contacts[0].id == contact_row["id"]
    assert profile.objects[0].id == object_row["id"]
    assert profile.interests[0].id == interest_row["id"]
    assert profile.assets[0].id == asset_row["id"]
    assert profile.contact_reasons[0].id == reason_row["id"]
    assert profile.touchpoints[0].id == touchpoint_row["id"]
    assert client_row["display_name"] == "Иван Петров"
    assert client_row["status"] == "active"
    assert client_row["source_type"] == "manual"
    assert contact_row["client_id"] == client_row["id"]
    assert contact_row["is_primary"] is True
    assert object_row["client_id"] == client_row["id"]
    assert interest_row["client_id"] == client_row["id"]
    assert interest_row["interest_status"] == "not_found"
    assert asset_row["client_id"] == client_row["id"]
    assert reason_row["client_id"] == client_row["id"]
    assert reason_row["status"] == "new"
    assert touchpoint_row["client_id"] == client_row["id"]
    assert audit_row["actor"] == "admin"
    assert audit_row["action"] == "crm.client_profile_created"
    assert audit_row["entity_type"] == "client"
    assert audit_row["entity_id"] == client_row["id"]


def test_duplicate_hints_match_contact_identity_fields(crm_session):
    service = CrmService(crm_session)
    profile = service.create_client_profile(
        actor="admin",
        display_name="Клиент с телеграмом",
        contacts=[
            {
                "telegram_user_id": "777",
                "telegram_username": "camera_user",
                "phone": "+79991112233",
                "email": "client@example.test",
            }
        ],
    )

    hints = service.find_duplicate_hints(
        telegram_user_id="777",
        telegram_username="@camera_user",
        phone="+7 (999) 111-22-33",
        email="CLIENT@example.test",
    )

    assert {(hint.match_type, hint.client_id) for hint in hints} == {
        ("telegram_user_id", profile.client.id),
        ("telegram_username", profile.client.id),
        ("phone", profile.client.id),
        ("email", profile.client.id),
    }
    assert all(hint.contact_id == profile.contacts[0].id for hint in hints)
