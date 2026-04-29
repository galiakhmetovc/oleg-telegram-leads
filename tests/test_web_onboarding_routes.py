from __future__ import annotations

import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.ai import ai_provider_accounts_table
from pur_leads.models.settings import settings_table
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
