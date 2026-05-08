from __future__ import annotations

from dataclasses import replace
from typing import TypeVar, cast
from uuid import UUID

from app.application.telegram_ingestion.ports import EnrichmentJobCreator, TelegramIngestionRepository
from app.application.telegram_ingestion.ports import TelegramIngestionSettingsRepository
from app.application.telegram_ingestion.ports import UserbotLoginClient
from app.domain.telegram_ingestion import TelegramIncomingMessage, TelegramIngestionResult
from app.domain.telegram_ingestion import TelegramIngestionSettings, TelegramSourceChat
from app.domain.telegram_ingestion import TelegramUserbotAccount

_Status = TypeVar("_Status", bound=str)


class IngestTelegramMessage:
    def __init__(
        self,
        *,
        repository: TelegramIngestionRepository,
        job_creator: EnrichmentJobCreator,
    ) -> None:
        self._repository = repository
        self._job_creator = job_creator

    async def execute(self, message: TelegramIncomingMessage) -> TelegramIngestionResult:
        text = (message.text or "").strip()
        if not text:
            return TelegramIngestionResult(
                status="skipped_empty_text",
                message=None,
                enrichment_job_id=None,
            )

        existing = await self._repository.get_source_message(
            source_chat_id=message.source_chat_id,
            telegram_message_id=message.telegram_message_id,
        )
        if existing is not None:
            return TelegramIngestionResult(
                status="duplicate",
                message=existing,
                enrichment_job_id=existing.enrichment_job_id,
            )

        job = await self._job_creator.create(text)
        saved = await self._repository.save_source_message(
            message,
            text=text,
            enrichment_job_id=job.id,
        )
        if saved.enrichment_job_id != job.id:
            return TelegramIngestionResult(
                status="duplicate",
                message=saved,
                enrichment_job_id=saved.enrichment_job_id,
            )
        await self._job_creator.publish(job.id)
        return TelegramIngestionResult(
            status="created",
            message=saved,
            enrichment_job_id=job.id,
        )


class UpdateTelegramIngestionSettings:
    def __init__(self, repository: TelegramIngestionSettingsRepository) -> None:
        self._repository = repository

    async def execute(self, settings: TelegramIngestionSettings) -> TelegramIngestionSettings:
        current = await self._repository.get_settings()
        accounts_by_id = {account.id: account for account in current.accounts}
        normalized_accounts = [
            _normalize_account(account, accounts_by_id.get(account.id))
            for account in settings.accounts
        ]
        _validate_unique([account.id for account in normalized_accounts], "Account ids must be unique")
        account_ids = {account.id for account in normalized_accounts}
        chats_by_id = {chat.id: chat for chat in current.chats}
        normalized_chats = [
            _normalize_chat(chat, account_ids, chats_by_id.get(chat.id))
            for chat in settings.chats
        ]
        _validate_unique([chat.id for chat in normalized_chats], "Chat ids must be unique")
        return await self._repository.save_settings(
            TelegramIngestionSettings(accounts=normalized_accounts, chats=normalized_chats)
        )


class SendUserbotLoginCode:
    def __init__(
        self,
        *,
        repository: TelegramIngestionSettingsRepository,
        login_client: UserbotLoginClient,
    ) -> None:
        self._repository = repository
        self._login_client = login_client

    async def execute(self, account_id: UUID) -> TelegramUserbotAccount:
        settings = await self._repository.get_settings()
        account = _find_account(settings, account_id)
        _ensure_login_ready(account)
        sent = await self._login_client.send_code(
            api_id=account.api_id,
            api_hash=account.api_hash or "",
            phone=account.phone,
            session_string=account.session_string,
        )
        updated = replace(
            account,
            phone_code_hash=sent.phone_code_hash,
            session_string=sent.session_string,
            status="code_sent",
            last_error=None,
        )
        saved = await self._repository.save_settings(_replace_account(settings, updated))
        return _find_account(saved, account_id)


