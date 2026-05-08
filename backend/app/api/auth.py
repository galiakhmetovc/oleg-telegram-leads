from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.core.auth import create_session_token, credentials_are_valid, verify_session_token
from app.core.config import Settings, get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class AuthStatusResponse(BaseModel):
    authenticated: bool
    username: str | None


@router.post("/login", response_model=AuthStatusResponse)
async def login(
    request: LoginRequest,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> AuthStatusResponse:
    if not credentials_are_valid(
        username=request.username,
        password=request.password,
        settings=settings,
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    token = create_session_token(username=settings.auth_username, settings=settings)
    response.set_cookie(
        settings.auth_cookie_name,
        token,
        httponly=True,
        max_age=settings.auth_session_ttl_seconds,
        samesite="lax",
        secure=False,
    )
    return AuthStatusResponse(authenticated=True, username=settings.auth_username)


@router.post("/logout", response_model=AuthStatusResponse)
async def logout(
    response: Response,
    settings: Settings = Depends(get_settings),
) -> AuthStatusResponse:
    response.delete_cookie(settings.auth_cookie_name, samesite="lax")
    return AuthStatusResponse(authenticated=False, username=None)


@router.get("/me", response_model=AuthStatusResponse)
async def me(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> AuthStatusResponse:
    if not settings.auth_enabled:
        return AuthStatusResponse(authenticated=True, username=settings.auth_username)
    session = verify_session_token(
        request.cookies.get(settings.auth_cookie_name),
        settings=settings,
    )
    return AuthStatusResponse(
        authenticated=session is not None,
        username=session.username if session else None,
    )
