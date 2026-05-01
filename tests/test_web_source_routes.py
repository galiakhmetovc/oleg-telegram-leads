from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import insert, select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.scheduler import scheduler_jobs_table
from pur_leads.models.telegram_sources import (
    monitored_sources_table,
    source_access_checks_table,
    source_preview_messages_table,
)
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
        json={
            "input_ref": "https://t.me/example_chat",
            "purpose": "lead_monitoring",
            "start_recent_days": 183,
        },
    )
    list_response = client.get("/api/sources")
    source_id = create_response.json()["source"]["id"]
    detail_response = client.get(f"/api/sources/{source_id}")

    assert denied_response.status_code == 401
    assert create_response.status_code == 200
    assert create_response.json()["source"]["status"] == "checking_access"
    assert create_response.json()["source"]["username"] == "example_chat"
    assert create_response.json()["source"]["start_mode"] == "recent_days"
    assert create_response.json()["source"]["start_recent_days"] == 183
    assert create_response.json()["access_job"]["job_type"] == "check_source_access"
    assert list_response.status_code == 200
    assert [row["id"] for row in list_response.json()["items"]] == [source_id]
    assert detail_response.status_code == 200
    assert detail_response.json()["source"]["id"] == source_id
    assert [job["job_type"] for job in detail_response.json()["jobs"]] == ["check_source_access"]


def test_source_routes_allow_catalog_source_from_beginning(tmp_path):
    fixture = _setup_app(tmp_path)
    client = fixture["client"]
    _login(client)

    create_response = client.post(
        "/api/sources",
        json={
            "input_ref": "https://t.me/purmaster",
            "purpose": "catalog_ingestion",
            "start_mode": "from_beginning",
            "check_access": False,
        },
    )

    assert create_response.status_code == 200
    assert create_response.json()["source"]["username"] == "purmaster"
    assert create_response.json()["source"]["start_mode"] == "from_beginning"
    assert create_response.json()["source"]["checkpoint_message_id"] is None
    assert create_response.json()["access_job"] is None


def test_source_detail_explains_public_read_without_join(tmp_path):
    fixture = _setup_app(tmp_path)
    client = fixture["client"]
    _login(client)
    with fixture["session_factory"]() as session:
        source = TelegramSourceService(session).create_draft(
            "https://t.me/purmaster",
            purpose="catalog_ingestion",
            added_by="admin",
        )
        session.execute(
            insert(source_access_checks_table).values(
                id="access-1",
                monitored_source_id=source.id,
                userbot_account_id=None,
                check_type="onboarding",
                status="succeeded",
                resolved_source_kind="telegram_channel",
                resolved_telegram_id="2384235784",
                resolved_title="ПУР: всё по уму",
                last_message_id=168,
                can_read_messages=True,
                can_read_history=True,
                flood_wait_seconds=None,
                error=None,
                checked_at=datetime(2026, 4, 28, 12, 0, 0),
            )
        )
        session.commit()

    detail_response = client.get(f"/api/sources/{source.id}")
    payload = detail_response.json()

    assert detail_response.status_code == 200
    assert payload["access_summary"]["mode"] == "public_read_without_join"
    assert payload["access_summary"]["label"] == "Публичное чтение без вступления"
    assert payload["access_summary"]["requires_join"] is False
    assert payload["access_checks"][0]["access_mode"] == "public_read_without_join"
    assert payload["access_checks"][0]["access_label"] == "Публичное чтение без вступления"


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


def test_source_raw_ingest_enqueues_one_shot_job_without_activating_source(tmp_path):
    fixture = _setup_app(tmp_path)
    client = fixture["client"]
    _login(client)
    with fixture["session_factory"]() as session:
        source = TelegramSourceService(session).create_draft(
            "https://t.me/purmaster",
            purpose="catalog_ingestion",
            added_by="admin",
        )

    response = client.post(f"/api/sources/{source.id}/raw-ingest", json={"limit": 50})
    detail_response = client.get(f"/api/sources/{source.id}")

    assert response.status_code == 200
    assert response.json()["source"]["status"] == "draft"
    assert response.json()["raw_ingest_job"]["job_type"] == "ingest_telegram_raw"
    assert response.json()["raw_ingest_job"]["payload_json"] == {
        "limit": 50,
        "mode": "raw_only",
        "requested_by": "admin",
        "enqueue_classification": False,
    }
    assert detail_response.json()["jobs"][0]["job_type"] == "ingest_telegram_raw"
    with fixture["session_factory"]() as session:
        source_row = session.execute(select(monitored_sources_table)).mappings().one()
        job = session.execute(select(scheduler_jobs_table)).mappings().one()
    assert source_row["status"] == "draft"
    assert source_row["checkpoint_message_id"] is None
    assert job["status"] == "queued"
    assert job["idempotency_key"] == f"source:{source.id}:raw-ingest"


def test_source_raw_export_route_enqueues_configured_export_job(tmp_path):
    fixture = _setup_app(tmp_path)
    client = fixture["client"]
    _login(client)
    with fixture["session_factory"]() as session:
        source = TelegramSourceService(session).create_draft(
            "https://t.me/purmaster",
            purpose="catalog_ingestion",
            added_by="admin",
            start_mode="from_beginning",
        )

    response = client.post(
        f"/api/sources/{source.id}/raw-export",
        json={
            "range_mode": "recent_days",
            "recent_days": 180,
            "batch_size": 500,
            "max_messages": 1200,
            "media_enabled": True,
            "media_types": ["document", "photo"],
            "max_media_size_bytes": 10485760,
        },
    )

    assert response.status_code == 200
    job = response.json()["raw_export_job"]
    assert job["job_type"] == "export_telegram_raw"
    assert job["payload_json"] == {
        "requested_by": "admin",
        "range": {
            "mode": "recent_days",
            "recent_days": 180,
            "message_id": None,
            "since_date": None,
            "batch_size": 500,
            "max_messages": 1200,
        },
        "media": {
            "enabled": True,
            "types": ["document", "photo"],
            "max_file_size_bytes": 10485760,
        },
        "canonicalize": True,
        "enqueue_classification": False,
    }
    with fixture["session_factory"]() as session:
        stored_job = session.execute(select(scheduler_jobs_table)).mappings().one()
    assert stored_job["status"] == "queued"
    assert stored_job["idempotency_key"].startswith(f"source:{source.id}:raw-export:")


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
        "client": TestClient(
            create_app(
                database_path=db_path,
                bootstrap_admin_password="initial-secret",
                bootstrap_admin_password_file=tmp_path / "bootstrap-admin-password.txt",
                telegram_bot_token="telegram-token",
            )
        ),
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
