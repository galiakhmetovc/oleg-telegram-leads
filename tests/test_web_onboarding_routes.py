from __future__ import annotations

import json
from pathlib import Path
import zipfile

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.ai import ai_provider_accounts_table
from pur_leads.models.audit import audit_log_table
from pur_leads.models.settings import settings_table
from pur_leads.models.telegram_sources import telegram_raw_export_runs_table
from pur_leads.models.tracing import trace_spans_table
from pur_leads.services.secrets import SecretRefService
from pur_leads.services.web_auth import WebAuthService
from pur_leads.web.app import create_app


def test_onboarding_configures_bot_token_and_notification_group(tmp_path):
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append({"path": request.url.path, "json": json.loads(request.content or b"{}")})
        if request.url.path.endswith("/getMe"):
            return httpx.Response(
                200,
                json={"ok": True, "result": {"id": 777, "username": "pur_leads_bot"}},
                request=request,
            )
        if request.url.path.endswith("/getUpdates"):
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": [
                        {
                            "update_id": 10,
                            "message": {
                                "message_id": 55,
                                "message_thread_id": 7,
                                "text": "/pur_setup",
                                "chat": {
                                    "id": -100123456,
                                    "type": "supergroup",
                                    "title": "Leads Finder",
                                },
                            },
                        }
                    ],
                },
                request=request,
            )
        if request.url.path.endswith("/sendMessage"):
            return httpx.Response(
                200,
                json={"ok": True, "result": {"message_id": 56}},
                request=request,
            )
        return httpx.Response(404, request=request)

    fixture = _setup_onboarding_app(
        tmp_path,
        telegram_bot_api_transport=httpx.MockTransport(handler),
    )
    client = fixture["client"]
    _login_local(client)

    initial_status = client.get("/api/onboarding/status")
    token_response = client.post(
        "/api/onboarding/bot-token",
        json={"token": "777:secret-token", "display_name": "PUR Leads bot"},
    )
    discover_response = client.get("/api/onboarding/notification-groups/discover")
    save_group_response = client.post(
        "/api/onboarding/notification-group",
        json={
            "chat_id": "-100123456",
            "title": "Leads Finder",
            "message_thread_id": 7,
            "send_test": True,
        },
    )
    final_status = client.get("/api/onboarding/status")
    resources_response = client.get("/api/onboarding/resources")

    assert initial_status.status_code == 200
    assert initial_status.json()["steps"]["bot_token"]["done"] is False
    assert initial_status.json()["steps"]["llm_provider"]["done"] is False
    assert token_response.status_code == 200
    assert token_response.json()["bot"]["username"] == "pur_leads_bot"
    assert "secret-token" not in json.dumps(token_response.json())
    assert discover_response.status_code == 200
    assert discover_response.json()["candidates"] == [
        {
            "chat_id": "-100123456",
            "title": "Leads Finder",
            "chat_type": "supergroup",
            "message_thread_id": 7,
        }
    ]
    assert save_group_response.status_code == 200
    assert save_group_response.json()["notification_group"]["chat_id"] == "-100123456"
    assert final_status.json()["steps"]["bot_token"]["done"] is True
    assert final_status.json()["steps"]["notification_group"]["done"] is True
    resources = resources_response.json()["items"]
    assert [resource["resource_type"] for resource in resources] == [
        "telegram_notification_group",
        "telegram_bot",
    ]
    assert resources[0]["display_name"] == "Leads Finder"
    assert (
        resources[0]["parent_resource_id"] == f"telegram_bot:{token_response.json()['bot']['id']}"
    )
    assert resources[1]["display_name"] == "PUR Leads bot"
    assert any(
        request["path"].endswith("/sendMessage")
        and request["json"]["chat_id"] == "-100123456"
        and request["json"]["message_thread_id"] == 7
        for request in requests
    )

    with fixture["session_factory"]() as session:
        settings = {
            row["key"]: row["value_json"]
            for row in session.execute(select(settings_table)).mappings().all()
        }
        token_secret_id = settings["telegram_bot_token_secret_ref"]["secret_ref_id"]
        assert SecretRefService(session).resolve_value(token_secret_id) == "777:secret-token"
        assert settings["telegram_lead_notification_chat_id"] == "-100123456"
        assert settings["telegram_lead_notification_thread_id"] == 7


