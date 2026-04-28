"""FastAPI application factory."""

from pathlib import Path

from fastapi import FastAPI

from pur_leads.core.config import load_settings
from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.session import create_session_factory
from pur_leads.services.web_auth import WebAuthService
from pur_leads.web.routes_auth import router as auth_router
from pur_leads.web.routes_health import router as health_router


def create_app(
    *,
    database_path: Path | str | None = None,
    bootstrap_admin_username: str | None = None,
    bootstrap_admin_password: str | None = None,
    telegram_bot_token: str | None = None,
    web_session_duration_hours: int | None = None,
    web_session_cookie_name: str | None = None,
    web_cookie_secure: bool | None = None,
) -> FastAPI:
    settings = load_settings()
    resolved_database_path = (
        Path(database_path) if database_path is not None else settings.database_path
    )
    engine = create_sqlite_engine(resolved_database_path)
    session_factory = create_session_factory(engine)

    app = FastAPI(title="PUR Leads")
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.telegram_bot_token = telegram_bot_token or settings.telegram_bot_token
    app.state.web_session_duration_hours = (
        web_session_duration_hours or settings.web_session_duration_hours
    )
    app.state.web_session_cookie_name = web_session_cookie_name or settings.web_session_cookie_name
    app.state.web_cookie_secure = (
        settings.web_cookie_secure if web_cookie_secure is None else web_cookie_secure
    )

    username = bootstrap_admin_username or settings.bootstrap_admin_username
    password = bootstrap_admin_password or settings.bootstrap_admin_password
    if password:
        with session_factory() as session:
            WebAuthService(
                session,
                telegram_bot_token=app.state.telegram_bot_token,
                session_duration_hours=app.state.web_session_duration_hours,
            ).ensure_bootstrap_admin(username=username, password=password)

    app.include_router(health_router)
    app.include_router(auth_router)
    return app
