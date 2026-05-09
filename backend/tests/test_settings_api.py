from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.notifications import get_notification_settings_repository
from app.api.settings import get_nlp_config_dir, get_nlp_config_repository
from app.api.telegram_ingestion import get_telegram_ingestion_repository
from app.domain.notifications import NotificationSettings
from app.domain.settings import NlpConfigRevision
from app.domain.telegram_ingestion import TelegramIngestionSettings
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
    group: Спрос и намерение
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
    group: Общие факты
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
  review_lanes:
    - key: direct_pur_lead
      label: Прямой лид ПУР
      description: Высокий приоритет ручной проверки
      priority: 200
      match_groups:
        - solution_area_types:
            - supply
        - reason_keys:
            - demand
      excluded_noise_signal_types: []
""",
        encoding="utf-8",
    )
    (config_dir / "vendors.yaml").write_text(
        """
vendors:
  - key: aqara
    canonical: Aqara
    type: vendor
    aliases:
      - Aqara
      - Акара
    fact_types:
      - vendor
""",
        encoding="utf-8",
    )
    (config_dir / "protocols.yaml").write_text(
        """
protocols:
  - key: zigbee
    canonical: Zigbee
    type: protocol
    aliases:
      - Zigbee
      - Зигби
    fact_types:
      - protocol
""",
        encoding="utf-8",
    )
    (config_dir / "devices.yaml").write_text(
        """
devices:
  - key: relay
    canonical: Реле
    type: device
    aliases:
      - реле
    fact_types:
      - automation_component
""",
        encoding="utf-8",
    )
    (config_dir / "software.yaml").write_text(
        """
software:
  - key: alice
    canonical: Алиса
    type: software
    aliases:
      - Алиса
    fact_types:
      - software
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


class InMemoryNotificationSettingsRepository:
    async def get_settings(self) -> NotificationSettings:
        return NotificationSettings(bots=[], chats=[], routes=[], updated_at=None)

    async def save_settings(
        self,
        settings: NotificationSettings,
    ) -> NotificationSettings:
        return settings


class InMemoryTelegramIngestionSettingsRepository:
    async def get_settings(self) -> TelegramIngestionSettings:
        return TelegramIngestionSettings(accounts=[], chats=[])

    async def save_settings(
        self,
        settings: TelegramIngestionSettings,
    ) -> TelegramIngestionSettings:
        return settings


def _app_with_settings_repo(
    config_dir: Path,
    repository: InMemoryNlpConfigRepository,
    *,
    raise_server_exceptions: bool = True,
) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_nlp_config_dir] = lambda: config_dir
    app.dependency_overrides[get_nlp_config_repository] = lambda: repository
    app.dependency_overrides[get_notification_settings_repository] = (
        lambda: InMemoryNotificationSettingsRepository()
    )
    app.dependency_overrides[get_telegram_ingestion_repository] = (
        lambda: InMemoryTelegramIngestionSettingsRepository()
    )
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


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
    assert payload["nlp"]["signals"][0]["group"] == "Спрос и намерение"
    assert payload["nlp"]["signals"][0]["patterns"][0]["tokens"][0] == {
        "predicate": "normalized",
        "value": "нужный",
    }
    assert payload["nlp"]["facts"][0]["type"] == "deadline"
    assert payload["nlp"]["facts"][0]["group"] == "Общие факты"
    assert payload["nlp"]["vendors"][0]["canonical"] == "Aqara"
    assert payload["nlp"]["vendors"][0]["aliases"] == ["Aqara", "Акара"]
    assert payload["nlp"]["protocols"][0]["fact_types"] == ["protocol"]
    assert payload["nlp"]["devices"][0]["type"] == "device"
    assert payload["nlp"]["software"][0]["canonical"] == "Алиса"
    assert payload["nlp"]["lead_scoring"]["lead_threshold"] == 35
    assert payload["nlp"]["lead_scoring"]["signal_weights"]["demand"] == 20
    assert payload["nlp"]["lead_scoring"]["solution_areas"]["supply"]["label"] == "Снабжение"
    assert payload["nlp"]["lead_scoring"]["review_lanes"][0]["key"] == "direct_pur_lead"
    assert payload["nlp"]["lead_scoring"]["review_lanes"][0]["match_groups"][0]["solution_area_types"] == ["supply"]
    assert payload["notifications"]["bots"] == []
    assert payload["notifications"]["chats"] == []
    assert payload["notifications"]["routes"] == []
    assert payload["telegram_ingestion"]["accounts"] == []
    assert payload["telegram_ingestion"]["chats"] == []
    assert any(item["key"] == "environment" and item["editable"] is False for item in payload["system"])
    assert repository.active is not None


