from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.notifications import get_notification_settings_repository, get_telegram_message_sender
from app.api.telegram_ingestion import get_telegram_ingestion_repository
from app.domain.notifications import NotificationSettings, TelegramSendResult
from app.domain.telegram_ingestion import TelegramIngestionSettings
from app.main import create_app


class InMemoryNotificationSettingsRepository:
    def __init__(self) -> None:
        self.settings = NotificationSettings(
            bots=[],
            chats=[],
            routes=[],
            updated_at=None,
        )

    async def get_settings(self) -> NotificationSettings:
        return self.settings

    async def save_settings(self, settings: NotificationSettings) -> NotificationSettings:
        self.settings = NotificationSettings(
            bots=settings.bots,
            chats=settings.chats,
            routes=settings.routes,
            updated_at=datetime(2026, 5, 8, tzinfo=UTC),
            summary=settings.summary,
        )
        return self.settings


class FakeTelegramMessageSender:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    async def get_bot_username(self, *, bot_token: str) -> str:
        return "pur_test_bot"

    async def send_text(self, *, bot_token: str, chat_id: str, text: str) -> TelegramSendResult:
        self.calls.append((bot_token, chat_id, text))
        return TelegramSendResult(message_id=777, chat_id=chat_id)


class InMemoryTelegramIngestionSettingsRepository:
    async def get_settings(self) -> TelegramIngestionSettings:
        return TelegramIngestionSettings(accounts=[], chats=[])

    async def save_settings(
        self,
        settings: TelegramIngestionSettings,
    ) -> TelegramIngestionSettings:
        return settings


def _client_with_notifications(
    repository: InMemoryNotificationSettingsRepository,
    sender: FakeTelegramMessageSender | None = None,
) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_notification_settings_repository] = lambda: repository
    app.dependency_overrides[get_telegram_message_sender] = lambda: sender or FakeTelegramMessageSender()
    app.dependency_overrides[get_telegram_ingestion_repository] = (
        lambda: InMemoryTelegramIngestionSettingsRepository()
    )
    return TestClient(app)


def test_get_settings_contains_masked_notification_bots_chats_and_routes() -> None:
    repository = InMemoryNotificationSettingsRepository()
    client = _client_with_notifications(repository)
    response = client.put(
        "/api/v1/settings/notifications",
        json={
            "bots": [
                {
                    "id": "main_bot",
                    "name": "Основной бот",
                    "enabled": True,
                    "token": "123456:ABCDEFSECRET",
                }
            ],
            "chats": [
                {
                    "id": "sales_chat",
                    "name": "Продажи",
                    "enabled": True,
                    "telegram_chat_id": "-100123",
                }
            ],
            "routes": [
                {
                    "id": "hot_leads",
                    "name": "Горячие лиды",
                    "enabled": True,
                    "priority": 100,
                    "bot_id": "main_bot",
                    "chat_id": "sales_chat",
                    "match_mode": "all",
                    "delivery_mode": "interactive",
                    "conditions": {"is_lead": True, "score_min": 80, "review_lanes": ["direct_pur_lead"]},
                    "message_template": "Лид {score}: {text}",
                }
            ],
        },
    )
    assert response.status_code == 200

    response = client.get("/api/v1/settings")

    assert response.status_code == 200
    notifications = response.json()["notifications"]
    assert notifications["bots"][0]["id"] == "main_bot"
    assert notifications["bots"][0]["has_token"] is True
    assert notifications["bots"][0]["token_masked"] == "123456:***CRET"
    assert notifications["chats"][0]["telegram_chat_id"] == "-100123"
    assert notifications["routes"][0]["delivery_mode"] == "interactive"
    assert notifications["routes"][0]["conditions"]["score_min"] == 80
    assert response.json()["telegram_ingestion"] == {"accounts": [], "chats": []}
    assert "ABCDEFSECRET" not in response.text


