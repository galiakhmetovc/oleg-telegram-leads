"""FastAPI dependency helpers."""

from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session, sessionmaker

from pur_leads.services.web_auth import AuthError, SessionValidationResult, WebAuthService


def get_session(request: Request) -> Iterator[Session]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session


def get_auth_service(
    request: Request,
    session: Session = Depends(get_session),
) -> WebAuthService:
    return WebAuthService(
        session,
        telegram_bot_token=request.app.state.telegram_bot_token,
        session_duration_hours=request.app.state.web_session_duration_hours,
    )


def current_admin(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> SessionValidationResult:
    cookie_name: str = request.app.state.web_session_cookie_name
    session_token = request.cookies.get(cookie_name)
    if not session_token:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        validated = auth_service.validate_session(session_token)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    if validated.user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return validated
