"""Admin user and settings routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from pur_leads.repositories.settings import SettingRecord
from pur_leads.repositories.userbots import UserbotAccountRecord
from pur_leads.repositories.web_auth import WebUserRecord
from pur_leads.services.settings import DEFAULT_SETTINGS, RawSecretValueError, SettingsService
from pur_leads.services.userbots import UserbotAccountService
from pur_leads.services.web_auth import (
    AuthError,
    SessionValidationResult,
    UserConflictError,
    WebAuthService,
)
from pur_leads.web.dependencies import current_admin, get_auth_service, get_session

router = APIRouter(prefix="/api")


class TelegramAdminRequest(BaseModel):
    telegram_user_id: str
    telegram_username: str | None = None
    display_name: str | None = None


class UserUpdateRequest(BaseModel):
    status: str | None = None
    display_name: str | None = None


class SettingUpdateRequest(BaseModel):
    value: Any
    value_type: str
    scope: str = "global"
    scope_id: str | None = None
    reason: str | None = None
    description: str | None = None
    requires_restart: bool = False


class UserbotCreateRequest(BaseModel):
    display_name: str
    session_name: str
    session_path: str
    telegram_user_id: str | None = None
    telegram_username: str | None = None
    status: str = "active"
    priority: str = "normal"
    max_parallel_telegram_jobs: int = 1
    flood_sleep_threshold_seconds: int = 60
    make_default: bool = False


@router.get("/admin/users")
def list_admin_users(
    _validated: SessionValidationResult = Depends(current_admin),
    auth_service: WebAuthService = Depends(get_auth_service),
) -> dict[str, Any]:
    return {"items": [_user_payload(user) for user in auth_service.list_admin_users()]}


@router.post("/admin/users/telegram")
def add_telegram_admin(
    payload: TelegramAdminRequest,
    validated: SessionValidationResult = Depends(current_admin),
    auth_service: WebAuthService = Depends(get_auth_service),
) -> dict[str, Any]:
    try:
        user = auth_service.add_telegram_admin(
            telegram_user_id=payload.telegram_user_id,
            telegram_username=payload.telegram_username,
            display_name=payload.display_name,
            actor=_actor(validated),
            actor_user_id=validated.user.id,
        )
    except UserConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AuthError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"user": _user_payload(user)}


@router.patch("/admin/users/{user_id}")
def update_admin_user(
    user_id: str,
    payload: UserUpdateRequest,
    validated: SessionValidationResult = Depends(current_admin),
    auth_service: WebAuthService = Depends(get_auth_service),
) -> dict[str, Any]:
    try:
        user = auth_service.update_admin_user(
            user_id,
            actor=_actor(validated),
            actor_user_id=validated.user.id,
            status=payload.status,
            display_name=payload.display_name,
            update_display_name="display_name" in payload.model_fields_set,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="User not found") from exc
    except AuthError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"user": _user_payload(user)}


@router.get("/admin/userbots")
def list_userbot_accounts(
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = UserbotAccountService(session)
    return {"items": [_userbot_payload(service, account) for account in service.list_accounts()]}


@router.post("/admin/userbots")
def create_userbot_account(
    payload: UserbotCreateRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    actor = _actor(validated)
    service = UserbotAccountService(session)
    try:
        account = service.create_account(
            display_name=payload.display_name,
            session_name=payload.session_name,
            session_path=payload.session_path,
            actor=actor,
            telegram_user_id=payload.telegram_user_id,
            telegram_username=payload.telegram_username,
            status=payload.status,
            priority=payload.priority,
            max_parallel_telegram_jobs=payload.max_parallel_telegram_jobs,
            flood_sleep_threshold_seconds=payload.flood_sleep_threshold_seconds,
        )
        if payload.make_default:
            SettingsService(session).set(
                "telegram_default_userbot_account_id",
                account.id,
                value_type="string",
                updated_by=actor,
                reason="userbot created as default",
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"userbot": _userbot_payload(service, account)}


@router.get("/settings")
def list_settings(
    scope: str | None = None,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = SettingsService(session)
    records = service.list(scope=scope)
    items = [_setting_payload(record, is_default=False) for record in records]
    if scope in (None, "global"):
        explicit_global_keys = {
            record.key for record in records if record.scope == "global" and record.scope_id == ""
        }
        items.extend(
            {
                "key": key,
                "value": default.value,
                "value_type": default.value_type,
                "scope": "global",
                "scope_id": "",
                "description": None,
                "requires_restart": False,
                "is_secret_ref": default.value_type == "secret_ref",
                "updated_by": None,
                "updated_at": None,
                "is_default": True,
            }
            for key, default in DEFAULT_SETTINGS.items()
            if key not in explicit_global_keys
        )
    return {"items": sorted(items, key=lambda item: (item["scope"], item["key"]))}


@router.put("/settings/{key}")
def update_setting(
    key: str,
    payload: SettingUpdateRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = SettingsService(session)
    try:
        service.set(
            key,
            payload.value,
            value_type=payload.value_type,
            updated_by=_actor(validated),
            scope=payload.scope,
            scope_id=payload.scope_id,
            reason=payload.reason,
            description=payload.description,
            requires_restart=payload.requires_restart,
        )
    except (RawSecretValueError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record = service.repository.get(key, scope=payload.scope, scope_id=payload.scope_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Setting not found")
    return {"setting": _setting_payload(record, is_default=False)}


def _actor(validated: SessionValidationResult) -> str:
    return validated.user.local_username or validated.user.telegram_user_id or validated.user.id


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
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "last_login_at": user.last_login_at,
    }


def _setting_payload(record: SettingRecord, *, is_default: bool) -> dict[str, Any]:
    return {
        "key": record.key,
        "value": record.value_json,
        "value_type": record.value_type,
        "scope": record.scope,
        "scope_id": record.scope_id,
        "description": record.description,
        "requires_restart": record.requires_restart,
        "is_secret_ref": record.is_secret_ref,
        "updated_by": record.updated_by,
        "updated_at": record.updated_at,
        "is_default": is_default,
    }


def _userbot_payload(
    service: UserbotAccountService,
    account: UserbotAccountRecord,
) -> dict[str, Any]:
    return service.public_payload(account)
