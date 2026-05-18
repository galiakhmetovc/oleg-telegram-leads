from pathlib import Path

import pytest

from app.infrastructure.nlp.config_loader import load_nlp_config, read_nlp_config_documents


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
    match:
      facts:
        - intent_need
""",
        encoding="utf-8",
    )
    (config_dir / "facts.yaml").write_text(
        """
facts:
  - type: intent_need
    label: Потребность
    group: Спрос и намерение
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
    assert config.signals[0].phrases == ()
    assert config.signals[0].match.facts[0].types == ("intent_need",)
    assert config.facts[0].phrases == (("нужна",), ("ищем", "поставщика"))


def test_default_config_uses_canonical_operator_groups() -> None:
    documents = read_nlp_config_documents(Path("config/nlp"))
    facts = documents["facts"]["facts"]
    signals = documents["signals"]["signals"]

    fact_groups = {fact.get("group") for fact in facts}
    signal_groups = {signal.get("group") for signal in signals}

    legacy_groups = {
        "V3: намерение",
        "V3: контекст",
        "V3: сегмент",
        "V3: объект",
        "V3: домен",
        "V3: шум",
        "Интенты",
        "Домены",
        "Намерение партнерства",
        "Контекст объекта",
        "Контекст проекта",
    }
    assert fact_groups.isdisjoint(legacy_groups)
    assert signal_groups.isdisjoint(legacy_groups)
    assert {fact["group"] for fact in facts if str(fact.get("type", "")).startswith("intent_")} == {"Намерение"}
    assert {
        signal["group"]
        for signal in signals
        if str(signal.get("type", "")).startswith("lead_")
    } == {"Намерение"}
    assert all(not str(fact.get("label", "")).startswith("Интент:") for fact in facts)
    assert all("интент" not in str(signal.get("label", "")).casefold() for signal in signals)
    forbidden_acronym = "П" + "УР"
    assert all(forbidden_acronym not in str(signal.get("label", "")) for signal in signals)
    assert all(forbidden_acronym not in str(signal.get("group", "")) for signal in signals)
    scoring = documents["lead_scoring"]["lead_scoring"]
    scoring_text_fields = [
        item.get("label", "")
        for item in scoring.get("review_lanes", [])
    ] + [
        item.get("description", "")
        for item in scoring.get("review_lanes", [])
    ] + [
        item.get("label", "")
        for item in scoring.get("score_caps", [])
    ]
    assert all(forbidden_acronym not in str(value) for value in scoring_text_fields)


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
    (config_dir / "signals.yaml").write_text("signals: []\n", encoding="utf-8")
    (config_dir / "facts.yaml").write_text(
        """
facts:
  - type: domain_smart_home
    label: Умный дом
    patterns:
      - tokens:
          - normalized: "умный"
          - normalized: "дом"
""",
        encoding="utf-8",
    )

    config = load_nlp_config(config_dir)

    assert config.facts[0].patterns[0].tokens[0].predicate == "normalized"
    assert config.facts[0].patterns[0].tokens[0].value == "умный"
    assert config.facts[0].patterns[0].tokens[1].value == "дом"


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
    (config_dir / "vendors.yaml").write_text(
        """
vendors:
  - key: yandex
    canonical: Яндекс
    aliases:
      - Яндекс
    fact_types:
      - vendor
  - key: aqara
    canonical: Aqara
    aliases:
      - Aqara
    fact_types:
      - vendor
""",
        encoding="utf-8",
    )
    (config_dir / "software.yaml").write_text(
        """
software:
  - key: alice
    canonical: Алиса
    aliases:
      - Алиса
    fact_types:
      - software
""",
        encoding="utf-8",
    )
    (config_dir / "devices.yaml").write_text(
        """
devices:
  - key: controller
    canonical: Контроллер
    aliases:
      - контроллер
    fact_types:
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


def test_rejects_signal_text_match_sources_from_yaml(tmp_path: Path) -> None:
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
      facts:
        - domain_smart_home
""",
        encoding="utf-8",
    )
    (config_dir / "facts.yaml").write_text(
        """
facts:
  - type: domain_smart_home
    label: Умный дом
    phrases:
      - ["умный", "дом"]
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="signals must use match.facts"):
        load_nlp_config(config_dir)


def test_rejects_alias_text_reused_in_fact_rule(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    config_dir.mkdir()
    (config_dir / "pipeline.yaml").write_text("stages: []\n", encoding="utf-8")
    (config_dir / "signals.yaml").write_text("signals: []\n", encoding="utf-8")
    (config_dir / "devices.yaml").write_text(
        """
devices:
  - key: wifi_module
    canonical: Wi-Fi модуль
    type: device
    aliases:
      - Wi-Fi модуль
    fact_types:
      - automation_component
""",
        encoding="utf-8",
    )
    (config_dir / "facts.yaml").write_text(
        """
facts:
  - type: domain_network
    label: Сеть
    patterns:
      - source_text: "Wi-Fi модуль"
        tokens:
          - normalized: "wi"
          - normalized: "fi"
          - normalized: "модуль"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="alias text is already owned by devices:wifi_module"):
        load_nlp_config(config_dir)


