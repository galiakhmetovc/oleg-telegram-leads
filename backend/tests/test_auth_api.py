from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app


def test_protects_api_routes_when_auth_enabled(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("PUR_AUTH_ENABLED", "true")
    get_settings.cache_clear()
    client = TestClient(create_app())

    response = client.get("/api/v1/settings")

    assert response.status_code == 401
    assert response.json()["detail"] == "authentication required"
    get_settings.cache_clear()


def test_login_sets_session_cookie_and_reports_authenticated_user(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("PUR_AUTH_ENABLED", "true")
    monkeypatch.setenv("PUR_AUTH_USERNAME", "admin")
    monkeypatch.setenv("PUR_AUTH_PASSWORD", "pur-dev-password")
    monkeypatch.setenv("PUR_AUTH_SESSION_SECRET", "test-secret")
    get_settings.cache_clear()
    client = TestClient(create_app())

    failed = client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
    succeeded = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "pur-dev-password"},
    )
    me = client.get("/api/v1/auth/me")

    assert failed.status_code == 401
    assert succeeded.status_code == 200
    assert "pur_session" in succeeded.cookies
    assert me.status_code == 200
    assert me.json() == {"authenticated": True, "username": "admin"}
    get_settings.cache_clear()
