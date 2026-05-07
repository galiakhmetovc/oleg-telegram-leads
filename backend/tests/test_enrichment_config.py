from pathlib import Path

import pytest

from app.infrastructure.nlp.config_loader import load_nlp_config


def test_loads_pipeline_and_domain_signals_from_yaml(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
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
    phrases:
      - ["нужна"]
      - ["ищем", "поставщика"]
""",
        encoding="utf-8",
    )

    config = load_nlp_config(config_dir)

    assert [stage.name for stage in config.enabled_stages] == ["segmentation", "domain_signals"]
    assert config.signals[0].type == "demand"
    assert config.signals[0].phrases == (("нужна",), ("ищем", "поставщика"))


def test_loads_normalized_yargy_patterns_from_yaml(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    config_dir.mkdir()
    (config_dir / "pipeline.yaml").write_text("stages: []\n", encoding="utf-8")
    (config_dir / "signals.yaml").write_text(
        """
signals:
  - type: smart_home
    label: Умный дом
    patterns:
      - tokens:
          - normalized: "умный"
          - normalized: "дом"
""",
        encoding="utf-8",
    )

    config = load_nlp_config(config_dir)

    assert config.signals[0].patterns[0].tokens[0].predicate == "normalized"
    assert config.signals[0].patterns[0].tokens[0].value == "умный"
    assert config.signals[0].patterns[0].tokens[1].value == "дом"


def test_rejects_unsupported_pattern_predicates(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    config_dir.mkdir()
    (config_dir / "pipeline.yaml").write_text("stages: []\n", encoding="utf-8")
    (config_dir / "signals.yaml").write_text(
        """
signals:
  - type: technical_terms
    label: Технические термины
    patterns:
      - tokens:
          - caseless: "СКУД"
      - tokens:
          - caseless: "zigbee"
          - normalized: "шлюз"
      - tokens:
          - caseless: "wi-fi"
          - normalized: "модуль"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsupported signals pattern predicate: caseless"):
        load_nlp_config(config_dir)


def test_loads_alias_catalogs_from_yaml(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    config_dir.mkdir()
    (config_dir / "pipeline.yaml").write_text("stages: []\n", encoding="utf-8")
    (config_dir / "signals.yaml").write_text("signals: []\n", encoding="utf-8")
    (config_dir / "vendors.yaml").write_text(
        """
vendors:
  - key: aqara
    canonical: Aqara
    type: vendor
    aliases:
      - Aqara
      - Акара
      - Аккара
    signal_types:
      - smart_home_platform
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
    signal_types:
      - protocol_gateway
    fact_types:
      - protocol
""",
        encoding="utf-8",
    )

    config = load_nlp_config(config_dir)

    assert [item.key for item in config.aliases] == ["aqara", "zigbee"]
    assert config.aliases[0].canonical == "Aqara"
    assert config.aliases[0].kind == "vendor"
    assert config.aliases[0].aliases == ("Aqara", "Акара", "Аккара")
    assert config.aliases[0].signal_types == ("smart_home_platform",)
    assert config.aliases[1].fact_types == ("protocol",)


def test_rejects_signal_without_phrases(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    config_dir.mkdir()
    (config_dir / "pipeline.yaml").write_text("stages: []\n", encoding="utf-8")
    (config_dir / "signals.yaml").write_text(
        """
signals:
  - type: demand
    label: Потребность
    phrases: []
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="phrases"):
        load_nlp_config(config_dir)
