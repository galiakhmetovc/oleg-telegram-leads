"""Onboarding routes for first-run Telegram setup."""

from __future__ import annotations

import base64
import binascii
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.integrations.telegram.bot_setup import (
    TelegramBotSetupClient,
    TelegramBotSetupError,
    notification_candidates_from_updates,
)
from pur_leads.integrations.telegram.userbot_login import (
    TelethonUserbotLoginClient,
    UserbotLoginPasswordRequired,
)
from pur_leads.models.telegram_sources import monitored_sources_table
from pur_leads.services.secrets import SecretRefService
from pur_leads.services.settings import SettingsService
from pur_leads.services.userbots import UserbotAccountService
from pur_leads.services.web_auth import SessionValidationResult
from pur_leads.web.dependencies import current_admin, get_session

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


class BotTokenRequest(BaseModel):
    token: str = Field(min_length=10)
    display_name: str = "Telegram bot"


class NotificationGroupRequest(BaseModel):
    chat_id: str = Field(min_length=1)
    title: str | None = None
    message_thread_id: int | None = None
    send_test: bool = True


class SessionFileUserbotRequest(BaseModel):
    display_name: str = Field(min_length=1)
    session_name: str = Field(min_length=1)
    session_file_name: str | None = None
    session_file_base64: str = Field(min_length=1)
    api_id: int = Field(gt=0)
    api_hash: str = Field(min_length=1)
    make_default: bool = True


class InteractiveUserbotStartRequest(BaseModel):
    display_name: str = Field(min_length=1)
    session_name: str = Field(min_length=1)
    api_id: int = Field(gt=0)
    api_hash: str = Field(min_length=1)
    phone: str = Field(min_length=3)
    make_default: bool = True


class InteractiveUserbotCompleteRequest(BaseModel):
    login_id: str = Field(min_length=1)
    code: str = Field(min_length=1)
    password: str | None = None


