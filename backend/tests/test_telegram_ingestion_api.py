from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.telegram_ingestion import get_telegram_ingestion_repository
from app.api.telegram_ingestion import get_userbot_login_client
from app.domain.telegram_ingestion import TelegramIngestionSettings, TelegramSourceChat
from app.domain.telegram_ingestion import TelegramUserbotAccount, UserbotAuthorization, UserbotCodeSent
from app.main import create_app


class InMemoryTelegramSettingsRepository:
    def __init__(self) -> None:
        self.settings = TelegramIngestionSettings(accounts=[], chats=[])

    async def get_settings(self) -> TelegramIngestionSettings:
        return self.settings

    async def save_settings(
        self,
        settings: TelegramIngestionSettings,
    ) -> TelegramIngestionSettings:
        now = datetime(2026, 5, 8, tzinfo=UTC)
        self.settings = TelegramIngestionSettings(
            accounts=[
                TelegramUserbotAccount(
                    id=account.id,
                    name=account.name,
                    phone=account.phone,
                    api_id=account.api_id,
                    api_hash=account.api_hash,
                    session_string=account.session_string,
                    phone_code_hash=account.phone_code_hash,
                    enabled=account.enabled,
                    status=account.status,
                    last_error=account.last_error,
                    telegram_user_id=account.telegram_user_id,
                    telegram_username=account.telegram_username,
                    created_at=account.created_at or now,
                    updated_at=now,
                )
                for account in settings.accounts
            ],
            chats=[
                TelegramSourceChat(
                    id=chat.id,
                    account_id=chat.account_id,
                    title=chat.title,
                    input_ref=chat.input_ref,
                    telegram_chat_id=chat.telegram_chat_id,
                    enabled=chat.enabled,
                    status=chat.status,
                    last_message_id=chat.last_message_id,
                    last_error=chat.last_error,
                    created_at=chat.created_at or now,
                    updated_at=now,
                )
                for chat in settings.chats
            ],
        )
        return self.settings


class FakeUserbotLoginClient:
    def __init__(self) -> None:
        self.sent_codes: list[dict[str, object]] = []
        self.sign_ins: list[dict[str, object]] = []

    async def send_code(
        self,
        *,
        api_id: int,
        api_hash: str,
        phone: str,
        session_string: str | None,
    ) -> UserbotCodeSent:
        self.sent_codes.append(
            {
                "api_id": api_id,
                "api_hash": api_hash,
                "phone": phone,
                "session_string": session_string,
            }
        )
        return UserbotCodeSent(
            phone_code_hash="phone-code-hash",
            session_string="pre-auth-session",
        )

    async def sign_in(
        self,
        *,
        api_id: int,
        api_hash: str,
        phone: str,
        code: str,
        phone_code_hash: str,
        password: str | None,
        session_string: str | None,
    ) -> UserbotAuthorization:
        self.sign_ins.append(
            {
                "api_id": api_id,
                "api_hash": api_hash,
                "phone": phone,
                "code": code,
                "phone_code_hash": phone_code_hash,
                "password": password,
                "session_string": session_string,
            }
        )
        return UserbotAuthorization(
            telegram_user_id="42",
            telegram_username="oleg",
            session_string="authorized-session",
        )


def _client(
    repository: InMemoryTelegramSettingsRepository,
    login_client: FakeUserbotLoginClient | None = None,
) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_telegram_ingestion_repository] = lambda: repository
    app.dependency_overrides[get_userbot_login_client] = lambda: login_client or FakeUserbotLoginClient()
    return TestClient(app)


