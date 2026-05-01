from __future__ import annotations

import json
from pathlib import Path
import zipfile

from fastapi.testclient import TestClient
from sqlalchemy import inspect, select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.interest_contexts import interest_contexts_table
from pur_leads.models.scheduler import scheduler_jobs_table
from pur_leads.models.telegram_sources import (
    monitored_sources_table,
    telegram_raw_export_runs_table,
)
from pur_leads.services.web_auth import WebAuthService
from pur_leads.web.app import create_app


def test_migration_creates_interest_context_tables_and_source_link(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")

    upgrade_database(engine)

    inspector = inspect(engine)
    assert "interest_contexts" in set(inspector.get_table_names())
    monitored_columns = {column["name"] for column in inspector.get_columns("monitored_sources")}
    assert "interest_context_id" in monitored_columns


def test_interest_context_route_creates_seed_source_without_automatic_analysis(tmp_path):
    fixture = _setup_app(tmp_path)
    client = fixture["client"]
    _login(client)

    create_context_response = client.post(
        "/api/interest-contexts",
        json={
            "name": "PUR умный дом",
            "description": "Канал и чаты, из которых строим ядро интересов.",
        },
    )
    context_id = create_context_response.json()["context"]["id"]
    source_response = client.post(
        f"/api/interest-contexts/{context_id}/telegram-source",
        json={
            "input_ref": "https://t.me/purmaster",
            "range_mode": "from_beginning",
            "media_enabled": True,
            "media_types": ["document"],
            "check_access": False,
            "enqueue_raw_export": True,
        },
    )
    detail_response = client.get(f"/api/interest-contexts/{context_id}")

    assert create_context_response.status_code == 200
    assert source_response.status_code == 200
    source = source_response.json()["source"]
    assert source["interest_context_id"] == context_id
    assert source["source_purpose"] == "interest_context_seed"
    assert source["lead_detection_enabled"] is False
    assert source["catalog_ingestion_enabled"] is False
    assert source_response.json()["raw_export_job"]["job_type"] == "export_telegram_raw"
    assert (
        source_response.json()["raw_export_job"]["payload_json"]["enqueue_classification"] is False
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["sources"][0]["id"] == source["id"]
    assert detail_response.json()["sources"][0]["latest_raw_export_run"] is None

    with fixture["session_factory"]() as session:
        context_row = session.execute(select(interest_contexts_table)).mappings().one()
        source_row = session.execute(select(monitored_sources_table)).mappings().one()
        job_row = session.execute(select(scheduler_jobs_table)).mappings().one()
    assert context_row["name"] == "PUR умный дом"
    assert source_row["interest_context_id"] == context_id
    assert source_row["source_purpose"] == "interest_context_seed"
    assert job_row["payload_json"]["range"]["mode"] == "from_beginning"
    assert job_row["payload_json"]["media"]["enabled"] is True


def test_interest_context_uploads_telegram_archive_as_raw_seed_artifact(tmp_path):
    archive_path = _write_desktop_archive(tmp_path)
    fixture = _setup_app(tmp_path, raw_export_storage_path=tmp_path / "raw")
    client = fixture["client"]
    _login(client)
    context_id = client.post(
        "/api/interest-contexts",
        json={"name": "Архив лидов"},
    ).json()["context"]["id"]

    with archive_path.open("rb") as archive_file:
        response = client.post(
            f"/api/interest-contexts/{context_id}/telegram-archive",
            data={"display_name": "Экспорт Telegram", "sync_source_messages": "false"},
            files={"file": ("ChatExport.zip", archive_file, "application/zip")},
            headers={"x-request-id": "interest-upload-1"},
        )
    detail_response = client.get(f"/api/interest-contexts/{context_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["message_count"] == 2
    assert payload["source"]["interest_context_id"] == context_id
    assert payload["source"]["source_purpose"] == "interest_context_seed"
    assert payload["source"]["lead_detection_enabled"] is False
    assert payload["source"]["catalog_ingestion_enabled"] is False
    assert payload["raw_export_run"]["export_format"] == "telegram_desktop_json_v1"
    assert Path(payload["result"]["messages_parquet_path"]).exists()
    assert "initial-secret" not in json.dumps(payload)

    detail = detail_response.json()
    assert detail["sources"][0]["latest_raw_export_run"]["id"] == payload["raw_export_run"]["id"]
    assert detail["sources"][0]["latest_raw_export_run"]["message_count"] == 2

    with fixture["session_factory"]() as session:
        raw_run = session.execute(select(telegram_raw_export_runs_table)).mappings().one()
        source = session.execute(select(monitored_sources_table)).mappings().one()
    assert raw_run["metadata_json"]["interest_context"]["id"] == context_id
    assert raw_run["metadata_json"]["trace"]["trace_id"] == response.headers["x-trace-id"]
    assert source["interest_context_id"] == context_id


def test_interest_context_page_is_protected_and_empty_home_redirects_there(tmp_path):
    client = _setup_app(tmp_path)["client"]

    denied_response = client.get("/interest-contexts", follow_redirects=False)
    _login(client)
    home_response = client.get("/", follow_redirects=False)
    page_response = client.get("/interest-contexts")
    js_response = client.get("/static/app.js")

    assert denied_response.status_code == 303
    assert denied_response.headers["location"] == "/login"
    assert home_response.status_code == 303
    assert home_response.headers["location"] == "/interest-contexts"
    assert page_response.status_code == 200
    assert 'data-page="interest-contexts"' in page_response.text
    assert 'id="interest-context-create-form"' in page_response.text
    assert 'id="interest-context-telegram-source-form"' in page_response.text
    assert 'id="interest-context-telegram-archive-form"' in page_response.text
    assert "initInterestContexts" in js_response.text


def _setup_app(tmp_path, **kwargs):
    db_path = tmp_path / "test.db"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        WebAuthService(session, telegram_bot_token="telegram-token").ensure_bootstrap_admin(
            username="admin",
            password="initial-secret",
        )
    app = create_app(
        database_path=db_path,
        bootstrap_admin_password="initial-secret",
        bootstrap_admin_password_file=tmp_path / "bootstrap-admin-password.txt",
        local_secret_storage_path=tmp_path / "secrets",
        telegram_session_storage_path=tmp_path / "sessions",
        telegram_bot_token="telegram-token",
        **kwargs,
    )
    return {"client": TestClient(app), "session_factory": session_factory}


def _login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/local",
        json={"username": "admin", "password": "initial-secret"},
    )
    assert response.status_code == 200


def _write_desktop_archive(tmp_path: Path) -> Path:
    archive_path = tmp_path / "ChatExport.zip"
    payload = {
        "name": "Чат лидов",
        "type": "public_supergroup",
        "id": 1292716582,
        "messages": [
            {
                "id": 1,
                "type": "message",
                "date": "2026-04-30T13:00:00",
                "date_unixtime": "1777543200",
                "from": "Анна",
                "from_id": "user1",
                "text": "Нужна камера Dahua A1",
                "text_entities": [],
            },
            {
                "id": 2,
                "type": "message",
                "date": "2026-04-30T13:01:00",
                "date_unixtime": "1777543260",
                "from": "Анна",
                "from_id": "user1",
                "text": "Нужна еще одна камера",
                "text_entities": [],
            },
        ],
    }
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "ChatExport_2026-04-30/result.json",
            json.dumps(payload, ensure_ascii=False),
        )
    return archive_path
