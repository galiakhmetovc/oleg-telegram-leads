"""Authentication routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from pur_leads.repositories.web_auth import WebUserRecord
from pur_leads.services.web_auth import (
    AuthError,
    LoginResult,
    SessionValidationResult,
    WebAuthService,
)
from pur_leads.web.dependencies import current_admin, get_auth_service

router = APIRouter(prefix="/api")


class LocalLoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    new_password: str


@router.post("/auth/local")
def login_local(
    payload: LocalLoginRequest,
    request: Request,
    response: Response,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> dict[str, Any]:
    try:
        result = auth_service.login_local(
            username=payload.username,
            password=payload.password,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    _set_session_cookie(request, response, result)
    return {"user": _user_payload(result.user)}


@router.post("/auth/telegram")
def login_telegram(
    payload: dict[str, Any],
    request: Request,
    response: Response,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> dict[str, Any]:
    try:
        result = auth_service.login_telegram(
            payload,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    _set_session_cookie(request, response, result)
    return {"user": _user_payload(result.user)}


@router.post("/auth/change-password")
def change_password(
    payload: ChangePasswordRequest,
    validated: SessionValidationResult = Depends(current_admin),
    auth_service: WebAuthService = Depends(get_auth_service),
) -> dict[str, Any]:
    user = auth_service.change_password(
        validated.user.id,
        new_password=payload.new_password,
        actor=validated.user.local_username or validated.user.telegram_user_id or validated.user.id,
    )
    return {"user": _user_payload(user)}


@router.post("/auth/logout")
def logout(
    request: Request,
    response: Response,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> dict[str, str]:
    cookie_name: str = request.app.state.web_session_cookie_name
    session_token = request.cookies.get(cookie_name)
    if session_token:
        auth_service.logout(session_token, actor="web")
    response.delete_cookie(cookie_name)
    return {"status": "ok"}


@router.get("/me")
def me(validated: SessionValidationResult = Depends(current_admin)) -> dict[str, Any]:
    return {"user": _user_payload(validated.user)}


def _set_session_cookie(request: Request, response: Response, result: LoginResult) -> None:
    response.set_cookie(
        request.app.state.web_session_cookie_name,
        result.session_token,
        httponly=True,
        secure=request.app.state.web_cookie_secure,
        samesite="lax",
        max_age=int(request.app.state.web_session_duration_hours * 3600),
    )


def _user_payload(user: WebUserRecord) -> dict[str, Any]:
    return {
        "id": user.id,
        "telegram_user_id": user.telegram_user_id,
        "telegram_username": user.telegram_username,
        "display_name": user.display_name,
        "auth_type": user.auth_type,
        "local_username": user.local_username,
        "must_change_password": user.must_change_password,
        "role": user.role,
        "status": user.status,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }
