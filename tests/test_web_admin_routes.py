from datetime import UTC, datetime
import hashlib
import hmac

from fastapi.testclient import TestClient
from sqlalchemy import func
from sqlalchemy import select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.audit import audit_log_table
from pur_leads.models.ai import (
    ai_agent_routes_table,
    ai_agents_table,
    ai_model_limits_table,
    ai_models_table,
    ai_provider_accounts_table,
    ai_providers_table,
)
from pur_leads.models.settings import settings_revisions_table
from pur_leads.models.web_auth import web_auth_sessions_table, web_users_table
from pur_leads.services.web_auth import WebAuthService
from pur_leads.web.app import create_app


def test_admin_user_routes_manage_telegram_admins_and_disable_sessions(tmp_path):
    fixture = _setup_admin_app(tmp_path)
    admin_client = fixture["client"]
    _login_local(admin_client)

    users_response = admin_client.get("/api/admin/users")
    create_response = admin_client.post(
        "/api/admin/users/telegram",
        json={
            "telegram_user_id": "42",
            "telegram_username": "oleg",
            "display_name": "Oleg",
        },
    )
    duplicate_response = admin_client.post(
        "/api/admin/users/telegram",
        json={
            "telegram_user_id": "42",
            "telegram_username": "oleg",
            "display_name": "Oleg",
        },
    )
    telegram_user_id = create_response.json()["user"]["id"]
    telegram_client = TestClient(fixture["app"])
    telegram_login_response = telegram_client.post(
        "/api/auth/telegram",
        json=_telegram_payload(
            bot_token="telegram-token",
            data={
                "id": "42",
                "username": "oleg",
                "first_name": "Oleg",
                "auth_date": str(int(datetime(2026, 4, 28, tzinfo=UTC).timestamp())),
            },
        ),
    )
    update_response = admin_client.patch(
        f"/api/admin/users/{telegram_user_id}",
        json={"status": "disabled", "display_name": "Oleg disabled"},
    )
    denied_login_response = telegram_client.post(
        "/api/auth/telegram",
        json=_telegram_payload(
            bot_token="telegram-token",
            data={
                "id": "42",
                "username": "oleg",
                "auth_date": str(int(datetime(2026, 4, 28, tzinfo=UTC).timestamp())),
            },
        ),
    )

    assert users_response.status_code == 200
    assert users_response.json()["items"][0]["local_username"] == "admin"
    assert "password_hash" not in users_response.json()["items"][0]
    assert create_response.status_code == 200
    assert create_response.json()["user"]["telegram_user_id"] == "42"
    assert duplicate_response.status_code == 409
    assert telegram_login_response.status_code == 200
    assert update_response.status_code == 200
    assert update_response.json()["user"]["status"] == "disabled"
    assert update_response.json()["user"]["display_name"] == "Oleg disabled"
    assert denied_login_response.status_code == 401
    assert telegram_client.get("/api/me").status_code == 401

    with fixture["session_factory"]() as session:
        user_row = (
            session.execute(select(web_users_table).where(web_users_table.c.id == telegram_user_id))
            .mappings()
            .one()
        )
        session_rows = (
            session.execute(
                select(web_auth_sessions_table).where(
                    web_auth_sessions_table.c.user_id == telegram_user_id
                )
            )
            .mappings()
            .all()
        )
        audit_actions = {
            row["action"] for row in session.execute(select(audit_log_table)).mappings().all()
        }
    assert user_row["status"] == "disabled"
    assert session_rows
    assert all(row["revoked_at"] is not None for row in session_rows)
    assert {
        "web_auth.telegram_admin_created",
        "web_auth.user_status_changed",
        "web_auth.user_display_name_changed",
        "web_auth.user_sessions_revoked",
    }.issubset(audit_actions)


