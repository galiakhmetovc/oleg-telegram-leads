"""Onboarding routes for first-run Telegram setup."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.integrations.telegram.bot_setup import (
    TelegramBotSetupClient,
    TelegramBotSetupError,
    notification_candidates_from_updates,
)
from pur_leads.integrations.telegram.userbot_login import (
    TelethonUserbotLoginClient,
    UserbotLoginPasswordRequired,
)
from pur_leads.models.ai import ai_provider_accounts_table
from pur_leads.models.telegram_sources import (
    monitored_sources_table,
    telegram_bots_table,
    telegram_notification_groups_table,
    userbot_accounts_table,
)
from pur_leads.services.ai_registry import AiRegistryService
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
    bot_id: str | None = None
    chat_id: str = Field(min_length=1)
    title: str | None = None
    chat_type: str | None = None
    message_thread_id: int | None = None
    send_test: bool = True


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


class LlmProviderRequest(BaseModel):
    base_url: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    display_name: str = "Z.AI"


class LlmDefaultModelRequest(BaseModel):
    model_id: str = Field(min_length=1)


@router.get("/status")
def onboarding_status(
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    settings = SettingsService(session)
    bot_token_ref = settings.get("telegram_bot_token_secret_ref")
    zai_api_key_ref = settings.get("zai_api_key_secret_ref")
    bot_count = _active_bot_count(session)
    notification_group_count = _active_notification_group_count(session)
    userbot_count = len(UserbotAccountService(session).list_accounts())
    llm_provider_count = len(_llm_provider_accounts(AiRegistryService(session).snapshot()))
    source_count = session.execute(
        select(func.count()).select_from(monitored_sources_table)
    ).scalar_one()
    steps = {
        "admin_password": {
            "done": not validated.user.must_change_password,
            "label": "Пароль администратора изменен",
        },
        "bot_token": {
            "done": bot_count > 0 or _is_secret_ref_value(bot_token_ref),
            "label": "Обычный Telegram-бот подключен",
        },
        "notification_group": {
            "done": notification_group_count > 0,
            "label": "Группа уведомлений выбрана",
        },
        "userbot": {
            "done": userbot_count > 0,
            "label": "Юзербот добавлен",
        },
        "llm_provider": {
            "done": _is_secret_ref_value(zai_api_key_ref) and llm_provider_count > 0,
            "label": "Провайдер LLM подключен",
        },
        "first_source": {
            "done": source_count > 0,
            "label": "Первый чат для поиска лидов добавлен",
        },
    }
    required_keys = (
        "admin_password",
        "bot_token",
        "notification_group",
        "userbot",
        "llm_provider",
    )
    return {
        "steps": steps,
        "complete": all(steps[key]["done"] for key in required_keys),
    }


@router.get("/resources")
async def list_resources(
    request: Request,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    await _refresh_missing_bot_usernames(request, session)
    return {"items": _resource_payloads(session)}


@router.get("/bots")
async def list_bots(
    request: Request,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    await _refresh_missing_bot_usernames(request, session)
    return {"items": _bot_payloads(session)}


@router.get("/userbots")
def list_userbots(
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    settings = SettingsService(session)
    api_hash_ref = settings.get("telegram_api_hash_secret_ref")
    return {
        "items": [
            UserbotAccountService(session).public_payload(account)
            for account in UserbotAccountService(session).list_accounts()
            if account.status == "active"
        ],
        "credentials": {
            "telegram_api_id": settings.get("telegram_api_id"),
            "api_hash_configured": _is_secret_ref_value(api_hash_ref),
        },
    }


@router.delete("/userbots/{userbot_id}")
def delete_userbot(
    userbot_id: str,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    row = (
        session.execute(
            select(userbot_accounts_table).where(
                userbot_accounts_table.c.id == userbot_id,
                userbot_accounts_table.c.status == "active",
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Userbot not found")
    session_path = Path(str(row["session_path"]))
    if session_path.exists():
        session_path.unlink()
    session.execute(
        update(userbot_accounts_table)
        .where(userbot_accounts_table.c.id == userbot_id)
        .values(status="disabled", updated_at=utc_now())
    )
    settings = SettingsService(session)
    if settings.get("telegram_default_userbot_account_id") == userbot_id:
        settings.set(
            "telegram_default_userbot_account_id",
            "",
            value_type="string",
            updated_by=_actor(validated),
            reason="remove default Telegram userbot during onboarding",
        )
    session.commit()
    return {
        "items": [
            UserbotAccountService(session).public_payload(account)
            for account in UserbotAccountService(session).list_accounts()
            if account.status == "active"
        ]
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
    actor = _actor(validated)
    SettingsService(session).set(
        "telegram_bot_token_secret_ref",
        {"secret_ref_id": secret_id},
        value_type="secret_ref",
        updated_by=actor,
        reason="configure Telegram bot token during onboarding",
    )
    bot_payload = _upsert_telegram_bot(
        session,
        display_name=payload.display_name.strip() or "Telegram bot",
        telegram_bot_id=str(bot.get("id")) if isinstance(bot, dict) and bot.get("id") else None,
        telegram_username=bot.get("username") if isinstance(bot, dict) else None,
        token_secret_ref=secret_id,
    )
    request.app.state.telegram_bot_token = token
    return {
        "bot": bot_payload,
        "items": _bot_payloads(session),
    }


@router.delete("/bots/{bot_id}")
def delete_bot(
    bot_id: str,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    bot = _bot_by_id(session, bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Telegram bot not found")
    now = utc_now()
    session.execute(
        update(telegram_bots_table)
        .where(telegram_bots_table.c.id == bot_id)
        .values(status="revoked", updated_at=now)
    )
    session.execute(
        update(telegram_notification_groups_table)
        .where(telegram_notification_groups_table.c.telegram_bot_id == bot_id)
        .values(status="revoked", updated_at=now)
    )
    _refresh_default_notification_settings(session, actor=_actor(validated))
    session.commit()
    return {"items": _bot_payloads(session)}


@router.get("/notification-groups/discover")
async def discover_notification_groups(
    request: Request,
    bot_id: str | None = None,
    _: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    token = _resolve_bot_token(request, session, bot_id=bot_id)
    if not token:
        raise HTTPException(status_code=400, detail="Telegram bot token is not configured")
    client = _bot_setup_client(request)
    try:
        updates = await client.get_updates(token)
    except TelegramBotSetupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"candidates": notification_candidates_from_updates(updates)}


@router.get("/notification-groups")
def list_notification_groups(
    bot_id: str | None = None,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return {"items": _notification_group_payloads(session, bot_id=bot_id)}


@router.post("/notification-group")
async def configure_notification_group(
    payload: NotificationGroupRequest,
    request: Request,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    bot_id = payload.bot_id or _first_active_bot_id(session)
    if not bot_id:
        raise HTTPException(status_code=400, detail="Telegram bot is not configured")
    bot = _bot_by_id(session, bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Telegram bot not found")
    token = _resolve_bot_token(request, session, bot_id=bot_id)
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
    actor = _actor(validated)
    group = _upsert_notification_group(
        session,
        telegram_bot_id=bot_id,
        chat_id=payload.chat_id.strip(),
        title=payload.title,
        chat_type=payload.chat_type,
        message_thread_id=payload.message_thread_id,
    )
    _set_default_notification_settings(
        session,
        actor=actor,
        token_secret_ref=str(bot["token_secret_ref"]),
        chat_id=payload.chat_id.strip(),
        message_thread_id=payload.message_thread_id,
    )
    return {"notification_group": group, "items": _notification_group_payloads(session)}


@router.delete("/notification-groups/{group_id}")
def delete_notification_group(
    group_id: str,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    row = _notification_group_by_id(session, group_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Notification group not found")
    session.execute(
        update(telegram_notification_groups_table)
        .where(telegram_notification_groups_table.c.id == group_id)
        .values(status="revoked", updated_at=utc_now())
    )
    _refresh_default_notification_settings(session, actor=_actor(validated))
    session.commit()
    return {"items": _notification_group_payloads(session)}


def _set_default_notification_settings(
    session: Session,
    *,
    actor: str,
    token_secret_ref: str,
    chat_id: str | None,
    message_thread_id: int | None,
) -> None:
    settings = SettingsService(session)
    settings.set(
        "telegram_bot_token_secret_ref",
        {"secret_ref_id": token_secret_ref},
        value_type="secret_ref",
        updated_by=actor,
        reason="select default Telegram bot during onboarding",
    )
    settings.set(
        "telegram_lead_notification_chat_id",
        chat_id or "",
        value_type="string",
        updated_by=actor,
        reason="configure Telegram notification group during onboarding",
    )
    settings.set(
        "telegram_lead_notification_thread_id",
        message_thread_id,
        value_type="int",
        updated_by=actor,
        reason="configure Telegram notification topic during onboarding",
    )


@router.post("/llm-provider")
def configure_llm_provider(
    payload: LlmProviderRequest,
    request: Request,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    actor = _actor(validated)
    base_url = payload.base_url.strip().rstrip("/")
    secret_id = SecretRefService(session).create_local_secret(
        secret_type="ai_api_key",
        display_name=payload.display_name.strip() or "Z.AI",
        value=payload.api_key.strip(),
        storage_root=request.app.state.local_secret_storage_path,
    )
    settings = SettingsService(session)
    settings.set(
        "zai_api_key_secret_ref",
        {"secret_ref_id": secret_id},
        value_type="secret_ref",
        updated_by=actor,
        reason="configure Z.AI API key during onboarding",
    )
    for key in ("catalog_llm_base_url", "lead_llm_shadow_base_url"):
        settings.set(
            key,
            base_url,
            value_type="string",
            updated_by=actor,
            reason="configure Z.AI base URL during onboarding",
        )
    for key in ("catalog_llm_provider", "lead_llm_shadow_provider"):
        settings.set(
            key,
            "zai",
            value_type="string",
            updated_by=actor,
            reason="configure Z.AI provider during onboarding",
        )
    registry = AiRegistryService(session)
    registry.bootstrap_defaults(actor=actor)
    registry.configure_zai_account(
        actor=actor,
        base_url=base_url,
        auth_secret_ref=f"secret_ref:{secret_id}",
        display_name=payload.display_name.strip() or "Z.AI",
    )
    snapshot = registry.snapshot()
    provider = next(
        (item for item in snapshot["providers"] if item["provider_key"] == "zai"),
        None,
    )
    account = next(
        (
            item
            for item in snapshot["accounts"]
            if item["auth_secret_ref"] == f"secret_ref:{secret_id}"
        ),
        None,
    )
    return {
        "provider": provider,
        "account": account,
        "models": snapshot["models"],
        "routes": snapshot["routes"],
        "accounts": _llm_provider_accounts(snapshot),
    }


@router.get("/llm-providers")
def list_llm_providers(
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return {"items": _llm_provider_accounts(AiRegistryService(session).snapshot())}


@router.delete("/llm-providers/{account_id}")
def delete_llm_provider(
    account_id: str,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    row = (
        session.execute(
            select(ai_provider_accounts_table).where(ai_provider_accounts_table.c.id == account_id)
        )
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="LLM provider account not found")
    session.execute(
        update(ai_provider_accounts_table)
        .where(ai_provider_accounts_table.c.id == account_id)
        .values(enabled=False, updated_at=utc_now())
    )
    session.commit()
    return {"items": _llm_provider_accounts(AiRegistryService(session).snapshot())}


@router.post("/llm-default-model")
def configure_default_llm_model(
    payload: LlmDefaultModelRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    actor = _actor(validated)
    registry = AiRegistryService(session)
    snapshot = registry.snapshot()
    model = next((item for item in snapshot["models"] if item["id"] == payload.model_id), None)
    if model is None:
        raise HTTPException(status_code=404, detail="AI model not found")
    if model["model_type"] != "language":
        raise HTTPException(status_code=400, detail="Default LLM model must be a language model")
    catalog_route = registry.upsert_agent_route(
        agent_key="catalog_extractor",
        model_id=payload.model_id,
        route_role="primary",
        actor=actor,
        priority=10,
        max_output_tokens=4096,
        temperature=0.0,
        enabled=True,
        structured_output_required=True,
    )
    lead_route = registry.upsert_agent_route(
        agent_key="lead_detector",
        model_id=payload.model_id,
        route_role="shadow",
        actor=actor,
        priority=10,
        max_output_tokens=512,
        temperature=0.0,
        enabled=True,
        structured_output_required=True,
    )
    settings = SettingsService(session)
    for key in ("catalog_llm_model", "lead_llm_shadow_model"):
        settings.set(
            key,
            model["provider_model_name"],
            value_type="string",
            updated_by=actor,
            reason="select default LLM model during onboarding",
        )
    return {"model": model, "routes": [catalog_route, lead_route]}


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


def _safe_session_name(value: str) -> str:
    raw = Path(value.strip()).stem or Path(value.strip()).name
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._-")
    return normalized or f"userbot-{new_id()}"


def _session_file_path(root: Path | str, session_name: str) -> Path:
    path = Path(root)
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path / f"{session_name}.session"


def _active_bot_count(session: Session) -> int:
    return int(
        session.execute(
            select(func.count())
            .select_from(telegram_bots_table)
            .where(telegram_bots_table.c.status == "active")
        ).scalar_one()
    )


def _active_notification_group_count(session: Session) -> int:
    return int(
        session.execute(
            select(func.count())
            .select_from(telegram_notification_groups_table)
            .where(telegram_notification_groups_table.c.status == "active")
        ).scalar_one()
    )


def _resource_payloads(session: Session) -> list[dict[str, Any]]:
    settings = SettingsService(session)
    api_hash_ref = settings.get("telegram_api_hash_secret_ref")
    credentials = {
        "telegram_api_id": settings.get("telegram_api_id"),
        "api_hash_configured": _is_secret_ref_value(api_hash_ref),
    }
    resources: list[dict[str, Any]] = []
    resources.extend(
        _notification_group_resource_payload(group)
        for group in _notification_group_payloads(session)
    )
    resources.extend(_bot_resource_payload(bot) for bot in _bot_payloads(session))
    resources.extend(
        _llm_provider_resource_payload(account)
        for account in _llm_provider_accounts(AiRegistryService(session).snapshot())
    )
    resources.extend(
        _userbot_resource_payload(
            UserbotAccountService(session).public_payload(account),
            credentials=credentials,
        )
        for account in UserbotAccountService(session).list_accounts()
        if account.status == "active"
    )
    return resources


def _notification_group_resource_payload(group: dict[str, Any]) -> dict[str, Any]:
    title = str(group.get("title") or group.get("chat_id") or "Группа уведомлений")
    detail = f"{group.get('bot_name') or 'бот'} / {group.get('chat_id') or ''}".strip()
    if group.get("message_thread_id"):
        detail = f"{detail} / topic {group['message_thread_id']}"
    return {
        "resource_id": f"telegram_notification_group:{group['id']}",
        "id": group["id"],
        "resource_type": "telegram_notification_group",
        "type_label": "Группа уведомлений",
        "display_name": title,
        "status": group["status"],
        "health": group["status"],
        "detail": detail,
        "parent_resource_id": f"telegram_bot:{group['bot_id']}",
        "delete_path": f"/api/onboarding/notification-groups/{group['id']}",
        "metadata": {
            "chat_id": group.get("chat_id"),
            "chat_type": group.get("chat_type"),
            "message_thread_id": group.get("message_thread_id"),
        },
    }


def _bot_resource_payload(bot: dict[str, Any]) -> dict[str, Any]:
    username = bot.get("telegram_username") or bot.get("username")
    return {
        "resource_id": f"telegram_bot:{bot['id']}",
        "id": bot["id"],
        "resource_type": "telegram_bot",
        "type_label": "Telegram-бот",
        "display_name": bot.get("display_name") or username or "Telegram bot",
        "status": bot["status"],
        "health": bot["status"],
        "detail": f"@{username}" if username else "username не получен",
        "parent_resource_id": None,
        "delete_path": f"/api/onboarding/bots/{bot['id']}",
        "metadata": {"telegram_bot_id": bot.get("telegram_bot_id")},
    }


def _llm_provider_resource_payload(account: dict[str, Any]) -> dict[str, Any]:
    provider_key = account.get("provider_key") or "unknown"
    base_url = account.get("base_url") or ""
    return {
        "resource_id": f"ai_provider_account:{account['id']}",
        "id": account["id"],
        "resource_type": "ai_provider_account",
        "type_label": "LLM-провайдер",
        "display_name": account.get("display_name") or "LLM provider",
        "status": "active" if account.get("enabled") else "disabled",
        "health": "active" if account.get("enabled") else "disabled",
        "detail": f"{provider_key} / {base_url}",
        "parent_resource_id": None,
        "delete_path": f"/api/onboarding/llm-providers/{account['id']}",
        "metadata": {"provider_key": provider_key},
    }


def _userbot_resource_payload(
    userbot: dict[str, Any],
    *,
    credentials: dict[str, Any],
) -> dict[str, Any]:
    username = userbot.get("telegram_username")
    api_id = credentials.get("telegram_api_id")
    api_hash_status = (
        "API hash сохранен" if credentials.get("api_hash_configured") else "API hash не сохранен"
    )
    return {
        "resource_id": f"telegram_userbot:{userbot['id']}",
        "id": userbot["id"],
        "resource_type": "telegram_userbot",
        "type_label": "Telegram-юзербот",
        "display_name": userbot.get("display_name") or userbot.get("session_name") or "Юзербот",
        "status": userbot["status"],
        "health": userbot["status"],
        "detail": f"{'@' + username if username else userbot.get('session_name') or ''}; API ID {api_id or 'не указан'}; {api_hash_status}",
        "parent_resource_id": None,
        "delete_path": f"/api/onboarding/userbots/{userbot['id']}",
        "metadata": {
            "telegram_user_id": userbot.get("telegram_user_id"),
            "telegram_username": username,
            "telegram_api_id": api_id,
            "api_hash_configured": credentials.get("api_hash_configured"),
        },
    }


def _bot_payloads(session: Session) -> list[dict[str, Any]]:
    rows = (
        session.execute(
            select(telegram_bots_table)
            .where(telegram_bots_table.c.status == "active")
            .order_by(telegram_bots_table.c.created_at.desc())
        )
        .mappings()
        .all()
    )
    return [_bot_payload(dict(row)) for row in rows]


def _bot_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "display_name": row["display_name"],
        "telegram_bot_id": row["telegram_bot_id"],
        "telegram_username": row["telegram_username"],
        "username": row["telegram_username"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _bot_by_id(session: Session, bot_id: str) -> dict[str, Any] | None:
    row = (
        session.execute(
            select(telegram_bots_table).where(
                telegram_bots_table.c.id == bot_id,
                telegram_bots_table.c.status == "active",
            )
        )
        .mappings()
        .first()
    )
    return dict(row) if row is not None else None


async def _refresh_missing_bot_usernames(request: Request, session: Session) -> None:
    rows = (
        session.execute(
            select(telegram_bots_table).where(
                telegram_bots_table.c.status == "active",
                telegram_bots_table.c.telegram_username.is_(None),
            )
        )
        .mappings()
        .all()
    )
    if not rows:
        return
    client = _bot_setup_client(request)
    changed = False
    for row in rows:
        try:
            token = SecretRefService(session).resolve_value(str(row["token_secret_ref"]))
            bot = await client.get_me(token)
        except (FileNotFoundError, KeyError, ValueError, TelegramBotSetupError):
            continue
        if not isinstance(bot, dict):
            continue
        values: dict[str, Any] = {"updated_at": utc_now()}
        if bot.get("username"):
            values["telegram_username"] = str(bot["username"])
        if bot.get("id"):
            values["telegram_bot_id"] = str(bot["id"])
        if len(values) > 1:
            session.execute(
                update(telegram_bots_table)
                .where(telegram_bots_table.c.id == row["id"])
                .values(**values)
            )
            changed = True
    if changed:
        session.commit()


def _first_active_bot_id(session: Session) -> str | None:
    row = (
        session.execute(
            select(telegram_bots_table.c.id)
            .where(telegram_bots_table.c.status == "active")
            .order_by(telegram_bots_table.c.created_at.desc())
        )
        .mappings()
        .first()
    )
    return str(row["id"]) if row is not None else None


def _upsert_telegram_bot(
    session: Session,
    *,
    display_name: str,
    telegram_bot_id: str | None,
    telegram_username: str | None,
    token_secret_ref: str,
) -> dict[str, Any]:
    now = utc_now()
    existing = None
    if telegram_bot_id:
        existing = (
            session.execute(
                select(telegram_bots_table).where(
                    telegram_bots_table.c.telegram_bot_id == telegram_bot_id,
                    telegram_bots_table.c.status == "active",
                )
            )
            .mappings()
            .first()
        )
    values = {
        "display_name": display_name,
        "telegram_bot_id": telegram_bot_id,
        "telegram_username": telegram_username,
        "token_secret_ref": token_secret_ref,
        "status": "active",
        "updated_at": now,
    }
    if existing is None:
        bot_id = new_id()
        session.execute(insert(telegram_bots_table).values(id=bot_id, created_at=now, **values))
    else:
        bot_id = str(existing["id"])
        session.execute(
            update(telegram_bots_table).where(telegram_bots_table.c.id == bot_id).values(**values)
        )
    session.commit()
    row = _bot_by_id(session, bot_id)
    return _bot_payload(row) if row is not None else {}


def _notification_group_payloads(
    session: Session,
    *,
    bot_id: str | None = None,
) -> list[dict[str, Any]]:
    conditions = [telegram_notification_groups_table.c.status == "active"]
    if bot_id:
        conditions.append(telegram_notification_groups_table.c.telegram_bot_id == bot_id)
    rows = (
        session.execute(
            select(
                telegram_notification_groups_table,
                telegram_bots_table.c.display_name.label("bot_name"),
            )
            .select_from(
                telegram_notification_groups_table.join(
                    telegram_bots_table,
                    telegram_notification_groups_table.c.telegram_bot_id
                    == telegram_bots_table.c.id,
                )
            )
            .where(*conditions)
            .order_by(telegram_notification_groups_table.c.created_at.desc())
        )
        .mappings()
        .all()
    )
    return [
        {
            "id": row["id"],
            "bot_id": row["telegram_bot_id"],
            "bot_name": row["bot_name"],
            "chat_id": row["chat_id"],
            "title": row["title"],
            "chat_type": row["chat_type"],
            "message_thread_id": row["message_thread_id"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


def _notification_group_by_id(session: Session, group_id: str) -> dict[str, Any] | None:
    row = (
        session.execute(
            select(telegram_notification_groups_table).where(
                telegram_notification_groups_table.c.id == group_id,
                telegram_notification_groups_table.c.status == "active",
            )
        )
        .mappings()
        .first()
    )
    return dict(row) if row is not None else None


def _upsert_notification_group(
    session: Session,
    *,
    telegram_bot_id: str,
    chat_id: str,
    title: str | None,
    chat_type: str | None,
    message_thread_id: int | None,
) -> dict[str, Any]:
    conditions = [
        telegram_notification_groups_table.c.telegram_bot_id == telegram_bot_id,
        telegram_notification_groups_table.c.chat_id == chat_id,
    ]
    if message_thread_id is None:
        conditions.append(telegram_notification_groups_table.c.message_thread_id.is_(None))
    else:
        conditions.append(
            telegram_notification_groups_table.c.message_thread_id == message_thread_id
        )
    existing = (
        session.execute(select(telegram_notification_groups_table).where(*conditions))
        .mappings()
        .first()
    )
    now = utc_now()
    values = {
        "telegram_bot_id": telegram_bot_id,
        "chat_id": chat_id,
        "title": title or chat_id,
        "chat_type": chat_type,
        "message_thread_id": message_thread_id,
        "status": "active",
        "updated_at": now,
    }
    if existing is None:
        group_id = new_id()
        session.execute(
            insert(telegram_notification_groups_table).values(
                id=group_id,
                created_at=now,
                **values,
            )
        )
    else:
        group_id = str(existing["id"])
        session.execute(
            update(telegram_notification_groups_table)
            .where(telegram_notification_groups_table.c.id == group_id)
            .values(**values)
        )
    session.commit()
    rows = _notification_group_payloads(session, bot_id=telegram_bot_id)
    return next((row for row in rows if row["id"] == group_id), rows[0] if rows else {})


def _refresh_default_notification_settings(session: Session, *, actor: str) -> None:
    row = (
        session.execute(
            select(
                telegram_notification_groups_table.c.chat_id,
                telegram_notification_groups_table.c.message_thread_id,
                telegram_bots_table.c.token_secret_ref,
            )
            .select_from(
                telegram_notification_groups_table.join(
                    telegram_bots_table,
                    telegram_notification_groups_table.c.telegram_bot_id
                    == telegram_bots_table.c.id,
                )
            )
            .where(
                telegram_notification_groups_table.c.status == "active",
                telegram_bots_table.c.status == "active",
            )
            .order_by(telegram_notification_groups_table.c.created_at.desc())
        )
        .mappings()
        .first()
    )
    if row is None:
        SettingsService(session).set(
            "telegram_lead_notification_chat_id",
            "",
            value_type="string",
            updated_by=actor,
            reason="clear default Telegram notification group during onboarding",
        )
        return
    _set_default_notification_settings(
        session,
        actor=actor,
        token_secret_ref=str(row["token_secret_ref"]),
        chat_id=str(row["chat_id"]),
        message_thread_id=row["message_thread_id"],
    )


def _resolve_bot_token(
    request: Request,
    session: Session,
    *,
    bot_id: str | None = None,
) -> str | None:
    if bot_id:
        bot = _bot_by_id(session, bot_id)
        if bot is None:
            return None
        try:
            return SecretRefService(session).resolve_value(str(bot["token_secret_ref"]))
        except (FileNotFoundError, KeyError, ValueError):
            return None
    try:
        token = SecretRefService(session).resolve_setting_secret("telegram_bot_token_secret_ref")
    except (FileNotFoundError, KeyError, ValueError):
        token = None
    return token or request.app.state.telegram_bot_token


def _llm_provider_accounts(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    providers = {provider["id"]: provider for provider in snapshot.get("providers", [])}
    return [
        {
            "id": account["id"],
            "display_name": account["display_name"],
            "provider_key": providers.get(account["ai_provider_id"], {}).get("provider_key"),
            "base_url": account["base_url"],
            "enabled": account["enabled"],
            "created_at": account["created_at"],
            "updated_at": account["updated_at"],
        }
        for account in snapshot.get("accounts", [])
        if account.get("enabled")
    ]


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