def test_rejects_separator_equivalent_alias_text_reused_in_fact_rule(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    config_dir.mkdir()
    (config_dir / "pipeline.yaml").write_text(
        """
stages: []
alias_matching:
  normalize_separators: true
""",
        encoding="utf-8",
    )
    (config_dir / "signals.yaml").write_text("signals: []\n", encoding="utf-8")
    (config_dir / "protocols.yaml").write_text(
        """
protocols:
  - key: wifi
    canonical: Wi-Fi
    aliases:
      - Wi-Fi
    fact_types:
      - protocol
""",
        encoding="utf-8",
    )
    (config_dir / "facts.yaml").write_text(
        """
facts:
  - type: technical_exact_fact
    label: Технический факт
    phrases:
      - ["wi", "fi"]
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="alias text is already owned by protocols:wifi"):
        load_nlp_config(config_dir)


def test_rejects_alias_text_reused_in_another_alias_owner(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    config_dir.mkdir()
    (config_dir / "pipeline.yaml").write_text("stages: []\n", encoding="utf-8")
    (config_dir / "signals.yaml").write_text("signals: []\n", encoding="utf-8")
    (config_dir / "protocols.yaml").write_text(
        """
protocols:
  - key: wifi
    canonical: Wi-Fi
    aliases:
      - Wi-Fi
""",
        encoding="utf-8",
    )
    (config_dir / "devices.yaml").write_text(
        """
devices:
  - key: wifi_module
    canonical: Wi-Fi модуль
    aliases:
      - Wi-Fi
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="alias text 'Wi-Fi' is already owned by protocols:wifi"):
        load_nlp_config(config_dir)


def test_alias_canonical_label_does_not_claim_unmatched_text(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    config_dir.mkdir()
    (config_dir / "pipeline.yaml").write_text("stages: []\n", encoding="utf-8")
    (config_dir / "signals.yaml").write_text("signals: []\n", encoding="utf-8")
    (config_dir / "vendors.yaml").write_text(
        """
vendors:
  - key: ekf
    canonical: EKF Connect
    aliases:
      - EKF
    fact_types:
      - vendor
""",
        encoding="utf-8",
    )
    (config_dir / "software.yaml").write_text(
        """
software:
  - key: ekf_connect_home
    canonical: EKF Connect Home
    aliases:
      - EKF Connect
    fact_types:
      - software
""",
        encoding="utf-8",
    )

    config = load_nlp_config(config_dir)

    assert config.aliases[0].canonical == "EKF Connect"
    assert config.aliases[1].aliases == ("EKF Connect",)


def test_rejects_fact_text_reused_in_another_fact_rule(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    config_dir.mkdir()
    (config_dir / "pipeline.yaml").write_text("stages: []\n", encoding="utf-8")
    (config_dir / "signals.yaml").write_text("signals: []\n", encoding="utf-8")
    (config_dir / "facts.yaml").write_text(
        """
facts:
  - type: intent_need
    label: Нужно
    phrases:
      - ["хочу"]
  - type: consultation_need
    label: Консультация
    patterns:
      - source_text: "хочу"
        tokens:
          - normalized: "хотеть"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="text is already owned by facts:intent_need"):
        load_nlp_config(config_dir)


def test_rejects_signal_match_fact_reference_without_emitter(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    config_dir.mkdir()
    (config_dir / "pipeline.yaml").write_text("stages: []\n", encoding="utf-8")
    (config_dir / "signals.yaml").write_text(
        """
signals:
  - type: pur_gate_automation
    label: Ворота
    match:
      facts:
        - types:
            - domain_gate_automation
""",
        encoding="utf-8",
    )
    (config_dir / "facts.yaml").write_text("facts: []\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unknown fact type domain_gate_automation"):
        load_nlp_config(config_dir)


def test_rejects_lead_scoring_fact_weight_without_emitter(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    config_dir.mkdir()
    (config_dir / "pipeline.yaml").write_text("stages: []\n", encoding="utf-8")
    (config_dir / "signals.yaml").write_text("signals: []\n", encoding="utf-8")
    (config_dir / "facts.yaml").write_text("facts: []\n", encoding="utf-8")
    (config_dir / "lead_scoring.yaml").write_text(
        """
lead_scoring:
  weights:
    facts:
      domain_power_stability: 5
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown fact type domain_power_stability"):
        load_nlp_config(config_dir)


def test_rejects_lead_scoring_noise_signal_without_signal_rule(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    config_dir.mkdir()
    (config_dir / "pipeline.yaml").write_text("stages: []\n", encoding="utf-8")
    (config_dir / "signals.yaml").write_text("signals: []\n", encoding="utf-8")
    (config_dir / "facts.yaml").write_text("facts: []\n", encoding="utf-8")
    (config_dir / "lead_scoring.yaml").write_text(
        """
lead_scoring:
  noise_signal_types:
    - operator_noise
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown signal type operator_noise"):
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
    (config_dir / "signals.yaml").write_text("signals: []\n", encoding="utf-8")
    (config_dir / "facts.yaml").write_text(
        """
facts:
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

    with pytest.raises(ValueError, match="unsupported facts pattern predicate: caseless"):
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

    with pytest.raises(ValueError, match="signals must use match.facts"):
        load_nlp_config(config_dir)