def test_onboarding_configures_llm_provider_and_default_model(tmp_path):
    fixture = _setup_onboarding_app(tmp_path)
    client = fixture["client"]
    _login_local(client)

    provider_response = client.post(
        "/api/onboarding/llm-provider",
        json={
            "base_url": "https://api.z.ai/api/coding/paas/v4",
            "api_key": "zai-secret",
        },
    )
    provider_payload = provider_response.json()
    resources_response = client.get("/api/onboarding/resources")
    provider_status_response = client.get("/api/onboarding/status")
    flash_model = next(
        model
        for model in provider_payload["models"]
        if model["normalized_model_name"] == "glm-4.5-flash"
    )
    model_response = client.post(
        "/api/onboarding/llm-default-model",
        json={"model_id": flash_model["id"]},
    )
    status_response = client.get("/api/onboarding/status")

    assert provider_response.status_code == 200
    assert "zai-secret" not in json.dumps(provider_payload)
    assert provider_payload["provider"]["provider_key"] == "zai"
    assert any(model["provider_model_name"] == "GLM-5.1" for model in provider_payload["models"])
    assert provider_status_response.json()["steps"]["llm_provider"]["done"] is True
    llm_resources = [
        resource
        for resource in resources_response.json()["items"]
        if resource["resource_type"] == "ai_provider_account"
    ]
    assert llm_resources == [
        {
            "resource_id": f"ai_provider_account:{provider_payload['account']['id']}",
            "id": provider_payload["account"]["id"],
            "resource_type": "ai_provider_account",
            "type_label": "LLM-провайдер",
            "display_name": "Z.AI",
            "status": "active",
            "health": "active",
            "detail": "zai / https://api.z.ai/api/coding/paas/v4",
            "parent_resource_id": None,
            "delete_path": f"/api/onboarding/llm-providers/{provider_payload['account']['id']}",
            "metadata": {"provider_key": "zai"},
        }
    ]
    assert model_response.status_code == 200
    assert model_response.json()["model"]["provider_model_name"] == "GLM-4.5-Flash"
    assert status_response.json()["steps"]["llm_provider"]["done"] is True
    with fixture["session_factory"]() as session:
        settings = {
            row["key"]: row["value_json"]
            for row in session.execute(select(settings_table)).mappings().all()
        }
        account = session.execute(select(ai_provider_accounts_table)).mappings().one()
        secret_id = settings["zai_api_key_secret_ref"]["secret_ref_id"]
        assert SecretRefService(session).resolve_value(secret_id) == "zai-secret"
        assert settings["catalog_llm_base_url"] == "https://api.z.ai/api/coding/paas/v4"
        assert settings["lead_llm_shadow_base_url"] == "https://api.z.ai/api/coding/paas/v4"
        assert settings["catalog_llm_model"] == "GLM-4.5-Flash"
    assert account["base_url"] == "https://api.z.ai/api/coding/paas/v4"
    assert account["auth_secret_ref"] == f"secret_ref:{secret_id}"


def test_onboarding_allows_multiple_llm_provider_resources(tmp_path):
    fixture = _setup_onboarding_app(tmp_path)
    client = fixture["client"]
    _login_local(client)

    first_response = client.post(
        "/api/onboarding/llm-provider",
        json={
            "base_url": "https://api.z.ai/api/coding/paas/v4",
            "api_key": "zai-secret-1",
            "display_name": "Z.AI основной",
        },
    )
    second_response = client.post(
        "/api/onboarding/llm-provider",
        json={
            "base_url": "https://api.z.ai/api/coding/paas/v4",
            "api_key": "zai-secret-2",
            "display_name": "Z.AI резерв",
        },
    )
    resources_response = client.get("/api/onboarding/resources")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    llm_resources = [
        resource
        for resource in resources_response.json()["items"]
        if resource["resource_type"] == "ai_provider_account"
    ]
    assert {resource["display_name"] for resource in llm_resources} == {
        "Z.AI основной",
        "Z.AI резерв",
    }
    assert len({resource["id"] for resource in llm_resources}) == 2
    assert "zai-secret" not in json.dumps(resources_response.json())


