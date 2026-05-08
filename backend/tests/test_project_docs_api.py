from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app


def test_lists_project_documents() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/project-docs")

    assert response.status_code == 200
    paths = {item["path"] for item in response.json()["items"]}
    assert "README.md" in paths
    assert "AGENTS.md" in paths
    assert "docs/architecture.md" in paths
    assert "state/current.md" in paths
    assert "backend/.pytest_cache/README.md" not in paths


def test_reads_project_document_content() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/project-docs/README.md")

    assert response.status_code == 200
    payload = response.json()
    assert payload["path"] == "README.md"
    assert "PUR Leads v2" in payload["content"]
    assert payload["size_bytes"] > 0


def test_rejects_non_document_paths() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/project-docs/backend/.pytest_cache/README.md")

    assert response.status_code == 404


def test_uses_configured_project_docs_root(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "README.md").write_text("# Custom Docs\n\nMounted docs root.", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "architecture.md").write_text("# Mounted Architecture\n", encoding="utf-8")
    monkeypatch.setenv("PUR_PROJECT_DOCS_ROOT", str(tmp_path))
    get_settings.cache_clear()

    try:
        client = TestClient(create_app())
        response = client.get("/api/v1/project-docs")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    payload = response.json()
    assert {item["path"] for item in payload["items"]} == {"README.md", "docs/architecture.md"}