def test_admin_user_routes_prevent_lockout_and_revoke_pending_sessions(tmp_path):
    fixture = _setup_admin_app(tmp_path)
    admin_client = fixture["client"]
    _login_local(admin_client)

    self_user_id = admin_client.get("/api/me").json()["user"]["id"]
    self_disable_response = admin_client.patch(
        f"/api/admin/users/{self_user_id}",
        json={"status": "disabled"},
    )
    create_response = admin_client.post(
        "/api/admin/users/telegram",
        json={
            "telegram_user_id": "43",
            "telegram_username": "pending_admin",
            "display_name": "Pending Admin",
        },
    )
    telegram_user_id = create_response.json()["user"]["id"]
    telegram_client = TestClient(fixture["app"])
    telegram_login_response = telegram_client.post(
        "/api/auth/telegram",
        json=_telegram_payload(
            bot_token="telegram-token",
            data={
                "id": "43",
                "username": "pending_admin",
                "auth_date": str(int(datetime(2026, 4, 28, tzinfo=UTC).timestamp())),
            },
        ),
    )
    pending_response = admin_client.patch(
        f"/api/admin/users/{telegram_user_id}",
        json={"status": "pending"},
    )
    reactivate_response = admin_client.patch(
        f"/api/admin/users/{telegram_user_id}",
        json={"status": "active"},
    )

    assert self_disable_response.status_code == 400
    assert telegram_login_response.status_code == 200
    assert pending_response.status_code == 200
    assert pending_response.json()["user"]["status"] == "pending"
    assert telegram_client.get("/api/me").status_code == 401
    assert reactivate_response.status_code == 200
    assert telegram_client.get("/api/me").status_code == 401

    with fixture["session_factory"]() as session:
        own_user = (
            session.execute(select(web_users_table).where(web_users_table.c.id == self_user_id))
            .mappings()
            .one()
        )
        telegram_sessions = (
            session.execute(
                select(web_auth_sessions_table).where(
                    web_auth_sessions_table.c.user_id == telegram_user_id
                )
            )
            .mappings()
            .all()
        )
    assert own_user["status"] == "active"
    assert telegram_sessions
    assert all(row["revoked_at"] is not None for row in telegram_sessions)


def test_admin_settings_routes_update_settings_and_audit_denials(tmp_path):
    fixture = _setup_admin_app(tmp_path)
    client = fixture["client"]

    denied_response = client.get("/api/admin/users")
    _login_local(client)
    defaults_response = client.get("/api/settings")
    update_response = client.put(
        "/api/settings/telegram_worker_count",
        json={"value": 2, "value_type": "int", "reason": "scale worker"},
    )
    secret_response = client.put(
        "/api/settings/ai_api_key",
        json={"value": "plain-secret", "value_type": "secret_ref"},
    )

    assert denied_response.status_code == 401
    assert defaults_response.status_code == 200
    default_rows = defaults_response.json()["items"]
    assert any(
        row["key"] == "telegram_worker_count" and row["value"] == 1 and row["is_default"]
        for row in default_rows
    )
    assert update_response.status_code == 200
    assert update_response.json()["setting"]["key"] == "telegram_worker_count"
    assert update_response.json()["setting"]["value"] == 2
    assert secret_response.status_code == 400

    with fixture["session_factory"]() as session:
        revisions = session.execute(select(settings_revisions_table)).mappings().all()
        audit_rows = session.execute(select(audit_log_table)).mappings().all()
    assert len(revisions) == 1
    assert revisions[0]["setting_key"] == "telegram_worker_count"
    assert revisions[0]["new_value_json"] == 2
    assert any(row["action"] == "settings.update" for row in audit_rows)
    assert any(row["action"] == "web_auth.protected_route_denied" for row in audit_rows)


def test_admin_userbot_routes_create_list_and_set_default(tmp_path):
    fixture = _setup_admin_app(tmp_path)
    client = fixture["client"]

    denied_response = client.get("/api/admin/userbots")
    _login_local(client)
    create_response = client.post(
        "/api/admin/userbots",
        json={
            "display_name": "Main userbot",
            "session_name": "main",
            "session_path": "/secure/main.session",
            "make_default": True,
        },
    )
    list_response = client.get("/api/admin/userbots")
    settings_response = client.get("/api/settings")

    assert denied_response.status_code == 401
    assert create_response.status_code == 200
    account = create_response.json()["userbot"]
    assert account["display_name"] == "Main userbot"
    assert account["session_name"] == "main"
    assert account["status"] == "active"
    assert "session_path" not in account
    assert list_response.status_code == 200
    assert [row["id"] for row in list_response.json()["items"]] == [account["id"]]
    assert any(
        row["key"] == "telegram_default_userbot_account_id"
        and row["value"] == account["id"]
        and row["is_default"] is False
        for row in settings_response.json()["items"]
    )