def test_onboarding_interactive_userbot_login_start_and_complete(tmp_path):
    login_client = FakeUserbotLoginClient()
    fixture = _setup_onboarding_app(
        tmp_path,
        userbot_login_client_factory=lambda: login_client,
    )
    client = fixture["client"]
    _login_local(client)

    start_response = client.post(
        "/api/onboarding/userbots/interactive/start",
        json={
            "display_name": "Interactive userbot",
            "session_name": "interactive",
            "api_id": 12345,
            "api_hash": "api-hash-secret",
            "phone": "+79990000000",
            "make_default": True,
        },
    )
    login_id = start_response.json()["login_id"]
    complete_response = client.post(
        "/api/onboarding/userbots/interactive/complete",
        json={"login_id": login_id, "code": "12345", "password": "2fa-password"},
    )

    assert start_response.status_code == 200
    assert start_response.json()["status"] == "code_sent"
    assert complete_response.status_code == 200
    userbot = complete_response.json()["userbot"]
    assert userbot["display_name"] == "Interactive userbot"
    assert userbot["telegram_user_id"] == "42"
    assert userbot["telegram_username"] == "oleg"
    assert login_client.sent_codes[0]["phone"] == "+79990000000"
    assert login_client.sign_ins[0]["code"] == "12345"
    assert Path(login_client.sign_ins[0]["session_path"]).exists()

    with fixture["session_factory"]() as session:
        settings = {
            row["key"]: row["value_json"]
            for row in session.execute(select(settings_table)).mappings().all()
        }
        assert settings["telegram_default_userbot_account_id"] == userbot["id"]
        assert settings["telegram_api_id"] == 12345


def test_login_request_creates_user_session_trace(tmp_path):
    fixture = _setup_onboarding_app(tmp_path)
    client = fixture["client"]

    response = client.post(
        "/api/auth/local",
        json={"username": "admin", "password": "initial-secret"},
        headers={"x-request-id": "login-request-1"},
    )

    assert response.status_code == 200
    trace_id = response.headers["x-trace-id"]
    assert len(trace_id) == 32
    assert response.headers["x-request-id"] == "login-request-1"
    with fixture["session_factory"]() as session:
        span = (
            session.execute(
                select(trace_spans_table).where(trace_spans_table.c.trace_id == trace_id)
            )
            .mappings()
            .one()
        )
        audit_row = (
            session.execute(
                select(audit_log_table).where(audit_log_table.c.action == "web_auth.login_success")
            )
            .mappings()
            .one()
        )
    assert span["span_name"] == "HTTP POST /api/auth/local"
    assert span["span_kind"] == "server"
    assert span["status"] == "ok"
    assert span["http_status_code"] == 200
    assert span["user_id"] == response.json()["user"]["id"]
    assert span["web_session_id"]
    assert span["request_id"] == "login-request-1"
    assert audit_row["new_value_json"]["trace"]["trace_id"] == trace_id
    assert audit_row["new_value_json"]["trace"]["user_id"] == response.json()["user"]["id"]
    assert audit_row["new_value_json"]["trace"]["web_session_id"] == span["web_session_id"]


