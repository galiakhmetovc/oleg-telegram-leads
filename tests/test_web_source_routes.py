from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import insert, select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.scheduler import scheduler_jobs_table
from pur_leads.models.telegram_sources import monitored_sources_table, source_preview_messages_table
from pur_leads.services.telegram_sources import TelegramSourceService
from pur_leads.services.web_auth import WebAuthService
from pur_leads.web.app import create_app


def test_source_routes_require_auth_create_and_return_detail(tmp_path):
    fixture = _setup_app(tmp_path)
    client = fixture["client"]

    denied_response = client.get("/api/sources")
    _login(client)
    create_response = client.post(
        "/api/sources",
        json={"input_ref": "https://t.me/example_chat", "purpose": "lead_monitoring"},
    )
    list_response = client.get("/api/sources")
    source_id = create_response.json()["source"]["id"]
    detail_response = client.get(f"/api/sources/{source_id}")

    assert denied_response.status_code == 401
    assert create_response.status_code == 200
    assert create_response.json()["source"]["status"] == "checking_access"
    assert create_response.json()["source"]["username"] == "example_chat"
    assert create_response.json()["access_job"]["job_type"] == "check_source_access"
    assert list_response.status_code == 200
    assert [row["id"] for row in list_response.json()["items"]] == [source_id]
    assert detail_response.status_code == 200
    assert detail_response.json()["source"]["id"] == source_id
    assert [job["job_type"] for job in detail_response.json()["jobs"]] == ["check_source_access"]


def test_source_action_routes_preview_activate_pause_and_reset_checkpoint(tmp_path):
    fixture = _setup_app(tmp_path)
    client = fixture["client"]
    _login(client)
    with fixture["session_factory"]() as session:
        source = TelegramSourceService(session).create_draft("@example", added_by="admin")
        _insert_preview_message(session, source.id)

    early_preview_response = client.post(f"/api/sources/{source.id}/preview", json={"limit": 3})
    with fixture["session_factory"]() as session:
        TelegramSourceService(session).set_status(source.id, "preview_ready", actor="system")

    preview_response = client.post(f"/api/sources/{source.id}/preview", json={"limit": 3})
    activate_response = client.post(f"/api/sources/{source.id}/activate")
    reset_denied_response = client.post(
        f"/api/sources/{source.id}/checkpoint",
        json={"message_id": 50, "confirm": False},
    )
    reset_response = client.post(
        f"/api/sources/{source.id}/checkpoint",
        json={"message_id": 50, "confirm": True},
    )
    pause_response = client.post(f"/api/sources/{source.id}/pause")
    detail_response = client.get(f"/api/sources/{source.id}")

    assert early_preview_response.status_code == 400
    assert preview_response.status_code == 200
    assert preview_response.json()["job"]["job_type"] == "fetch_source_preview"
    assert activate_response.status_code == 200
    assert activate_response.json()["source"]["status"] == "active"
    assert activate_response.json()["poll_job"]["job_type"] == "poll_monitored_source"
    assert reset_denied_response.status_code == 400
    assert reset_response.status_code == 200
    assert reset_response.json()["source"]["checkpoint_message_id"] == 50
    assert pause_response.status_code == 200
    assert pause_response.json()["source"]["status"] == "paused"
    assert detail_response.status_code == 200
    assert detail_response.json()["preview_messages"][0]["text"] == "preview text"

    with fixture["session_factory"]() as session:
        source_row = session.execute(select(monitored_sources_table)).mappings().one()
        jobs = session.execute(select(scheduler_jobs_table)).mappings().all()
    assert source_row["status"] == "paused"
    assert [job["job_type"] for job in jobs] == [
        "fetch_source_preview",
        "poll_monitored_source",
    ]


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
    return {
        "client": TestClient(create_app(database_path=db_path, telegram_bot_token="telegram-token")),
        "session_factory": session_factory,
    }


def _login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/local",
        json={"username": "admin", "password": "initial-secret"},
    )
    assert response.status_code == 200


def _insert_preview_message(session, source_id: str) -> None:
    session.execute(
        insert(source_preview_messages_table).values(
            id="preview-1",
            monitored_source_id=source_id,
            access_check_id=None,
            telegram_message_id=10,
            message_date=datetime(2026, 4, 28, 12, 0, 0),
            sender_display="Sender",
            text="preview text",
            caption=None,
            has_media=False,
            media_metadata_json=None,
            sort_order=0,
            created_at=datetime(2026, 4, 28, 12, 0, 0),
        )
    )
    session.commit()
