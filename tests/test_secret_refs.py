import pytest
from sqlalchemy import select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.audit import operational_events_table
from pur_leads.models.secrets import secret_refs_table
from pur_leads.services.secrets import SecretRefService


@pytest.fixture
def secret_service(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        yield SecretRefService(session), session


@pytest.mark.parametrize(
    "secret_type",
    ["telegram_session", "telegram_api", "ai_api_key", "web_session_secret"],
)
def test_create_secret_refs(secret_service, secret_type):
    service, session = secret_service

    secret_id = service.create_ref(
        secret_type=secret_type,
        display_name=f"{secret_type} ref",
        storage_backend="env",
        storage_ref=f"{secret_type.upper()}_REF",
    )

    row = session.execute(select(secret_refs_table)).mappings().one()
    assert row["id"] == secret_id
    assert row["secret_type"] == secret_type
    assert row["status"] == "active"


def test_public_view_does_not_expose_storage_ref(secret_service):
    service, _session = secret_service
    secret_id = service.create_ref(
        secret_type="ai_api_key",
        display_name="z.ai key",
        storage_backend="env",
        storage_ref="ZAI_API_KEY",
    )

    public_view = service.public_view(secret_id)

    assert public_view == {
        "id": secret_id,
        "secret_type": "ai_api_key",
        "display_name": "z.ai key",
        "storage_backend": "env",
        "status": "active",
    }


def test_mark_missing_updates_status_and_records_masked_event(secret_service):
    service, session = secret_service
    secret_id = service.create_ref(
        secret_type="telegram_session",
        display_name="main userbot",
        storage_backend="file",
        storage_ref="/tmp/userbot.session",
    )

    service.mark_missing(secret_id, checked_by="worker-a")

    secret_row = session.execute(select(secret_refs_table)).mappings().one()
    event_row = session.execute(select(operational_events_table)).mappings().one()
    assert secret_row["status"] == "missing"
    assert secret_row["last_checked_at"] is not None
    assert event_row["severity"] == "error"
    assert event_row["entity_type"] == "secret_ref"
    assert event_row["entity_id"] == secret_id
    assert event_row["details_json"] == {
        "checked_by": "worker-a",
        "display_name": "main userbot",
        "storage_backend": "file",
    }
