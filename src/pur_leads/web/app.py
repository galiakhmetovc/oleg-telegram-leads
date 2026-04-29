"""FastAPI application factory."""

from collections.abc import Callable
from pathlib import Path
import secrets
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from pur_leads.core.config import load_settings
from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.services.web_auth import WebAuthService
from pur_leads.web.routes_admin import router as admin_router
from pur_leads.web.routes_auth import router as auth_router
from pur_leads.web.routes_catalog import router as catalog_router
from pur_leads.web.routes_crm import router as crm_router
from pur_leads.web.routes_health import router as health_router
from pur_leads.web.routes_leads import router as leads_router
from pur_leads.web.routes_onboarding import router as onboarding_router
from pur_leads.web.routes_operations import router as operations_router
from pur_leads.web.routes_pages import router as pages_router
from pur_leads.web.routes_quality import router as quality_router
from pur_leads.web.routes_sources import router as sources_router
from pur_leads.web.routes_today import router as today_router


def create_app(
    *,
    database_path: Path | str | None = None,
    bootstrap_admin_username: str | None = None,
    bootstrap_admin_password: str | None = None,
    telegram_bot_token: str | None = None,
    web_session_duration_hours: int | None = None,
    web_session_cookie_name: str | None = None,
    web_cookie_secure: bool | None = None,
    backup_path: Path | str | None = None,
    bootstrap_admin_password_file: Path | str | None = None,
    local_secret_storage_path: Path | str | None = None,
    telegram_session_storage_path: Path | str | None = None,
    telegram_bot_api_base_url: str = "https://api.telegram.org",
    telegram_bot_api_transport: Any | None = None,
    userbot_login_client_factory: Callable[[], Any] | None = None,
) -> FastAPI:
    settings = load_settings()
    resolved_database_path = (
        Path(database_path) if database_path is not None else settings.database_path
    )
    engine = create_sqlite_engine(resolved_database_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    app = FastAPI(title="PUR Leads")
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.database_path = resolved_database_path
    app.state.backup_path = Path(backup_path) if backup_path is not None else settings.backup_path
    app.state.local_secret_storage_path = (
        Path(local_secret_storage_path)
        if local_secret_storage_path is not None
        else settings.local_secret_storage_path
    )
    app.state.telegram_session_storage_path = (
        Path(telegram_session_storage_path)
        if telegram_session_storage_path is not None
        else settings.telegram_session_storage_path
    )
    app.state.telegram_bot_token = telegram_bot_token or settings.telegram_bot_token
    app.state.telegram_bot_api_base_url = telegram_bot_api_base_url
    app.state.telegram_bot_api_transport = telegram_bot_api_transport
    app.state.userbot_login_client_factory = userbot_login_client_factory
    app.state.userbot_login_attempts = {}
    app.state.web_session_duration_hours = (
        web_session_duration_hours or settings.web_session_duration_hours
    )
    app.state.web_session_cookie_name = web_session_cookie_name or settings.web_session_cookie_name
    app.state.web_cookie_secure = (
        settings.web_cookie_secure if web_cookie_secure is None else web_cookie_secure
    )
    app.state.bootstrap_admin_username = (
        bootstrap_admin_username or settings.bootstrap_admin_username
    )
    app.state.bootstrap_admin_password_file = (
        Path(bootstrap_admin_password_file)
        if bootstrap_admin_password_file is not None
        else settings.bootstrap_admin_password_file
    )

    configured_bootstrap_password = (
        bootstrap_admin_password
        if bootstrap_admin_password is not None
        else settings.bootstrap_admin_password
    )
    _ensure_bootstrap_admin(
        session_factory=session_factory,
        username=app.state.bootstrap_admin_username,
        configured_password=_non_empty(configured_bootstrap_password),
        password_file=app.state.bootstrap_admin_password_file,
        telegram_bot_token=app.state.telegram_bot_token,
        session_duration_hours=app.state.web_session_duration_hours,
    )

    static_path = Path(__file__).with_name("static")
    app.mount("/static", StaticFiles(directory=static_path), name="static")
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(leads_router)
    app.include_router(onboarding_router)
    app.include_router(crm_router)
    app.include_router(catalog_router)
    app.include_router(sources_router)
    app.include_router(today_router)
    app.include_router(operations_router)
    app.include_router(quality_router)
    app.include_router(admin_router)
    app.include_router(pages_router)
    return app


def _ensure_bootstrap_admin(
    *,
    session_factory,
    username: str,
    configured_password: str | None,
    password_file: Path,
    telegram_bot_token: str | None,
    session_duration_hours: int,
) -> None:
    with session_factory() as session:
        auth_service = WebAuthService(
            session,
            telegram_bot_token=telegram_bot_token,
            session_duration_hours=session_duration_hours,
        )
        existing = auth_service.repository.get_user_by_local_username(username)
        if existing is not None and not existing.must_change_password:
            password_file.unlink(missing_ok=True)
            return

        existing_file_password = _read_bootstrap_password_file(password_file)
        password = configured_password or existing_file_password or _generate_bootstrap_password()
        needs_file_write = configured_password is not None or not password_file.exists()
        auth_service.ensure_bootstrap_admin(
            username=username,
            password=password,
            reset_password_if_must_change=existing is not None and needs_file_write,
        )
        if needs_file_write:
            _write_bootstrap_password_file(password_file, username=username, password=password)


def _generate_bootstrap_password() -> str:
    return secrets.token_urlsafe(24)


def _non_empty(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _read_bootstrap_password_file(path: Path) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("password="):
            password = line.split("=", 1)[1].strip()
            return password or None
    return None


def _write_bootstrap_password_file(path: Path, *, username: str, password: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "# Temporary bootstrap administrator password.",
                "# Change the password in the web interface; this file will be removed.",
                f"username={username}",
                f"password={password}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)