def test_admin_ai_registry_routes_list_update_limits_and_add_agent_routes(tmp_path):
    fixture = _setup_admin_app(tmp_path)
    client = fixture["client"]

    denied_response = client.get("/api/admin/ai-registry")
    _login_local(client)
    empty_registry_response = client.get("/api/admin/ai-registry")
    empty_registry_counts = _ai_registry_counts(fixture["session_factory"])
    bootstrap_response = client.post("/api/admin/ai-registry/bootstrap-defaults")
    registry_response = client.get("/api/admin/ai-registry")
    registry = registry_response.json()
    flash = next(
        model for model in registry["models"] if model["normalized_model_name"] == "glm-4.5-flash"
    )
    airx = next(
        model for model in registry["models"] if model["normalized_model_name"] == "glm-4.5-airx"
    )
    limit_response = client.patch(
        f"/api/admin/ai-model-limits/{flash['limit']['id']}",
        json={"raw_limit": 7, "utilization_ratio": 0.8},
    )
    route_response = client.post(
        "/api/admin/ai-agents/catalog_extractor/routes",
        json={
            "model_id": airx["id"],
            "route_role": "fallback",
            "priority": 30,
            "max_output_tokens": 2048,
            "temperature": 0.0,
            "enabled": True,
            "structured_output_required": True,
        },
    )
    updated_registry = client.get("/api/admin/ai-registry").json()

    assert denied_response.status_code == 401
    assert empty_registry_response.status_code == 200
    assert empty_registry_response.json()["models"] == []
    assert empty_registry_response.json()["agents"] == []
    assert empty_registry_response.json()["routes"] == []
    assert empty_registry_counts == {
        "providers": 0,
        "provider_accounts": 0,
        "models": 0,
        "model_limits": 0,
        "agents": 0,
        "routes": 0,
    }
    assert bootstrap_response.status_code == 200
    assert registry_response.status_code == 200
    assert any(model["normalized_model_name"] == "glm-ocr" for model in registry["models"])
    assert any(agent["agent_key"] == "ocr_extractor" for agent in registry["agents"])
    assert limit_response.status_code == 200
    assert limit_response.json()["limit"]["raw_limit"] == 7
    assert limit_response.json()["limit"]["effective_limit"] == 5
    assert route_response.status_code == 200
    assert route_response.json()["route"]["model"] == "GLM-4.5-AirX"
    assert route_response.json()["route"]["route_role"] == "fallback"
    assert any(
        route["model"] == "GLM-4.5-AirX" and route["route_role"] == "fallback"
        for route in updated_registry["routes"]
    )

    with fixture["session_factory"]() as session:
        audit_actions = {
            row["action"] for row in session.execute(select(audit_log_table)).mappings().all()
        }
    assert {"ai_registry.limit_update", "ai_registry.route_upsert"}.issubset(audit_actions)


def _ai_registry_counts(session_factory) -> dict[str, int]:
    with session_factory() as session:
        return {
            "providers": session.scalar(select(func.count()).select_from(ai_providers_table)),
            "provider_accounts": session.scalar(
                select(func.count()).select_from(ai_provider_accounts_table)
            ),
            "models": session.scalar(select(func.count()).select_from(ai_models_table)),
            "model_limits": session.scalar(select(func.count()).select_from(ai_model_limits_table)),
            "agents": session.scalar(select(func.count()).select_from(ai_agents_table)),
            "routes": session.scalar(select(func.count()).select_from(ai_agent_routes_table)),
        }


def _setup_admin_app(tmp_path):
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
        telegram_bot_token="telegram-token",
    )
    return {"app": app, "client": TestClient(app), "session_factory": session_factory}


def _login_local(client: TestClient) -> None:
    response = client.post(
        "/api/auth/local",
        json={"username": "admin", "password": "initial-secret"},
    )
    assert response.status_code == 200


def _telegram_payload(*, bot_token: str, data: dict[str, str]) -> dict[str, str]:
    check_string = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    digest = hmac.new(secret_key, check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    return {**data, "hash": digest}
