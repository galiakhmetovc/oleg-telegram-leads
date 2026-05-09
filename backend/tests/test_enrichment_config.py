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
    group: Спрос и намерение
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
    assert config.signals[0].group == "Спрос и намерение"
    assert config.signals[0].phrases == (("нужна",), ("ищем", "поставщика"))


def test_loads_alias_matching_settings_from_pipeline_yaml(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    config_dir.mkdir()
    (config_dir / "pipeline.yaml").write_text(
        """
stages: []
alias_matching:
  normalize_separators: true
  normalize_yo: true
  normalize_latin_confusables: true
  fuzzy_enabled: true
  fuzzy_min_length: 5
  fuzzy_max_distance: 1
  fuzzy_long_min_length: 10
  fuzzy_long_max_distance: 2
  fuzzy_excluded_aliases:
    - knx
    - sst
""",
        encoding="utf-8",
    )
    (config_dir / "signals.yaml").write_text("signals: []\n", encoding="utf-8")

    config = load_nlp_config(config_dir)

    assert config.alias_matching.normalize_separators is True
    assert config.alias_matching.normalize_latin_confusables is True
    assert config.alias_matching.fuzzy_enabled is True
    assert config.alias_matching.fuzzy_min_length == 5
    assert config.alias_matching.fuzzy_long_max_distance == 2
    assert config.alias_matching.fuzzy_excluded_aliases == ("knx", "sst")


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


def test_loads_signal_fact_dependencies_from_yaml(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    config_dir.mkdir()
    (config_dir / "pipeline.yaml").write_text("stages: []\n", encoding="utf-8")
    (config_dir / "signals.yaml").write_text(
        """
signals:
  - type: smart_home
    label: Умный дом
    match:
      facts:
        - types:
            - alias:vendors:yandex
            - alias:vendors:aqara
        - types:
            - alias:software:alice
        - types:
            - automation_component
""",
        encoding="utf-8",
    )

    config = load_nlp_config(config_dir)

    assert config.signals[0].match.facts[0].types == ("alias:vendors:yandex", "alias:vendors:aqara")
    assert config.signals[0].match.facts[1].types == ("alias:software:alice",)
    assert config.signals[0].match.facts[2].types == ("automation_component",)


def test_rejects_direct_signal_alias_dependencies_from_yaml(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    config_dir.mkdir()
    (config_dir / "pipeline.yaml").write_text("stages: []\n", encoding="utf-8")
    (config_dir / "signals.yaml").write_text(
        """
signals:
  - type: smart_home
    label: Умный дом
    match:
      aliases:
        - catalog: vendors
          keys:
            - yandex
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="match.aliases is not supported"):
        load_nlp_config(config_dir)


def test_rejects_empty_direct_signal_alias_dependencies_from_yaml(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    config_dir.mkdir()
    (config_dir / "pipeline.yaml").write_text("stages: []\n", encoding="utf-8")
    (config_dir / "signals.yaml").write_text(
        """
signals:
  - type: smart_home
    label: Умный дом
    phrases:
      - ["умный", "дом"]
    match:
      aliases: []
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="match.aliases is not supported"):
        load_nlp_config(config_dir)


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

    config = load_nlp_config(config_dir)

    assert [item.key for item in config.aliases] == ["aqara", "zigbee"]
    assert config.aliases[0].canonical == "Aqara"
    assert config.aliases[0].kind == "vendor"
    assert config.aliases[0].aliases == ("Aqara", "Акара", "Аккара")
    assert config.aliases[0].catalog == "vendors"
    assert config.aliases[1].fact_types == ("protocol",)


def test_rejects_signal_without_any_match_source(tmp_path: Path) -> None:
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

    with pytest.raises(ValueError, match="phrases, patterns, or match"):
        load_nlp_config(config_dir)
