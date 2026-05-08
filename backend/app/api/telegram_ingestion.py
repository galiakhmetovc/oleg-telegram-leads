from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.application.telegram_ingestion.use_cases import CompleteUserbotLogin, SendUserbotLoginCode
from app.application.telegram_ingestion.use_cases import UpdateTelegramIngestionSettings
from app.db.session import create_sessionmaker
from app.domain.telegram_ingestion import TelegramIngestionSettings, TelegramSourceChat
from app.domain.telegram_ingestion import TelegramUserbotAccount
from app.infrastructure.persistence.telegram_ingestion_repository import (
    PostgresTelegramIngestionRepository,
)
from app.infrastructure.telegram.userbot_login import TelethonUserbotLoginClient
from app.infrastructure.telegram.userbot_login import UserbotLoginPasswordRequired

router = APIRouter(prefix="/settings/telegram-ingestion", tags=["settings"])


class TelegramUserbotAccountSnapshot(BaseModel):
    id: UUID
    name: str
    phone: str
    api_id: int
    enabled: bool
    status: str
    has_api_hash: bool
    api_hash_masked: str | None
    has_session: bool
    last_error: str | None
    cooldown_until: datetime | None
    telegram_user_id: str | None
    telegram_username: str | None
    created_at: datetime | None
    updated_at: datetime | None


class TelegramSourceChatSnapshot(BaseModel):
    id: UUID
    account_id: UUID
    title: str
    input_ref: str
    telegram_chat_id: str | None
    enabled: bool
    status: str
    last_message_id: int | None
    last_error: str | None
    created_at: datetime | None
    updated_at: datetime | None


class TelegramIngestionSettingsSnapshot(BaseModel):
    accounts: list[TelegramUserbotAccountSnapshot]
    chats: list[TelegramSourceChatSnapshot]


class TelegramUserbotAccountUpdate(BaseModel):
    id: UUID
    name: str = Field(min_length=1)
    phone: str = Field(min_length=1)
    api_id: int = Field(gt=0)
    api_hash: str | None = None
    session_string: str | None = None
    enabled: bool = True
    status: Literal["draft", "code_sent", "authorized", "error"] | None = None


class TelegramSourceChatUpdate(BaseModel):
    id: UUID
    account_id: UUID
    title: str = Field(min_length=1)
    input_ref: str = Field(min_length=1)
    telegram_chat_id: str | None = None
    enabled: bool = True
    status: Literal["draft", "resolved", "error"] = "draft"


class TelegramIngestionSettingsUpdate(BaseModel):
    accounts: list[TelegramUserbotAccountUpdate] = Field(default_factory=list)
    chats: list[TelegramSourceChatUpdate] = Field(default_factory=list)


class UserbotLoginCodeResponse(BaseModel):
    status: Literal["code_sent"]
    account: TelegramUserbotAccountSnapshot


class UserbotSignInRequest(BaseModel):
    code: str = Field(min_length=1)
    password: str | None = None


class UserbotSignInResponse(BaseModel):
    status: Literal["authorized"]
    account: TelegramUserbotAccountSnapshot


def get_telegram_ingestion_repository() -> PostgresTelegramIngestionRepository:
    return PostgresTelegramIngestionRepository(create_sessionmaker())


def get_userbot_login_client() -> TelethonUserbotLoginClient:
    return TelethonUserbotLoginClient()


@router.get("", response_model=TelegramIngestionSettingsSnapshot)
async def get_telegram_ingestion_settings(
    repository: PostgresTelegramIngestionRepository = Depends(get_telegram_ingestion_repository),
) -> TelegramIngestionSettingsSnapshot:
    return settings_snapshot(await repository.get_settings())


