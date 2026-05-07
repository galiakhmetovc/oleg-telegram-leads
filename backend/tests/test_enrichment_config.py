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