def test_notification_route_delivery_mode_defaults_to_batched() -> None:
    repository = InMemoryNotificationSettingsRepository()
    client = _client_with_notifications(repository)
    response = client.put(
        "/api/v1/settings/notifications",
        json={
            "bots": [
                {
                    "id": "main_bot",
                    "name": "Основной бот",
                    "enabled": True,
                    "token": "123456:ABCDEFSECRET",
                }
            ],
            "chats": [
                {
                    "id": "sales_chat",
                    "name": "Продажи",
                    "enabled": True,
                    "telegram_chat_id": "-100123",
                }
            ],
            "routes": [
                {
                    "id": "hot_leads",
                    "name": "Горячие лиды",
                    "enabled": True,
                    "priority": 100,
                    "bot_id": "main_bot",
                    "chat_id": "sales_chat",
                    "match_mode": "all",
                    "conditions": {"is_lead": True},
                    "message_template": "Лид {score}: {text}",
                }
            ],
        },
    )
    assert response.status_code == 200

    response = client.get("/api/v1/settings")

    assert response.status_code == 200
    assert response.json()["notifications"]["routes"][0]["delivery_mode"] == "batched"


def test_updates_notification_summary_settings() -> None:
    repository = InMemoryNotificationSettingsRepository()
    client = _client_with_notifications(repository)

    response = client.put(
        "/api/v1/settings/notifications",
        json={
            "bots": [
                {
                    "id": "main_bot",
                    "name": "Основной бот",
                    "enabled": True,
                    "token": "123456:ABCDEFSECRET",
                }
            ],
            "chats": [
                {
                    "id": "sales_chat",
                    "name": "Продажи",
                    "enabled": True,
                    "telegram_chat_id": "-100123",
                },
                {
                    "id": "summary_chat",
                    "name": "Сводки",
                    "enabled": True,
                    "telegram_chat_id": "-100456",
                },
            ],
            "routes": [],
            "summary": {
                "enabled": True,
                "bot_id": "main_bot",
                "chat_id": "summary_chat",
                "timezone": "Europe/Moscow",
                "day_start_hour": 9,
                "night_start_hour": 21,
            },
        },
    )
    assert response.status_code == 200

    response = client.get("/api/v1/settings")

    assert response.status_code == 200
    assert response.json()["notifications"]["summary"] == {
        "enabled": True,
        "bot_id": "main_bot",
        "chat_id": "summary_chat",
        "timezone": "Europe/Moscow",
        "day_start_hour": 9,
        "night_start_hour": 21,
    }


def test_notification_summary_requires_known_bot_and_chat() -> None:
    repository = InMemoryNotificationSettingsRepository()
    client = _client_with_notifications(repository)

    response = client.put(
        "/api/v1/settings/notifications",
        json={
            "bots": [
                {
                    "id": "main_bot",
                    "name": "Основной бот",
                    "enabled": True,
                    "token": "123456:ABCDEFSECRET",
                }
            ],
            "chats": [],
            "routes": [],
            "summary": {
                "enabled": True,
                "bot_id": "main_bot",
                "chat_id": "summary_chat",
            },
        },
    )

    assert response.status_code == 422
    assert "unknown chat summary_chat" in response.json()["detail"]


def test_notification_summary_requires_valid_timezone() -> None:
    repository = InMemoryNotificationSettingsRepository()
    client = _client_with_notifications(repository)

    response = client.put(
        "/api/v1/settings/notifications",
        json={
            "bots": [
                {
                    "id": "main_bot",
                    "name": "Основной бот",
                    "enabled": True,
                    "token": "123456:ABCDEFSECRET",
                }
            ],
            "chats": [
                {
                    "id": "summary_chat",
                    "name": "Сводки",
                    "enabled": True,
                    "telegram_chat_id": "-100456",
                }
            ],
            "routes": [],
            "summary": {
                "enabled": True,
                "bot_id": "main_bot",
                "chat_id": "summary_chat",
                "timezone": "Bad/Zone",
            },
        },
    )

    assert response.status_code == 422
    assert "Summary timezone is invalid" in response.json()["detail"]