@router.put("", response_model=TelegramIngestionSettingsSnapshot)
async def update_telegram_ingestion_settings(
    payload: TelegramIngestionSettingsUpdate,
    repository: PostgresTelegramIngestionRepository = Depends(get_telegram_ingestion_repository),
) -> TelegramIngestionSettingsSnapshot:
    try:
        settings = await UpdateTelegramIngestionSettings(repository).execute(
            settings_from_update(payload)
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return settings_snapshot(settings)


@router.post("/accounts/{account_id}/send-code", response_model=UserbotLoginCodeResponse)
async def send_userbot_login_code(
    account_id: UUID,
    repository: PostgresTelegramIngestionRepository = Depends(get_telegram_ingestion_repository),
    login_client: TelethonUserbotLoginClient = Depends(get_userbot_login_client),
) -> UserbotLoginCodeResponse:
    try:
        account = await SendUserbotLoginCode(
            repository=repository,
            login_client=login_client,
        ).execute(account_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return UserbotLoginCodeResponse(status="code_sent", account=account_snapshot(account))


@router.post("/accounts/{account_id}/sign-in", response_model=UserbotSignInResponse)
async def complete_userbot_login(
    account_id: UUID,
    payload: UserbotSignInRequest,
    repository: PostgresTelegramIngestionRepository = Depends(get_telegram_ingestion_repository),
    login_client: TelethonUserbotLoginClient = Depends(get_userbot_login_client),
) -> UserbotSignInResponse:
    try:
        account = await CompleteUserbotLogin(
            repository=repository,
            login_client=login_client,
        ).execute(account_id=account_id, code=payload.code, password=payload.password)
    except UserbotLoginPasswordRequired as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return UserbotSignInResponse(status="authorized", account=account_snapshot(account))


async def read_telegram_ingestion_settings_snapshot(
    repository: PostgresTelegramIngestionRepository,
) -> TelegramIngestionSettingsSnapshot:
    return settings_snapshot(await repository.get_settings())


def settings_from_update(payload: TelegramIngestionSettingsUpdate) -> TelegramIngestionSettings:
    return TelegramIngestionSettings(
        accounts=[
            TelegramUserbotAccount(
                id=item.id,
                name=item.name,
                phone=item.phone,
                api_id=item.api_id,
                api_hash=item.api_hash,
                session_string=item.session_string,
                phone_code_hash=None,
                enabled=item.enabled,
                status=item.status or ("authorized" if item.session_string else "draft"),
                last_error=None,
        telegram_user_id=None,
        telegram_username=None,
        created_at=None,
        updated_at=None,
        cooldown_until=None,
            )
            for item in payload.accounts
        ],
        chats=[
            TelegramSourceChat(
                id=item.id,
                account_id=item.account_id,
                title=item.title,
                input_ref=item.input_ref,
                telegram_chat_id=item.telegram_chat_id,
                enabled=item.enabled,
                status=item.status,
                last_message_id=None,
                last_error=None,
                created_at=None,
                updated_at=None,
            )
            for item in payload.chats
        ],
    )


def settings_snapshot(settings: TelegramIngestionSettings) -> TelegramIngestionSettingsSnapshot:
    return TelegramIngestionSettingsSnapshot(
        accounts=[account_snapshot(account) for account in settings.accounts],
        chats=[chat_snapshot(chat) for chat in settings.chats],
    )


def account_snapshot(account: TelegramUserbotAccount) -> TelegramUserbotAccountSnapshot:
    return TelegramUserbotAccountSnapshot(
        id=account.id,
        name=account.name,
        phone=account.phone,
        api_id=account.api_id,
        enabled=account.enabled,
        status=account.status,
        has_api_hash=account.has_api_hash,
        api_hash_masked=mask_secret(account.api_hash),
        has_session=account.has_session,
        last_error=account.last_error,
        cooldown_until=account.cooldown_until,
        telegram_user_id=account.telegram_user_id,
        telegram_username=account.telegram_username,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


def chat_snapshot(chat: TelegramSourceChat) -> TelegramSourceChatSnapshot:
    return TelegramSourceChatSnapshot(
        id=chat.id,
        account_id=chat.account_id,
        title=chat.title,
        input_ref=chat.input_ref,
        telegram_chat_id=chat.telegram_chat_id,
        enabled=chat.enabled,
        status=chat.status,
        last_message_id=chat.last_message_id,
        last_error=chat.last_error,
        created_at=chat.created_at,
        updated_at=chat.updated_at,
    )


def mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}***{value[-4:]}"
