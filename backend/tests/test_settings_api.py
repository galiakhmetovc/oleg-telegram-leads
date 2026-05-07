from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.api.settings import get_nlp_config_dir
from app.main import create_app


def _write_config(config_dir: Path) -> None:
    config_dir.mkdir()
    (config_dir / "pipeline.yaml").write_text(
        """
stages:
  - name: segmentation
    enabled: true
  - name: domain_signals
    enabled: true
""",
        encoding="utf-8",
    )
    (config_dir / "signals.yaml").write_text(
        """
signals:
  - type: demand
    label: Потребность
    color: "#2e7d32"
    confidence: 0.72
    phrases:
      - ["нужна"]
    patterns:
      - tokens:
          - normalized: "нужный"
""",
        encoding="utf-8",
    )
    (config_dir / "facts.yaml").write_text(
        """
facts:
  - type: deadline
    label: Срок
    confidence: 0.55
    phrases:
      - ["завтра"]
""",
        encoding="utf-8",
    )


def test_get_settings_returns_editable_nlp_and_readonly_system_settings(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    _write_config(config_dir)
    app = create_app()
    app.dependency_overrides[get_nlp_config_dir] = lambda: config_dir
    client = TestClient(app)

    response = client.get("/api/v1/settings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["nlp"]["source"]["editable"] is True
    assert payload["nlp"]["signals"][0]["type"] == "demand"
    assert payload["nlp"]["signals"][0]["patterns"][0]["tokens"][0] == {
        "predicate": "normalized",
        "value": "нужный",
    }
    assert payload["nlp"]["facts"][0]["type"] == "deadline"
    assert any(item["key"] == "environment" and item["editable"] is False for item in payload["system"])


def test_update_nlp_settings_validates_and_writes_yaml(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    _write_config(config_dir)
    app = create_app()
    app.dependency_overrides[get_nlp_config_dir] = lambda: config_dir
    client = TestClient(app)
    updated = client.get("/api/v1/settings").json()["nlp"]
    updated["signals"][0]["phrases"].append(["ищем", "поставщика"])

    response = client.put("/api/v1/settings/nlp", json=updated)

    assert response.status_code == 200
    payload = response.json()
    assert ["ищем", "поставщика"] in payload["signals"][0]["phrases"]
    assert "ищем" in (config_dir / "signals.yaml").read_text(encoding="utf-8")


def test_preview_nlp_settings_uses_draft_without_saving(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    _write_config(config_dir)
    app = create_app()
    app.dependency_overrides[get_nlp_config_dir] = lambda: config_dir
    client = TestClient(app)
    draft = client.get("/api/v1/settings").json()["nlp"]
    draft["signals"][0]["phrases"].append(["ищем", "поставщика"])

    response = client.post(
        "/api/v1/settings/nlp/preview",
        json={"text": "Ищем поставщика завтра", "nlp": draft},
    )

    assert response.status_code == 200
    payload = response.json()
    assert any(item["type"] == "demand" for item in payload["domain_signals"])
    assert "ищем" not in (config_dir / "signals.yaml").read_text(encoding="utf-8")