def test_get_settings_rejects_unsupported_rule_predicates(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    _write_config(config_dir)
    repository = InMemoryNlpConfigRepository()
    repository.active = {
        "pipeline": {"stages": []},
        "signals": {
            "signals": [
                {
                    "type": "technical_terms",
                    "label": "Технические термины",
                    "patterns": [
                        {"tokens": [{"caseless": "СКУД"}]},
                        {
                            "tokens": [
                                {"caseless": "zigbee"},
                                {"normalized": "шлюз"},
                            ]
                        },
                    ],
                }
            ]
        },
        "facts": {"facts": []},
        "vendors": {"vendors": []},
        "protocols": {"protocols": []},
        "devices": {"devices": []},
        "software": {"software": []},
        "lead_scoring": {
            "lead_scoring": {
                "thresholds": {"lead": 1, "warm": 1, "hot": 1},
                "weights": {"signals": {}, "facts": {}},
                "solution_areas": {},
                "customer_segments": {},
                "intent_signal_types": [],
                "noise_signal_types": [],
                "review_lanes": [],
            }
        },
    }
    repository.revision = 4
    client = _app_with_settings_repo(
        config_dir,
        repository,
        raise_server_exceptions=False,
    )

    response = client.get("/api/v1/settings")

    assert response.status_code == 500


def test_build_semantic_pattern_returns_lemmas_and_operator_text(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    _write_config(config_dir)
    repository = InMemoryNlpConfigRepository()
    client = _app_with_settings_repo(config_dir, repository)

    response = client.post(
        "/api/v1/settings/nlp/semantic-pattern",
        json={"text": "Нужна консультация по умному дому"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_text"] == "Нужна консультация по умному дому"
    assert payload["lemma_text"] == "нужный консультация по умный дом"
    assert payload["tokens"] == [
        {"predicate": "normalized", "value": "нужный"},
        {"predicate": "normalized", "value": "консультация"},
        {"predicate": "normalized", "value": "по"},
        {"predicate": "normalized", "value": "умный"},
        {"predicate": "normalized", "value": "дом"},
    ]


def test_update_nlp_settings_validates_and_writes_database_revision_not_yaml(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    _write_config(config_dir)
    repository = InMemoryNlpConfigRepository()
    client = _app_with_settings_repo(config_dir, repository)
    updated = client.get("/api/v1/settings").json()["nlp"]
    updated["signals"][0]["patterns"].append(
        {
            "source_text": "Нужна консультация",
            "tokens": [
                {"predicate": "normalized", "value": "нужный"},
                {"predicate": "normalized", "value": "консультация"},
            ],
        }
    )
    updated["signals"][0]["group"] = "Активный спрос"
    updated["lead_scoring"]["signal_weights"]["demand"] = 25
    updated["lead_scoring"]["review_lanes"][0]["priority"] = 250
    updated["vendors"][0]["aliases"].append("Аккара")
    updated["alias_matching"]["fuzzy_enabled"] = True
    updated["alias_matching"]["fuzzy_max_distance"] = 1

    response = client.put("/api/v1/settings/nlp", json=updated)

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"]["type"] == "postgres"
    assert payload["source"]["revision"] == 2
    assert payload["signals"][0]["patterns"][1]["source_text"] == "Нужна консультация"
    assert payload["signals"][0]["group"] == "Активный спрос"
    assert repository.active is not None
    assert repository.active["signals"]["signals"][0]["patterns"][1]["source_text"] == "Нужна консультация"
    assert repository.active["signals"]["signals"][0]["group"] == "Активный спрос"
    assert repository.active["lead_scoring"]["lead_scoring"]["weights"]["signals"]["demand"] == 25
    assert repository.active["lead_scoring"]["lead_scoring"]["review_lanes"][0]["priority"] == 250
    assert repository.active["vendors"]["vendors"][0]["aliases"] == ["Aqara", "Акара", "Аккара"]
    assert repository.active["pipeline"]["alias_matching"]["fuzzy_enabled"] is True
    assert repository.active["pipeline"]["alias_matching"]["fuzzy_max_distance"] == 1
    assert "консультация" not in (config_dir / "signals.yaml").read_text(encoding="utf-8")
    assert "Аккара" not in (config_dir / "vendors.yaml").read_text(encoding="utf-8")


def test_constructor_noise_adds_selected_text_to_postgres_nlp_revision(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    _write_config(config_dir)
    repository = InMemoryNlpConfigRepository()
    client = _app_with_settings_repo(config_dir, repository)

    response = client.post(
        "/api/v1/settings/nlp/constructor/noise",
        json={
            "text": "DSS Express",
            "source_message_id": "focus-1",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["text"] == "DSS Express"
    assert payload["signal_type"] == "operator_noise"
    assert payload["signal_label"] == "Операторский шум"
    assert payload["phrase"] == ["dss", "express"]
    assert payload["created_rule"] is True
    assert payload["created_phrase"] is True
    assert payload["nlp"]["source"]["revision"] == 2
    assert repository.active is not None

    operator_noise = next(
        signal
        for signal in repository.active["signals"]["signals"]
        if signal["type"] == "operator_noise"
    )
    assert operator_noise["phrases"] == [["dss", "express"]]
    scoring = repository.active["lead_scoring"]["lead_scoring"]
    assert scoring["weights"]["signals"]["operator_noise"] == -50
    assert "operator_noise" in scoring["noise_signal_types"]
    assert "operator_noise" in scoring["lead_veto_signal_types"]
    assert "operator_noise" in scoring["review_lanes"][0]["excluded_noise_signal_types"]
    assert "DSS Express" not in (config_dir / "signals.yaml").read_text(encoding="utf-8")


def test_constructor_noise_phrase_matches_original_text_with_symbol_separator(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    _write_config(config_dir)
    repository = InMemoryNlpConfigRepository()
    client = _app_with_settings_repo(config_dir, repository)

    response = client.post(
        "/api/v1/settings/nlp/constructor/noise",
        json={
            "text": "Бот создан в @botsbaseru",
            "source_message_id": "focus-1",
        },
    )

    assert response.status_code == 200
    nlp_settings = response.json()["nlp"]
    nlp_settings["pipeline"]["stages"].append({"name": "lead_scoring", "enabled": True})
    nlp_settings["lead_scoring"]["signal_weights"]["demand"] = 100
    preview = client.post(
        "/api/v1/settings/nlp/preview",
        json={
            "nlp": nlp_settings,
            "text": "Нужна консультация. 🔖ads: Бот создан в @botsbaseru",
        },
    )

    assert preview.status_code == 200
    payload = preview.json()
    assert any(signal["type"] == "operator_noise" for signal in payload["domain_signals"])
    assessment = payload["lead_assessment"]
    assert assessment["score"] == 0
    assert assessment["is_lead"] is False
    assert assessment["temperature"] == "none"
    assert assessment["noise_signals"][0]["type"] == "operator_noise"
    assert any(reason["source"] == "score_cap" for reason in assessment["reasons"])


def test_constructor_alias_adds_selected_text_to_existing_catalog_item(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    _write_config(config_dir)
    repository = InMemoryNlpConfigRepository()
    client = _app_with_settings_repo(config_dir, repository)

    response = client.post(
        "/api/v1/settings/nlp/constructor/alias",
        json={
            "text": "Аккара",
            "source_message_id": "focus-1",
            "catalog": "vendors",
            "key": "aqara",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["text"] == "Аккара"
    assert payload["catalog"] == "vendors"
    assert payload["key"] == "aqara"
    assert payload["created_target"] is False
    assert payload["created_entry"] is True
    assert payload["settings_ref"] == {
        "section": "aliases",
        "catalog": "vendors",
        "key": "aqara",
        "label": "Aqara",
    }
    assert repository.active is not None
    assert repository.active["vendors"]["vendors"][0]["aliases"] == ["Aqara", "Акара", "Аккара"]
    assert "Аккара" not in (config_dir / "vendors.yaml").read_text(encoding="utf-8")


def test_constructor_fact_adds_exact_phrase_to_existing_fact_rule(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    _write_config(config_dir)
    repository = InMemoryNlpConfigRepository()
    client = _app_with_settings_repo(config_dir, repository)

    response = client.post(
        "/api/v1/settings/nlp/constructor/fact",
        json={
            "text": "до завтра",
            "source_message_id": "focus-1",
            "target_type": "deadline",
            "phrase_kind": "exact",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["text"] == "до завтра"
    assert payload["rule_type"] == "deadline"
    assert payload["rule_label"] == "Срок"
    assert payload["phrase_kind"] == "exact"
    assert payload["created_target"] is False
    assert payload["created_entry"] is True
    assert payload["exact_phrase"] == ["до", "завтра"]
    assert repository.active is not None
    assert repository.active["facts"]["facts"][0]["phrases"] == [["завтра"], ["до", "завтра"]]
    assert "до завтра" not in (config_dir / "facts.yaml").read_text(encoding="utf-8")


def test_constructor_signal_creates_semantic_rule_with_zero_weight(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    _write_config(config_dir)
    repository = InMemoryNlpConfigRepository()
    client = _app_with_settings_repo(config_dir, repository)

    response = client.post(
        "/api/v1/settings/nlp/constructor/signal",
        json={
            "text": "камера DSS",
            "source_message_id": "focus-1",
            "target_type": "operator_dss_context",
            "target_label": "DSS контекст",
            "group": "Операторские сигналы",
            "phrase_kind": "semantic",
            "confidence": 0.6,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["rule_type"] == "operator_dss_context"
    assert payload["rule_label"] == "DSS контекст"
    assert payload["phrase_kind"] == "semantic"
    assert payload["created_target"] is True
    assert payload["created_entry"] is True
    assert payload["semantic_pattern"]["source_text"] == "камера DSS"
    assert payload["settings_ref"] == {
        "section": "signals",
        "key": "operator_dss_context",
        "label": "DSS контекст",
    }
    assert repository.active is not None
    signal = repository.active["signals"]["signals"][-1]
    assert signal["type"] == "operator_dss_context"
    assert signal["label"] == "DSS контекст"
    assert signal["group"] == "Операторские сигналы"
    assert signal["patterns"][0]["source_text"] == "камера DSS"
    assert repository.active["lead_scoring"]["lead_scoring"]["weights"]["signals"]["operator_dss_context"] == 0
    assert "DSS контекст" not in (config_dir / "signals.yaml").read_text(encoding="utf-8")


def test_preview_nlp_settings_uses_draft_without_saving(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    _write_config(config_dir)
    repository = InMemoryNlpConfigRepository()
    client = _app_with_settings_repo(config_dir, repository)
    draft = client.get("/api/v1/settings").json()["nlp"]
    draft["signals"][0]["phrases"].append(["ищем", "поставщика"])
    draft["signals"].append(
        {
            "type": "smart_home_platform",
            "label": "Платформа умного дома",
            "group": "Умный дом",
            "phrases": [],
            "patterns": [],
            "match": {"aliases": [{"catalog": "vendors", "keys": ["aqara"]}], "facts": []},
        }
    )
    draft["vendors"][0]["aliases"].append("Аккара")
    draft["pipeline"]["stages"].append({"name": "lead_scoring", "enabled": True})
    draft["lead_scoring"]["lead_threshold"] = 20
    draft["lead_scoring"]["signal_weights"]["smart_home_platform"] = 20

    response = client.post(
        "/api/v1/settings/nlp/preview",
        json={"text": "Ищем поставщика Аккара завтра", "nlp": draft},
    )

    assert response.status_code == 200
    payload = response.json()
    assert any(item["type"] == "demand" for item in payload["domain_signals"])
    assert any(item["type"] == "smart_home_platform" for item in payload["domain_signals"])
    assert payload["lead_assessment"]["is_lead"] is True
    assert "ищем" not in (config_dir / "signals.yaml").read_text(encoding="utf-8")
    assert repository.active is not None
    assert ["ищем", "поставщика"] not in repository.active["signals"]["signals"][0]["phrases"]
    assert "Аккара" not in repository.active["vendors"]["vendors"][0]["aliases"]
