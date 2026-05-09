from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from app.application.evaluation.review_eval import ReviewEvalReport, ReviewEvalRow
from app.application.evaluation.review_eval import build_review_eval_report
from app.db.session import create_sessionmaker
from app.infrastructure.persistence.analytics_repository import PostgresAnalyticsRepository


async def load_review_eval_rows(*, limit: int | None = None) -> list[ReviewEvalRow]:
    return await PostgresAnalyticsRepository(create_sessionmaker()).list_review_eval_rows(limit=limit)


def render_markdown_report(report: ReviewEvalReport) -> str:
    lines = [
        "# Review Eval Report",
        "",
        f"- reviewed: {report.reviewed}",
        f"- evaluated: {report.evaluated}",
        f"- skipped_uncertain: {report.skipped_uncertain}",
        f"- skipped_missing_prediction: {report.skipped_missing_prediction}",
        "",
        "| metric | value |",
        "| --- | ---: |",
        f"| precision | {report.precision:.6f} |",
        f"| recall | {report.recall:.6f} |",
        f"| specificity | {report.specificity:.6f} |",
        f"| accuracy | {report.accuracy:.6f} |",
        f"| f1 | {report.f1:.6f} |",
        "",
        "| cell | count |",
        "| --- | ---: |",
        f"| true_positive | {report.true_positive} |",
        f"| false_positive | {report.false_positive} |",
        f"| true_negative | {report.true_negative} |",
        f"| false_negative | {report.false_negative} |",
        "",
        "| verdict | count |",
        "| --- | ---: |",
    ]
    for verdict, count in sorted(report.by_verdict.items()):
        lines.append(f"| {verdict} | {count} |")

    lines.extend(_markdown_examples("False Positives", report.false_positives))
    lines.extend(_markdown_examples("False Negatives", report.false_negatives))
    return "\n".join(lines) + "\n"


def _markdown_examples(title: str, examples: list[dict[str, Any]]) -> list[str]:
    lines = ["", f"## {title}", ""]
    if not examples:
        lines.append("No examples.")
        return lines
    lines.extend(["| source_message_id | verdict | score | lane | text |", "| --- | --- | ---: | --- | --- |"])
    for example in examples:
        lines.append(
            "| "
            f"{example['source_message_id']} | "
            f"{example['verdict']} | "
            f"{example['score']} | "
            f"{example['review_lane']} | "
            f"{_escape_markdown_table(str(example['text_preview']))} |"
        )
    return lines


def _escape_markdown_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate automatic lead detection against saved message reviews.")
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    parser.add_argument("--output", type=Path, default=None, help="Optional output file. Defaults to stdout.")
    parser.add_argument("--limit", type=int, default=None, help="Limit reviewed rows, newest first.")
    parser.add_argument("--examples", type=int, default=20, help="Max false positive/negative examples.")
    return parser


async def run(argv: list[str] | None = None) -> ReviewEvalReport:
    args = build_parser().parse_args(argv)
    rows = await load_review_eval_rows(limit=args.limit)
    report = build_review_eval_report(rows, example_limit=args.examples)
    rendered = (
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n"
        if args.format == "json"
        else render_markdown_report(report)
    )
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    asyncio.run(run(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
