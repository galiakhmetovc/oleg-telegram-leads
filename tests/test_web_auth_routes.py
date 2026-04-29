from datetime import UTC, datetime
import hashlib
import hmac

from fastapi.testclient import TestClient
from sqlalchemy import select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.web_auth import web_auth_sessions_table
from pur_leads.services.web_auth import WebAuthService
from pur_leads.web.app import create_app


def test_local_auth_routes_login_me_change_password_and_logout(tmp_path):
    db_path = tmp_path / "test.db"
    upgrade_database(create_sqlite_engine(db_path))
    app = create_app(
        database_path=db_path,
        bootstrap_admin_username="admin",
        bootstrap_admin_password="initial-secret",
        bootstrap_admin_password_file=tmp_path / "bootstrap-admin-password.txt",
        telegram_bot_token="telegram-token",
    )
    client = TestClient(app)

    assert client.get("/api/me").status_code == 401

    login_response = client.post(
        "/api/auth/local",
        json={"username": "admin", "password": "initial-secret"},
    )
    assert login_response.status_code == 200
    assert login_response.json()["user"]["local_username"] == "admin"
    assert login_response.json()["user"]["must_change_password"] is True
    assert "pur_session" in login_response.cookies

    me_response = client.get("/api/me")
    assert me_response.status_code == 200
    assert me_response.json()["user"]["role"] == "admin"

    change_response = client.post(
        "/api/auth/change-password",
        json={"new_password": "changed-secret"},
    )
    assert change_response.status_code == 200
    assert change_response.json()["user"]["must_change_password"] is False

    logout_response = client.post("/api/auth/logout")
    assert logout_response.status_code == 200
    assert client.get("/api/me").status_code == 401

    session_factory = create_session_factory(create_sqlite_engine(db_path))
    with session_factory() as session:
        session_row = session.execute(select(web_auth_sessions_table)).mappings().one()
        assert session_row["revoked_at"] is not None


def test_bootstrap_admin_password_file_is_removed_after_forced_password_change(tmp_path):
    db_path = tmp_path / "test.db"
    password_file = tmp_path / "bootstrap-admin-password.txt"
    upgrade_database(create_sqlite_engine(db_path))
    app = create_app(
        database_path=db_path,
        bootstrap_admin_password_file=password_file,
        telegram_bot_token="telegram-token",
    )
    client = TestClient(app)

    assert password_file.exists()
    assert password_file.stat().st_mode & 0o777 == 0o600
    password_lines = dict(
        line.split("=", 1) for line in password_file.read_text().splitlines() if "=" in line
    )
    assert password_lines["username"] == "admin"
    assert password_lines["password"]

    login_response = client.post(
        "/api/auth/local",
        json={"username": "admin", "password": password_lines["password"]},
    )
    assert login_response.status_code == 200
    assert login_response.json()["user"]["must_change_password"] is True

    change_response = client.post(
        "/api/auth/change-password",
        json={"new_password": "changed-secret"},
    )
    assert change_response.status_code == 200
    assert change_response.json()["user"]["must_change_password"] is False
    assert not password_file.exists()

    restarted_client = TestClient(
        create_app(
            database_path=db_path,
            bootstrap_admin_password_file=password_file,
            telegram_bot_token="telegram-token",
        )
    )
    assert not password_file.exists()
    changed_login = restarted_client.post(
        "/api/auth/local",
        json={"username": "admin", "password": "changed-secret"},
    )
    assert changed_login.status_code == 200
    assert changed_login.json()["user"]["must_change_password"] is False


def test_telegram_auth_route_requires_valid_payload_and_preapproved_user(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        service = WebAuthService(session, telegram_bot_token="telegram-token")
        admin = service.ensure_bootstrap_admin(username="admin", password="initial-secret")
        service.add_telegram_admin(
            telegram_user_id="42",
            telegram_username="oleg",
            display_name="Oleg",
            actor="admin",
            actor_user_id=admin.id,
        )

    client = TestClient(
        create_app(
            database_path=db_path,
            bootstrap_admin_password="initial-secret",
            bootstrap_admin_password_file=tmp_path / "bootstrap-admin-password.txt",
            telegram_bot_token="telegram-token",
        )
    )
    valid_payload = _telegram_payload(
        bot_token="telegram-token",
        data={
            "id": "42",
            "username": "oleg",
            "first_name": "Oleg",
            "auth_date": str(int(datetime(2026, 4, 28, tzinfo=UTC).timestamp())),
        },
    )
    bad_response = client.post("/api/auth/telegram", json={**valid_payload, "hash": "bad"})
    unknown_response = client.post(
        "/api/auth/telegram",
        json=_telegram_payload(
            bot_token="telegram-token",
            data={"id": "99", "auth_date": valid_payload["auth_date"]},
        ),
    )
    ok_response = client.post("/api/auth/telegram", json=valid_payload)

    assert bad_response.status_code == 401
    assert unknown_response.status_code == 401
    assert ok_response.status_code == 200
    assert ok_response.json()["user"]["telegram_user_id"] == "42"
    assert "pur_session" in ok_response.cookies


def _telegram_payload(*, bot_token: str, data: dict[str, str]) -> dict[str, str]:
    check_string = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    digest = hmac.new(secret_key, check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    return {**data, "hash": digest}