def test_updates_telegram_ingestion_settings_and_masks_secrets() -> None:
    repository = InMemoryTelegramSettingsRepository()
    client = _client(repository)
    account_id = str(uuid4())
    chat_id = str(uuid4())

    response = client.put(
        "/api/v1/settings/telegram-ingestion",
        json={
            "accounts": [
                {
                    "id": account_id,
                    "name": "Основной userbot",
                    "phone": "+79990000000",
                    "api_id": 12345,
                    "api_hash": "api-hash-secret",
                    "enabled": True,
                }
            ],
            "chats": [
                {
                    "id": chat_id,
                    "account_id": account_id,
                    "title": "Дизайнеры",
                    "input_ref": "@designers_chat",
                    "telegram_chat_id": "-100123",
                    "enabled": True,
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["accounts"][0]["id"] == account_id
    assert payload["accounts"][0]["has_api_hash"] is True
    assert payload["accounts"][0]["api_hash_masked"] == "api-***cret"
    assert payload["accounts"][0]["has_session"] is False
    assert "api-hash-secret" not in response.text
    assert payload["chats"][0]["input_ref"] == "@designers_chat"
    assert repository.settings.accounts[0].api_hash == "api-hash-secret"


def test_update_telegram_ingestion_settings_preserves_existing_secrets() -> None:
    repository = InMemoryTelegramSettingsRepository()
    client = _client(repository)
    account_id = str(uuid4())
    first = client.put(
        "/api/v1/settings/telegram-ingestion",
        json={
            "accounts": [
                {
                    "id": account_id,
                    "name": "Основной userbot",
                    "phone": "+79990000000",
                    "api_id": 12345,
                    "api_hash": "api-hash-secret",
                    "session_string": "authorized-session",
                    "enabled": True,
                }
            ],
            "chats": [],
        },
    )
    assert first.status_code == 200

    response = client.put(
        "/api/v1/settings/telegram-ingestion",
        json={
            "accounts": [
                {
                    "id": account_id,
                    "name": "Переименованный userbot",
                    "phone": "+79990000000",
                    "api_id": 12345,
                    "api_hash": "",
                    "session_string": "",
                    "enabled": True,
                }
            ],
            "chats": [],
        },
    )

    assert response.status_code == 200
    assert repository.settings.accounts[0].name == "Переименованный userbot"
    assert repository.settings.accounts[0].api_hash == "api-hash-secret"
    assert repository.settings.accounts[0].session_string == "authorized-session"


def test_userbot_login_send_code_and_complete_updates_account_state() -> None:
    repository = InMemoryTelegramSettingsRepository()
    login_client = FakeUserbotLoginClient()
    client = _client(repository, login_client)
    account_id = str(uuid4())
    setup = client.put(
        "/api/v1/settings/telegram-ingestion",
        json={
            "accounts": [
                {
                    "id": account_id,
                    "name": "Основной userbot",
                    "phone": "+79990000000",
                    "api_id": 12345,
                    "api_hash": "api-hash-secret",
                    "enabled": True,
                }
            ],
            "chats": [],
        },
    )
    assert setup.status_code == 200

    start = client.post(f"/api/v1/settings/telegram-ingestion/accounts/{account_id}/send-code")
    complete = client.post(
        f"/api/v1/settings/telegram-ingestion/accounts/{account_id}/sign-in",
        json={"code": "12345", "password": "2fa-password"},
    )

    assert start.status_code == 200
    assert start.json()["status"] == "code_sent"
    assert complete.status_code == 200
    account = complete.json()["account"]
    assert account["status"] == "authorized"
    assert account["telegram_user_id"] == "42"
    assert account["telegram_username"] == "oleg"
    assert account["has_session"] is True
    assert "authorized-session" not in complete.text
    assert login_client.sent_codes == [
        {
            "api_id": 12345,
            "api_hash": "api-hash-secret",
            "phone": "+79990000000",
            "session_string": None,
        }
    ]
    assert login_client.sign_ins == [
        {
            "api_id": 12345,
            "api_hash": "api-hash-secret",
            "phone": "+79990000000",
            "code": "12345",
            "phone_code_hash": "phone-code-hash",
            "password": "2fa-password",
            "session_string": "pre-auth-session",
        }
    ]
