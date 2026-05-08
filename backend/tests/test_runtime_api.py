from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.runtime import get_runtime_repository
from app.main import create_app


class FakeRuntimeRepository:
    def __init__(self) -> None:
        self.log_call: dict[str, object] | None = None
        self.retention_call: dict[str, int] | None = None

    async def list_logs(
        self,
        *,
        limit: int,
        offset: int,
        service: str | None,
        level: str | None,
        q: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
    ) -> dict[str, object]:
        self.log_call = {
            "limit": limit,
            "offset": offset,
            "service": service,
            "level": level,
            "q": q,
            "created_from": created_from,
            "created_to": created_to,
        }
        return {
            "total": 321,
            "items": [
                {
                    "created_at": datetime(2026, 5, 8, 12, 0, tzinfo=UTC),
                    "service": service or "userbot",
                    "level": level or "info",
                    "message": "Получено сообщение Telegram",
                    "payload": {"limit": limit, "offset": offset, "q": q},
                }
            ],
        }

    async def enforce_log_retention(
        self,
        *,
        enrichment_event_rows: int,
        notification_outbox_rows: int,
    ) -> dict[str, int]:
        self.retention_call = {
            "enrichment_event_rows": enrichment_event_rows,
            "notification_outbox_rows": notification_outbox_rows,
        }
        return {"enrichment_events_deleted": 0, "notification_outbox_deleted": 0}

    async def system_status(self) -> list[dict[str, object]]:
        return [
            {"service": "backend", "status": "ok", "details": {}},
            {"service": "userbot", "status": "ok", "details": {"resolved": 4}},
        ]


def test_lists_runtime_logs() -> None:
    repository = FakeRuntimeRepository()
    app = create_app()
    app.dependency_overrides[get_runtime_repository] = lambda: repository
    client = TestClient(app)

    response = client.get(
        "/api/v1/runtime/logs",
        params={
            "limit": 20,
            "offset": 40,
            "service": "userbot",
            "level": "error",
            "q": "FloodWait",
            "created_from": "2026-05-08T10:00:00Z",
            "created_to": "2026-05-08T13:00:00Z",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 321
    assert payload["limit"] == 20
    assert payload["offset"] == 40
    assert payload["items"][0]["service"] == "userbot"
    assert payload["items"][0]["level"] == "error"
    assert payload["items"][0]["payload"] == {"limit": 20, "offset": 40, "q": "FloodWait"}
    assert repository.log_call == {
        "limit": 20,
        "offset": 40,
        "service": "userbot",
        "level": "error",
        "q": "FloodWait",
        "created_from": datetime(2026, 5, 8, 10, 0, tzinfo=UTC),
        "created_to": datetime(2026, 5, 8, 13, 0, tzinfo=UTC),
    }
    assert repository.retention_call == {
        "enrichment_event_rows": 20000,
        "notification_outbox_rows": 10000,
    }


def test_caps_runtime_log_limit() -> None:
    repository = FakeRuntimeRepository()
    app = create_app()
    app.dependency_overrides[get_runtime_repository] = lambda: repository
    client = TestClient(app)

    response = client.get("/api/v1/runtime/logs", params={"limit": 999})

    assert response.status_code == 200
    assert response.json()["limit"] == 200
    assert repository.log_call is not None
    assert repository.log_call["limit"] == 200


def test_returns_system_status() -> None:
    app = create_app()
    app.dependency_overrides[get_runtime_repository] = lambda: FakeRuntimeRepository()
    client = TestClient(app)

    response = client.get("/api/v1/runtime/status")

    assert response.status_code == 200
    payload = response.json()
    assert [item["service"] for item in payload["services"]] == ["backend", "userbot"]
