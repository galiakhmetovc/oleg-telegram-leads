from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.infrastructure.nlp.config_loader import load_nlp_config
from app.infrastructure.nlp.russian_text_enricher import RussianTextEnricher


@dataclass(frozen=True)
class BatchEnrichmentSummary:
    input_path: str
    output_path: str
    summary_path: str
    processed: int
    skipped: int
    failed: int
    leads: int
    limit: int | None
    elapsed_seconds: float
    messages_per_second: float
    started_at: str
    finished_at: str


def run_batch_enrichment(
    *,
    input_path: Path,
    output_path: Path,
    summary_path: Path,
    config_dir: Path,
    limit: int | None,
    progress_interval: int,
) -> BatchEnrichmentSummary:
    started_at = datetime.now(UTC)
    start_time = time.perf_counter()
    config = load_nlp_config(config_dir)
    enricher = RussianTextEnricher(config)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    processed = 0
    skipped = 0
    failed = 0
    leads = 0

    with input_path.open(encoding="utf-8") as input_file:
        with output_path.open("w", encoding="utf-8") as output_file:
            for line_number, line in enumerate(input_file, start=1):
                if limit is not None and processed >= limit:
                    break

                raw_message = json.loads(line)
                message_id = raw_message.get("message_id", raw_message.get("id"))
                text = _message_text(raw_message)
                if not text:
                    skipped += 1
                    continue

                try:
                    result = enricher.enrich(text)
                except Exception as exc:  # pragma: no cover - defensive batch isolation
                    failed += 1
                    output_file.write(
                        json.dumps(
                            {
                                "message_id": message_id,
                                "text": text,
                                "error": {
                                    "type": type(exc).__name__,
                                    "message": str(exc),
                                    "line_number": line_number,
                                },
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    continue

                if result.lead_assessment is not None and result.lead_assessment.is_lead:
                    leads += 1

                output_file.write(
                    json.dumps(
                        {
                            "message_id": message_id,
                            "text": text,
                            "result": result.to_dict(),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                processed += 1

                if progress_interval > 0 and processed % progress_interval == 0:
                    _print_progress(processed, skipped, failed, leads, start_time)

    finished_at = datetime.now(UTC)
    elapsed_seconds = time.perf_counter() - start_time
    messages_per_second = processed / elapsed_seconds if elapsed_seconds > 0 else 0.0
    summary = BatchEnrichmentSummary(
        input_path=str(input_path),
        output_path=str(output_path),
        summary_path=str(summary_path),
        processed=processed,
        skipped=skipped,
        failed=failed,
        leads=leads,
        limit=limit,
        elapsed_seconds=round(elapsed_seconds, 6),
        messages_per_second=round(messages_per_second, 6),
        started_at=started_at.isoformat(),
        finished_at=finished_at.isoformat(),
    )
    summary_path.write_text(
        json.dumps(asdict(summary), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def _message_text(raw_message: dict[str, Any]) -> str:
    text = raw_message.get("text", "")
    if isinstance(text, str):
        return text.strip()
    if isinstance(text, list):
        parts = [
            item if isinstance(item, str) else str(item.get("text", ""))
            for item in text
            if isinstance(item, str) or isinstance(item, dict)
        ]
        return "".join(parts).strip()
    return ""


def _print_progress(
    processed: int,
    skipped: int,
    failed: int,
    leads: int,
    start_time: float,
) -> None:
    elapsed_seconds = time.perf_counter() - start_time
    rate = processed / elapsed_seconds if elapsed_seconds > 0 else 0.0
    print(
        (
            f"processed={processed} skipped={skipped} failed={failed} "
            f"leads={leads} rate={rate:.3f}/s elapsed={elapsed_seconds:.1f}s"
        ),
        file=sys.stderr,
        flush=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run full text enrichment for JSONL messages.")
    parser.add_argument("--input", required=True, type=Path, help="Input JSONL with message_id/text")
    parser.add_argument("--output", required=True, type=Path, help="Output full enrichment JSONL")
    parser.add_argument(
        "--summary",
        type=Path,
        default=None,
        help="Summary JSON path. Defaults to <output>.summary.json",
    )
    parser.add_argument("--config-dir", type=Path, default=Path("config/nlp"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--progress-interval", type=int, default=100)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary_path = args.summary or args.output.with_suffix(args.output.suffix + ".summary.json")
    summary = run_batch_enrichment(
        input_path=args.input,
        output_path=args.output,
        summary_path=summary_path,
        config_dir=args.config_dir,
        limit=args.limit,
        progress_interval=args.progress_interval,
    )
    print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))
    return 0 if summary.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
