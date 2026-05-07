from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.settings import get_nlp_config_dir, get_nlp_config_repository
from app.domain.settings import NlpConfigRevision
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
    (config_dir / "lead_scoring.yaml").write_text(
        """
lead_scoring:
  thresholds:
    lead: 35
    warm: 55
    hot: 80
  weights:
    signals:
      demand: 20
    facts:
      deadline: 5
  solution_areas:
    supply:
      label: Снабжение
      signal_types:
        - demand
      fact_types: []
  customer_segments:
    active_request:
      label: Активный запрос
      signal_types:
        - demand
      fact_types:
        - deadline
  intent_signal_types:
    - demand
  noise_signal_types: []
""",
        encoding="utf-8",
    )


class InMemoryNlpConfigRepository:
    def __init__(self) -> None:
        self.active: dict[str, dict[str, Any]] | None = None
        self.revision = 0

    async def get_active_or_seed(
        self,
        default_documents: dict[str, dict[str, Any]],
    ) -> NlpConfigRevision:
        if self.active is None:
            self.active = default_documents
            self.revision = 1
        return NlpConfigRevision(
            id=uuid4(),
            revision=self.revision,
            documents=self.active,
            source="bootstrap" if self.revision == 1 else "ui",
            created_at=None,
        )

    async def replace_active(
        self,
        documents: dict[str, dict[str, Any]],
        *,
        source: str,
    ) -> NlpConfigRevision:
        self.revision += 1
        self.active = documents
        return NlpConfigRevision(
            id=uuid4(),
            revision=self.revision,
            documents=documents,
            source=source,
            created_at=None,
        )


def _app_with_settings_repo(config_dir: Path, repository: InMemoryNlpConfigRepository) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_nlp_config_dir] = lambda: config_dir
    app.dependency_overrides[get_nlp_config_repository] = lambda: repository
    return TestClient(app)


def test_get_settings_returns_editable_nlp_and_readonly_system_settings(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    _write_config(config_dir)
    repository = InMemoryNlpConfigRepository()
    client = _app_with_settings_repo(config_dir, repository)

    response = client.get("/api/v1/settings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["nlp"]["source"]["editable"] is True
    assert payload["nlp"]["source"]["type"] == "postgres"
    assert payload["nlp"]["source"]["revision"] == 1
    assert payload["nlp"]["signals"][0]["type"] == "demand"
    assert payload["nlp"]["signals"][0]["patterns"][0]["tokens"][0] == {
        "predicate": "normalized",
        "value": "нужный",
    }
    assert payload["nlp"]["facts"][0]["type"] == "deadline"
    assert payload["nlp"]["lead_scoring"]["lead_threshold"] == 35
    assert payload["nlp"]["lead_scoring"]["signal_weights"]["demand"] == 20
    assert payload["nlp"]["lead_scoring"]["solution_areas"]["supply"]["label"] == "Снабжение"
    assert any(item["key"] == "environment" and item["editable"] is False for item in payload["system"])
    assert repository.active is not None


def test_update_nlp_settings_validates_and_writes_database_revision_not_yaml(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    _write_config(config_dir)
    repository = InMemoryNlpConfigRepository()
    client = _app_with_settings_repo(config_dir, repository)
    updated = client.get("/api/v1/settings").json()["nlp"]
    updated["signals"][0]["phrases"].append(["ищем", "поставщика"])
    updated["lead_scoring"]["signal_weights"]["demand"] = 25

    response = client.put("/api/v1/settings/nlp", json=updated)

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"]["type"] == "postgres"
    assert payload["source"]["revision"] == 2
    assert ["ищем", "поставщика"] in payload["signals"][0]["phrases"]
    assert repository.active is not None
    assert ["ищем", "поставщика"] in repository.active["signals"]["signals"][0]["phrases"]
    assert repository.active["lead_scoring"]["lead_scoring"]["weights"]["signals"]["demand"] == 25
    assert "ищем" not in (config_dir / "signals.yaml").read_text(encoding="utf-8")


def test_preview_nlp_settings_uses_draft_without_saving(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    _write_config(config_dir)
    repository = InMemoryNlpConfigRepository()
    client = _app_with_settings_repo(config_dir, repository)
    draft = client.get("/api/v1/settings").json()["nlp"]
    draft["signals"][0]["phrases"].append(["ищем", "поставщика"])
    draft["pipeline"]["stages"].append({"name": "lead_scoring", "enabled": True})
    draft["lead_scoring"]["lead_threshold"] = 20

    response = client.post(
        "/api/v1/settings/nlp/preview",
        json={"text": "Ищем поставщика завтра", "nlp": draft},
    )

    assert response.status_code == 200
    payload = response.json()
    assert any(item["type"] == "demand" for item in payload["domain_signals"])
    assert payload["lead_assessment"]["is_lead"] is True
    assert "ищем" not in (config_dir / "signals.yaml").read_text(encoding="utf-8")
    assert repository.active is not None
    assert ["ищем", "поставщика"] not in repository.active["signals"]["signals"][0]["phrases"]
