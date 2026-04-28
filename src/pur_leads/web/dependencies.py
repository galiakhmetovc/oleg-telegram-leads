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
        _record_authorization_denied(
            request,
            auth_service,
            actor="anonymous",
            reason="missing_session",
        )
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        validated = auth_service.validate_session(session_token)
    except AuthError as exc:
        _record_authorization_denied(
            request,
            auth_service,
            actor="unknown",
            reason=str(exc),
        )
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    if validated.user.role != "admin":
        _record_authorization_denied(
            request,
            auth_service,
            actor=validated.user.local_username
            or validated.user.telegram_user_id
            or validated.user.id,
            reason="admin_role_required",
        )
        raise HTTPException(status_code=403, detail="Admin role required")
    return validated


def _record_authorization_denied(
    request: Request,
    auth_service: WebAuthService,
    *,
    actor: str,
    reason: str,
) -> None:
    auth_service.audit.record_change(
        actor=actor,
        action="web_auth.protected_route_denied",
        entity_type="web_route",
        entity_id=request.url.path,
        old_value_json=None,
        new_value_json={"reason": reason, "method": request.method},
    )