def test_notification_summary_is_preserved_when_payload_omits_it() -> None:
    repository = InMemoryNotificationSettingsRepository()
    client = _client_with_notifications(repository)
    base_payload = {
        "bots": [
            {
                "id": "main_bot",
                "name": "Основной бот",
                "enabled": True,
                "token": "123456:ABCDEFSECRET",
            }
        ],
        "chats": [
            {
                "id": "summary_chat",
                "name": "Сводки",
                "enabled": True,
                "telegram_chat_id": "-100456",
            }
        ],
        "routes": [],
    }
    response = client.put(
        "/api/v1/settings/notifications",
        json={
            **base_payload,
            "summary": {
                "enabled": True,
                "bot_id": "main_bot",
                "chat_id": "summary_chat",
            },
        },
    )
    assert response.status_code == 200

    response = client.put(
        "/api/v1/settings/notifications",
        json=base_payload,
    )

    assert response.status_code == 200
    assert response.json()["summary"] == {
        "enabled": True,
        "bot_id": "main_bot",
        "chat_id": "summary_chat",
        "timezone": "Europe/Moscow",
        "day_start_hour": 9,
        "night_start_hour": 21,
    }


def test_updates_notification_settings_and_preserves_existing_bot_tokens() -> None:
    repository = InMemoryNotificationSettingsRepository()
    client = _client_with_notifications(repository)

    response = client.put(
        "/api/v1/settings/notifications",
        json={
            "bots": [
                {
                    "id": "main_bot",
                    "name": "Основной бот",
                    "enabled": True,
                    "token": "123456:ABCDEFSECRET",
                }
            ],
            "chats": [],
            "routes": [],
        },
    )
    assert response.status_code == 200

    response = client.put(
        "/api/v1/settings/notifications",
        json={
            "bots": [
                {
                    "id": "main_bot",
                    "name": "Переименованный бот",
                    "enabled": True,
                    "token": "",
                }
            ],
            "chats": [],
            "routes": [],
        },
    )

    assert response.status_code == 200
    assert repository.settings.bots[0].name == "Переименованный бот"
    assert repository.settings.bots[0].token == "123456:ABCDEFSECRET"


def test_sends_chat_test_message_with_selected_bot_and_chat() -> None:
    repository = InMemoryNotificationSettingsRepository()
    sender = FakeTelegramMessageSender()
    client = _client_with_notifications(repository, sender)
    response = client.put(
        "/api/v1/settings/notifications",
        json={
            "bots": [
                {
                    "id": "main_bot",
                    "name": "Основной бот",
                    "enabled": True,
                    "token": "123456:ABCDEFSECRET",
                }
            ],
            "chats": [
                {
                    "id": "sales_chat",
                    "name": "Продажи",
                    "enabled": True,
                    "telegram_chat_id": "@pur_test_group",
                }
            ],
            "routes": [],
        },
    )
    assert response.status_code == 200

    response = client.post(
        "/api/v1/settings/notifications/telegram/chats/sales_chat/test",
        json={"bot_id": "main_bot", "message": "Проверка уведомлений"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "message": "Тестовое сообщение отправлено",
        "telegram_message_id": 777,
        "chat_id": "@pur_test_group",
    }
    assert sender.calls == [
        ("123456:ABCDEFSECRET", "@pur_test_group", "Проверка уведомлений")
    ]


def test_chat_test_message_requires_existing_enabled_bot_and_chat() -> None:
    repository = InMemoryNotificationSettingsRepository()
    client = _client_with_notifications(repository)

    response = client.post(
        "/api/v1/settings/notifications/telegram/chats/missing_chat/test",
        json={"bot_id": "missing_bot", "message": "Проверка"},
    )

    assert response.status_code == 422
    assert "Telegram bot is not configured" in response.text