def test_uploading_telegram_desktop_archive_creates_traceable_data_source_resource(tmp_path):
    archive_path = _write_desktop_archive(tmp_path)
    fixture = _setup_onboarding_app(tmp_path, raw_export_storage_path=tmp_path / "raw")
    client = fixture["client"]
    _login_local(client)

    with archive_path.open("rb") as archive_file:
        response = client.post(
            "/api/onboarding/resources/telegram-desktop-archive",
            data={
                "purpose": "lead_monitoring",
                "display_name": "Чат лидов из архива",
                "sync_source_messages": "true",
            },
            files={"file": ("ChatExport.zip", archive_file, "application/zip")},
            headers={"x-request-id": "upload-request-1"},
        )
    resources_response = client.get("/api/onboarding/resources")

    assert response.status_code == 200
    payload = response.json()
    assert payload["resource"]["resource_type"] == "data_source_telegram_archive"
    assert payload["resource"]["display_name"] == "Чат лидов из архива"
    assert payload["result"]["message_count"] == 2
    assert payload["result"]["created_source_messages"] == 2
    assert "initial-secret" not in json.dumps(payload)

    resources = resources_response.json()["items"]
    uploaded = [
        resource
        for resource in resources
        if resource["resource_type"] == "data_source_telegram_archive"
    ]
    assert len(uploaded) == 1
    assert uploaded[0]["metadata"]["raw_export_run_id"] == payload["result"]["raw_export_run_id"]
    assert uploaded[0]["metadata"]["message_count"] == 2
    assert uploaded[0]["metadata"]["uploaded_by_user_id"] == payload["trace"]["user_id"]
    assert uploaded[0]["delete_path"] is None

    trace_id = response.headers["x-trace-id"]
    with fixture["session_factory"]() as session:
        raw_run = session.execute(select(telegram_raw_export_runs_table)).mappings().one()
        upload_span = (
            session.execute(
                select(trace_spans_table).where(
                    trace_spans_table.c.trace_id == trace_id,
                    trace_spans_table.c.span_name == "resource.import.telegram_desktop_archive",
                )
            )
            .mappings()
            .one()
        )
        audit_row = (
            session.execute(
                select(audit_log_table).where(
                    audit_log_table.c.action == "resource.data_source_uploaded"
                )
            )
            .mappings()
            .one()
        )
    assert raw_run["metadata_json"]["trace"]["trace_id"] == trace_id
    assert raw_run["metadata_json"]["trace"]["user_id"] == payload["trace"]["user_id"]
    assert raw_run["metadata_json"]["trace"]["web_session_id"] == payload["trace"]["web_session_id"]
    assert Path(raw_run["metadata_json"]["upload"]["stored_archive_path"]).exists()
    assert raw_run["metadata_json"]["upload"]["sha256"]
    assert upload_span["parent_span_id"]
    assert upload_span["resource_type"] == "monitored_source"
    assert upload_span["resource_id"] == payload["result"]["monitored_source_id"]
    assert (
        upload_span["attributes_json"]["raw_export_run_id"]
        == payload["result"]["raw_export_run_id"]
    )
    assert audit_row["new_value_json"]["trace"]["trace_id"] == trace_id
    assert (
        audit_row["new_value_json"]["raw_export_run_id"] == payload["result"]["raw_export_run_id"]
    )


class FakeUserbotLoginClient:
    def __init__(self) -> None:
        self.sent_codes: list[dict] = []
        self.sign_ins: list[dict] = []

    async def send_code(self, *, session_path, api_id, api_hash, phone):
        self.sent_codes.append(
            {
                "session_path": str(session_path),
                "api_id": api_id,
                "api_hash": api_hash,
                "phone": phone,
            }
        )
        Path(session_path).write_bytes(b"pending session")
        return "phone-code-hash"

    async def sign_in(
        self, *, session_path, api_id, api_hash, phone, code, phone_code_hash, password
    ):
        self.sign_ins.append(
            {
                "session_path": str(session_path),
                "api_id": api_id,
                "api_hash": api_hash,
                "phone": phone,
                "code": code,
                "phone_code_hash": phone_code_hash,
                "password": password,
            }
        )
        return {"telegram_user_id": "42", "telegram_username": "oleg"}


def _setup_onboarding_app(tmp_path, **kwargs):
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
    return {"app": app, "client": TestClient(app), "session_factory": session_factory}


def _login_local(client: TestClient) -> None:
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