class CompleteUserbotLogin:
    def __init__(
        self,
        *,
        repository: TelegramIngestionSettingsRepository,
        login_client: UserbotLoginClient,
    ) -> None:
        self._repository = repository
        self._login_client = login_client

    async def execute(
        self,
        *,
        account_id: UUID,
        code: str,
        password: str | None,
    ) -> TelegramUserbotAccount:
        settings = await self._repository.get_settings()
        account = _find_account(settings, account_id)
        _ensure_login_ready(account)
        if not account.phone_code_hash:
            raise ValueError("Telegram login code was not requested")
        stripped_code = code.strip()
        if not stripped_code:
            raise ValueError("Telegram login code is required")
        authorization = await self._login_client.sign_in(
            api_id=account.api_id,
            api_hash=account.api_hash or "",
            phone=account.phone,
            code=stripped_code,
            phone_code_hash=account.phone_code_hash,
            password=_optional_str(password),
            session_string=account.session_string,
        )
        updated = replace(
            account,
            session_string=authorization.session_string,
            phone_code_hash=None,
            status="authorized",
            last_error=None,
            telegram_user_id=authorization.telegram_user_id,
            telegram_username=authorization.telegram_username,
        )
        saved = await self._repository.save_settings(_replace_account(settings, updated))
        return _find_account(saved, account_id)


def _normalize_account(
    account: TelegramUserbotAccount,
    existing: TelegramUserbotAccount | None,
) -> TelegramUserbotAccount:
    name = _required_str(account.name, "Account name is required")
    phone = _required_str(account.phone, "Telegram phone is required")
    api_hash = _optional_str(account.api_hash) or (existing.api_hash if existing else None)
    session_string = _optional_str(account.session_string) or (
        existing.session_string if existing else None
    )
    if account.enabled and not api_hash:
        raise ValueError(f"Telegram api_hash is required for enabled account {account.id}")
    return TelegramUserbotAccount(
        id=account.id,
        name=name,
        phone=phone,
        api_id=account.api_id,
        api_hash=api_hash,
        session_string=session_string,
        phone_code_hash=account.phone_code_hash or (existing.phone_code_hash if existing else None),
        enabled=account.enabled,
        status=_preserved_status(account.status, existing.status if existing else None),
        last_error=account.last_error or (existing.last_error if existing else None),
        telegram_user_id=account.telegram_user_id or (existing.telegram_user_id if existing else None),
        telegram_username=account.telegram_username or (existing.telegram_username if existing else None),
        created_at=account.created_at or (existing.created_at if existing else None),
        updated_at=account.updated_at or (existing.updated_at if existing else None),
        cooldown_until=account.cooldown_until or (existing.cooldown_until if existing else None),
    )


def _normalize_chat(
    chat: TelegramSourceChat,
    account_ids: set[UUID],
    existing: TelegramSourceChat | None,
) -> TelegramSourceChat:
    if chat.account_id not in account_ids:
        raise ValueError(f"Telegram source chat {chat.id} references unknown account {chat.account_id}")
    input_ref = _required_str(chat.input_ref, "Telegram source input_ref is required")
    same_source = bool(existing and existing.account_id == chat.account_id and existing.input_ref == input_ref)
    return TelegramSourceChat(
        id=chat.id,
        account_id=chat.account_id,
        title=_required_str(chat.title, "Source chat title is required"),
        input_ref=input_ref,
        telegram_chat_id=_optional_str(chat.telegram_chat_id) or (
            existing.telegram_chat_id if same_source and existing else None
        ),
        enabled=chat.enabled,
        status=_preserved_status(chat.status, existing.status if same_source and existing else None),
        last_message_id=chat.last_message_id if chat.last_message_id is not None else (
            existing.last_message_id if same_source and existing else None
        ),
        last_error=chat.last_error or (existing.last_error if same_source and existing else None),
        created_at=chat.created_at or (existing.created_at if existing else None),
        updated_at=chat.updated_at or (existing.updated_at if existing else None),
    )


def _preserved_status(incoming: _Status, existing: _Status | None) -> _Status:
    if incoming != "draft" or existing in {None, "draft"}:
        return incoming
    return cast(_Status, existing)


def _find_account(
    settings: TelegramIngestionSettings,
    account_id: UUID,
) -> TelegramUserbotAccount:
    account = next((item for item in settings.accounts if item.id == account_id), None)
    if account is None:
        raise ValueError("Telegram userbot account is not configured")
    return account


def _ensure_login_ready(account: TelegramUserbotAccount) -> None:
    if not account.enabled:
        raise ValueError("Telegram userbot account is disabled")
    if not account.api_hash:
        raise ValueError("Telegram api_hash is required")
    if not account.phone.strip():
        raise ValueError("Telegram phone is required")


def _replace_account(
    settings: TelegramIngestionSettings,
    account: TelegramUserbotAccount,
) -> TelegramIngestionSettings:
    return TelegramIngestionSettings(
        accounts=[account if item.id == account.id else item for item in settings.accounts],
        chats=settings.chats,
    )


def _optional_str(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _required_str(value: str, message: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(message)
    return stripped


def _validate_unique(values: list[UUID], message: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(message)
