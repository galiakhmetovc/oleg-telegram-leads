from datetime import UTC, datetime
import base64
import hashlib
import hmac
import secrets

import pytest
from sqlalchemy import select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.audit import audit_log_table, operational_events_table
from pur_leads.models.web_auth import web_auth_sessions_table, web_users_table
from pur_leads.services.web_auth import (
    AuthError,
    PBKDF2_ALGORITHM,
    PBKDF2_ITERATIONS,
    PasswordPolicyError,
    WebAuthService,
    verify_password,
)


@pytest.fixture
def auth_session(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        yield session


def test_bootstrap_local_login_session_logout_and_password_change(auth_session):
    service = WebAuthService(auth_session, telegram_bot_token="bot-token")

    admin = service.ensure_bootstrap_admin(username="admin", password="initial-secret")
    same_admin = service.ensure_bootstrap_admin(username="admin", password="ignored")
    with pytest.raises(AuthError):
        service.login_local(username="admin", password="wrong")
    login = service.login_local(
        username="admin",
        password="initial-secret",
        ip_address="127.0.0.1",
        user_agent="pytest",
    )
    validated = service.validate_session(login.session_token)
    service.change_password(
        admin.id,
        new_password="changed-secret",
        actor="admin",
    )
    service.logout(login.session_token, actor="admin")

    users = auth_session.execute(select(web_users_table)).mappings().all()
    session_row = auth_session.execute(select(web_auth_sessions_table)).mappings().one()
    audit_rows = auth_session.execute(select(audit_log_table)).mappings().all()
    event_rows = auth_session.execute(select(operational_events_table)).mappings().all()
    assert same_admin.id == admin.id
    assert users[0]["local_username"] == "admin"
    assert users[0]["password_hash"] != "initial-secret"
    assert users[0]["must_change_password"] is False
    assert login.session_token != session_row["session_token_hash"]
    assert session_row["ip_address"] == "127.0.0.1"
    assert session_row["user_agent"] == "pytest"
    assert session_row["revoked_at"] is not None
    assert validated.user.id == admin.id
    assert {row["action"] for row in audit_rows} >= {
        "web_auth.bootstrap_admin_created",
        "web_auth.login_success",
        "web_auth.password_changed",
        "web_auth.logout",
    }
    assert any(
        row["event_type"] == "access_check" and row["severity"] == "warning" for row in event_rows
    )
    assert service.login_local(username="admin", password="changed-secret").user.id == admin.id


def test_change_password_rejects_weak_password(auth_session):
    service = WebAuthService(auth_session, telegram_bot_token="bot-token")
    admin = service.ensure_bootstrap_admin(username="admin", password="initial-secret")

    with pytest.raises(PasswordPolicyError, match="минимум 12"):
        service.change_password(admin.id, new_password="short", actor="admin")

    row = (
        auth_session.execute(select(web_users_table).where(web_users_table.c.id == admin.id))
        .mappings()
        .one()
    )
    assert verify_password("initial-secret", row["password_hash"])
    assert row["must_change_password"] is True


def test_password_hash_storage_format_and_login_rehash(auth_session):
    service = WebAuthService(auth_session, telegram_bot_token="bot-token")
    legacy_hash = _legacy_password_hash("initial-secret", iterations=210_000)
    admin = service.ensure_bootstrap_admin(username="admin", password="initial-secret")
    auth_session.execute(
        web_users_table.update()
        .where(web_users_table.c.id == admin.id)
        .values(password_hash=legacy_hash)
    )

    service.login_local(username="admin", password="initial-secret")

    row = (
        auth_session.execute(select(web_users_table).where(web_users_table.c.id == admin.id))
        .mappings()
        .one()
    )
    assert row["password_hash"] != legacy_hash
    assert row["password_hash"].startswith(f"{PBKDF2_ALGORITHM}${PBKDF2_ITERATIONS}$")
    assert "initial-secret" not in row["password_hash"]
    assert verify_password("initial-secret", row["password_hash"])


def test_telegram_login_requires_valid_payload_and_preapproved_active_user(auth_session):
    service = WebAuthService(auth_session, telegram_bot_token="telegram-token")
    admin = service.ensure_bootstrap_admin(username="admin", password="initial-secret")
    telegram_user = service.add_telegram_admin(
        telegram_user_id="42",
        telegram_username="oleg",
        display_name="Oleg",
        actor="admin",
        actor_user_id=admin.id,
    )
    payload = _telegram_payload(
        bot_token="telegram-token",
        data={
            "id": "42",
            "username": "oleg_new",
            "first_name": "Oleg",
            "auth_date": str(int(datetime(2026, 4, 28, tzinfo=UTC).timestamp())),
        },
    )

    with pytest.raises(AuthError, match="invalid Telegram auth"):
        service.login_telegram({**payload, "hash": "bad-hash"})
    with pytest.raises(AuthError, match="unknown Telegram user"):
        service.login_telegram(
            _telegram_payload(
                bot_token="telegram-token",
                data={"id": "99", "auth_date": payload["auth_date"]},
            )
        )

    login = service.login_telegram(payload)
    updated_user = (
        auth_session.execute(
            select(web_users_table).where(web_users_table.c.id == telegram_user.id)
        )
        .mappings()
        .one()
    )
    session_row = (
        auth_session.execute(
            select(web_auth_sessions_table).where(
                web_auth_sessions_table.c.auth_method == "telegram"
            )
        )
        .mappings()
        .one()
    )
    assert login.user.id == telegram_user.id
    assert updated_user["telegram_username"] == "oleg_new"
    assert updated_user["last_login_at"] is not None
    assert session_row["user_id"] == telegram_user.id


def test_disabled_users_cannot_login(auth_session):
    service = WebAuthService(auth_session, telegram_bot_token="bot-token")
    admin = service.ensure_bootstrap_admin(username="admin", password="initial-secret")
    service.disable_user(admin.id, actor="admin")

    with pytest.raises(AuthError, match="not active"):
        service.login_local(username="admin", password="initial-secret")


def _telegram_payload(*, bot_token: str, data: dict[str, str]) -> dict[str, str]:
    check_string = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    digest = hmac.new(secret_key, check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    return {**data, "hash": digest}


def _legacy_password_hash(password: str, *, iterations: int) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "$".join(
        [
            PBKDF2_ALGORITHM,
            str(iterations),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        ]
    )