@router.get("/status")
def onboarding_status(
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    settings = SettingsService(session)
    bot_token_ref = settings.get("telegram_bot_token_secret_ref")
    notification_chat_id = settings.get("telegram_lead_notification_chat_id")
    userbot_count = len(UserbotAccountService(session).list_accounts())
    source_count = session.execute(
        select(func.count()).select_from(monitored_sources_table)
    ).scalar_one()
    steps = {
        "admin_password": {
            "done": not validated.user.must_change_password,
            "label": "Пароль администратора изменен",
        },
        "bot_token": {
            "done": _is_secret_ref_value(bot_token_ref),
            "label": "Обычный Telegram-бот подключен",
        },
        "notification_group": {
            "done": isinstance(notification_chat_id, str) and bool(notification_chat_id.strip()),
            "label": "Группа уведомлений выбрана",
        },
        "userbot": {
            "done": userbot_count > 0,
            "label": "Юзербот добавлен",
        },
        "first_source": {
            "done": source_count > 0,
            "label": "Первый чат для поиска лидов добавлен",
        },
    }
    required_keys = ("admin_password", "bot_token", "notification_group", "userbot")
    return {
        "steps": steps,
        "complete": all(steps[key]["done"] for key in required_keys),
    }


@router.post("/bot-token")
async def configure_bot_token(
    payload: BotTokenRequest,
    request: Request,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    token = payload.token.strip()
    client = _bot_setup_client(request)
    try:
        bot = await client.get_me(token)
    except TelegramBotSetupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    secret_id = SecretRefService(session).create_local_secret(
        secret_type="telegram_api",
        display_name=payload.display_name.strip() or "Telegram bot",
        value=token,
        storage_root=request.app.state.local_secret_storage_path,
    )
    SettingsService(session).set(
        "telegram_bot_token_secret_ref",
        {"secret_ref_id": secret_id},
        value_type="secret_ref",
        updated_by=_actor(validated),
        reason="configure Telegram bot token during onboarding",
    )
    request.app.state.telegram_bot_token = token
    return {
        "bot": {
            "id": bot.get("id") if isinstance(bot, dict) else None,
            "username": bot.get("username") if isinstance(bot, dict) else None,
        }
    }


@router.get("/notification-groups/discover")
async def discover_notification_groups(
    request: Request,
    _: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    token = _resolve_bot_token(request, session)
    if not token:
        raise HTTPException(status_code=400, detail="Telegram bot token is not configured")
    client = _bot_setup_client(request)
    try:
        updates = await client.get_updates(token)
    except TelegramBotSetupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"candidates": notification_candidates_from_updates(updates)}


@router.post("/notification-group")
async def configure_notification_group(
    payload: NotificationGroupRequest,
    request: Request,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    token = _resolve_bot_token(request, session)
    if not token:
        raise HTTPException(status_code=400, detail="Telegram bot token is not configured")
    if payload.send_test:
        try:
            await _bot_setup_client(request).send_message(
                token,
                chat_id=payload.chat_id.strip(),
                text="PUR Leads: группа уведомлений подключена.",
                message_thread_id=payload.message_thread_id,
            )
        except TelegramBotSetupError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    settings = SettingsService(session)
    actor = _actor(validated)
    settings.set(
        "telegram_lead_notification_chat_id",
        payload.chat_id.strip(),
        value_type="string",
        updated_by=actor,
        reason="configure Telegram notification group during onboarding",
    )
    settings.set(
        "telegram_lead_notification_thread_id",
        payload.message_thread_id,
        value_type="int",
        updated_by=actor,
        reason="configure Telegram notification topic during onboarding",
    )
    return {
        "notification_group": {
            "chat_id": payload.chat_id.strip(),
            "title": payload.title,
            "message_thread_id": payload.message_thread_id,
        }
    }


@router.post("/userbots/session-file")
def upload_userbot_session_file(
    payload: SessionFileUserbotRequest,
    request: Request,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    session_name = _safe_session_name(payload.session_name)
    session_path = _session_file_path(request.app.state.telegram_session_storage_path, session_name)
    session_path.write_bytes(_decode_session_file(payload.session_file_base64))
    session_path.chmod(0o600)
    account = _create_userbot_account(
        session,
        actor=_actor(validated),
        display_name=payload.display_name,
        session_name=session_name,
        session_path=session_path,
        secret_storage_root=request.app.state.local_secret_storage_path,
        api_id=payload.api_id,
        api_hash=payload.api_hash,
        make_default=payload.make_default,
    )
    return {"userbot": UserbotAccountService(session).public_payload(account)}


@router.post("/userbots/interactive/start")
async def start_interactive_userbot_login(
    payload: InteractiveUserbotStartRequest,
    request: Request,
    _: SessionValidationResult = Depends(current_admin),
) -> dict[str, Any]:
    session_name = _safe_session_name(payload.session_name)
    session_path = _session_file_path(request.app.state.telegram_session_storage_path, session_name)
    client = _userbot_login_client(request)
    phone_code_hash = await client.send_code(
        session_path=session_path,
        api_id=payload.api_id,
        api_hash=payload.api_hash,
        phone=payload.phone.strip(),
    )
    if session_path.exists():
        session_path.chmod(0o600)
    login_id = new_id()
    request.app.state.userbot_login_attempts[login_id] = {
        "display_name": payload.display_name,
        "session_name": session_name,
        "session_path": str(session_path),
        "api_id": payload.api_id,
        "api_hash": payload.api_hash,
        "phone": payload.phone.strip(),
        "phone_code_hash": phone_code_hash,
        "make_default": payload.make_default,
    }
    return {"login_id": login_id, "status": "code_sent"}


@router.post("/userbots/interactive/complete")
async def complete_interactive_userbot_login(
    payload: InteractiveUserbotCompleteRequest,
    request: Request,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    attempt = request.app.state.userbot_login_attempts.pop(payload.login_id, None)
    if not attempt:
        raise HTTPException(status_code=404, detail="Login attempt not found")
    session_path = Path(attempt["session_path"])
    client = _userbot_login_client(request)
    try:
        user = await client.sign_in(
            session_path=session_path,
            api_id=int(attempt["api_id"]),
            api_hash=str(attempt["api_hash"]),
            phone=str(attempt["phone"]),
            code=payload.code.strip(),
            phone_code_hash=str(attempt["phone_code_hash"]),
            password=payload.password,
        )
    except UserbotLoginPasswordRequired as exc:
        request.app.state.userbot_login_attempts[payload.login_id] = attempt
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if session_path.exists():
        session_path.chmod(0o600)
    account = _create_userbot_account(
        session,
        actor=_actor(validated),
        display_name=str(attempt["display_name"]),
        session_name=str(attempt["session_name"]),
        session_path=session_path,
        secret_storage_root=request.app.state.local_secret_storage_path,
        api_id=int(attempt["api_id"]),
        api_hash=str(attempt["api_hash"]),
        make_default=bool(attempt["make_default"]),
        telegram_user_id=user.get("telegram_user_id") if isinstance(user, dict) else None,
        telegram_username=user.get("telegram_username") if isinstance(user, dict) else None,
    )
    return {"userbot": UserbotAccountService(session).public_payload(account)}


def _create_userbot_account(
    session: Session,
    *,
    actor: str,
    display_name: str,
    session_name: str,
    session_path: Path,
    secret_storage_root: Path | str,
    api_id: int,
    api_hash: str,
    make_default: bool,
    telegram_user_id: str | None = None,
    telegram_username: str | None = None,
):
    secret_id = SecretRefService(session).create_local_secret(
        secret_type="telegram_api",
        display_name="Telegram API hash",
        value=api_hash,
        storage_root=secret_storage_root,
    )
    settings = SettingsService(session)
    settings.set(
        "telegram_api_id",
        api_id,
        value_type="int",
        updated_by=actor,
        reason="configure Telegram API id during onboarding",
    )
    settings.set(
        "telegram_api_hash_secret_ref",
        {"secret_ref_id": secret_id},
        value_type="secret_ref",
        updated_by=actor,
        reason="configure Telegram API hash during onboarding",
    )
    account = UserbotAccountService(session).create_account(
        display_name=display_name.strip(),
        telegram_user_id=telegram_user_id,
        telegram_username=telegram_username,
        session_name=session_name,
        session_path=str(session_path),
        actor=actor,
    )
    if make_default:
        SettingsService(session).set(
            "telegram_default_userbot_account_id",
            account.id,
            value_type="string",
            updated_by=actor,
            reason="select default Telegram userbot during onboarding",
        )
    return account


def _decode_session_file(value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid session file encoding") from exc


def _safe_session_name(value: str) -> str:
    raw = Path(value.strip()).stem or Path(value.strip()).name
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._-")
    return normalized or f"userbot-{new_id()}"


def _session_file_path(root: Path | str, session_name: str) -> Path:
    path = Path(root)
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path / f"{session_name}.session"


def _resolve_bot_token(request: Request, session: Session) -> str | None:
    try:
        token = SecretRefService(session).resolve_setting_secret("telegram_bot_token_secret_ref")
    except (FileNotFoundError, KeyError, ValueError):
        token = None
    return token or request.app.state.telegram_bot_token


def _bot_setup_client(request: Request) -> TelegramBotSetupClient:
    return TelegramBotSetupClient(
        base_url=request.app.state.telegram_bot_api_base_url,
        transport=request.app.state.telegram_bot_api_transport,
    )


def _userbot_login_client(request: Request):
    factory = request.app.state.userbot_login_client_factory
    return factory() if factory else TelethonUserbotLoginClient()


def _is_secret_ref_value(value: Any) -> bool:
    return isinstance(value, dict) and isinstance(value.get("secret_ref_id"), str)


def _actor(validated: SessionValidationResult) -> str:
    return (
        validated.user.local_username
        or validated.user.telegram_user_id
        or validated.user.telegram_username
        or validated.user.id
    )
