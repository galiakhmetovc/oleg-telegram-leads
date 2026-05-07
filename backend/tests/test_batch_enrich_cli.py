import json
from pathlib import Path

from app.cli.batch_enrich import run_batch_enrichment


def test_batch_enrichment_writes_full_results_and_summary(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    config_dir.mkdir()
    (config_dir / "pipeline.yaml").write_text(
        """
stages:
  - name: segmentation
    enabled: true
  - name: facts
    enabled: true
  - name: domain_signals
    enabled: true
  - name: lead_scoring
    enabled: true
  - name: metrics
    enabled: true
""",
        encoding="utf-8",
    )
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
    (config_dir / "facts.yaml").write_text(
        """
facts:
  - type: solution_area
    label: Направление
    patterns:
      - tokens:
          - normalized: "умный"
          - normalized: "дом"
""",
        encoding="utf-8",
    )
    (config_dir / "lead_scoring.yaml").write_text(
        """
lead_scoring:
  thresholds:
    lead: 10
    warm: 20
    hot: 40
  weights:
    signals:
      smart_home: 20
    facts:
      solution_area: 15
  solution_areas:
    smart_home:
      label: Умный дом
      signal_types:
        - smart_home
      fact_types:
        - solution_area
  customer_segments: {}
  intent_signal_types:
    - smart_home
  noise_signal_types: []
""",
        encoding="utf-8",
    )
    input_path = tmp_path / "messages.jsonl"
    output_path = tmp_path / "enriched.jsonl"
    summary_path = tmp_path / "summary.json"
    input_path.write_text(
        "\n".join(
            [
                json.dumps({"message_id": 10, "text": "Нужен умный дом"}, ensure_ascii=False),
                json.dumps({"message_id": 11, "text": "   "}, ensure_ascii=False),
                json.dumps({"message_id": 12, "text": "Обычное сообщение"}, ensure_ascii=False),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    summary = run_batch_enrichment(
        input_path=input_path,
        output_path=output_path,
        summary_path=summary_path,
        config_dir=config_dir,
        limit=None,
        progress_interval=0,
    )

    rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    persisted_summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert summary.processed == 2
    assert summary.skipped == 1
    assert summary.leads == 1
    assert persisted_summary["processed"] == 2
    assert persisted_summary["skipped"] == 1
    assert [row["message_id"] for row in rows] == [10, 12]
    assert rows[0]["result"]["lead_assessment"]["is_lead"] is True
    assert rows[0]["result"]["tokens"]
    assert rows[0]["result"]["domain_signals"][0]["type"] == "smart_home"
    assert rows[0]["result"]["facts"][0]["type"] == "solution_area"
    assert rows[1]["result"]["lead_assessment"]["is_lead"] is False
