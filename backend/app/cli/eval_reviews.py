from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import sqlalchemy as sa

from app.db.session import create_sessionmaker
from app.infrastructure.persistence.tables import enrichment_results
from app.infrastructure.persistence.tables import message_reviews
from app.infrastructure.persistence.tables import telegram_source_chats
from app.infrastructure.persistence.tables import telegram_source_messages

POSITIVE_REVIEW_VERDICTS = {"lead"}
NEGATIVE_REVIEW_VERDICTS = {"not_lead", "noise"}


@dataclass(frozen=True)
class ReviewEvalRow:
    source_message_id: str
    telegram_message_id: int | None
    source_chat_title: str | None
    verdict: str | None
    predicted_is_lead: bool | None
    score: int
    temperature: str
    review_lane: str
    text: str


@dataclass(frozen=True)
class ReviewEvalReport:
    reviewed: int
    evaluated: int
    skipped_uncertain: int
    skipped_missing_prediction: int
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    precision: float
    recall: float
    specificity: float
    accuracy: float
    f1: float
    by_verdict: dict[str, int]
    false_positives: list[dict[str, Any]]
    false_negatives: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def expected_lead_from_verdict(verdict: str | None) -> bool | None:
    if verdict in POSITIVE_REVIEW_VERDICTS:
        return True
    if verdict in NEGATIVE_REVIEW_VERDICTS:
        return False
    return None


def build_review_eval_report(
    rows: list[ReviewEvalRow],
    *,
    example_limit: int = 20,
) -> ReviewEvalReport:
    true_positive = 0
    false_positive = 0
    true_negative = 0
    false_negative = 0
    skipped_uncertain = 0
    skipped_missing_prediction = 0
    false_positives: list[dict[str, Any]] = []
    false_negatives: list[dict[str, Any]] = []

    for row in rows:
        expected = expected_lead_from_verdict(row.verdict)
        if expected is None:
            skipped_uncertain += 1
            continue
        if row.predicted_is_lead is None:
            skipped_missing_prediction += 1
            continue

        if expected and row.predicted_is_lead:
            true_positive += 1
        elif expected and not row.predicted_is_lead:
            false_negative += 1
            if len(false_negatives) < example_limit:
                false_negatives.append(_row_example(row))
        elif not expected and row.predicted_is_lead:
            false_positive += 1
            if len(false_positives) < example_limit:
                false_positives.append(_row_example(row))
        else:
            true_negative += 1

    evaluated = true_positive + false_positive + true_negative + false_negative
    precision = _rounded_ratio(true_positive, true_positive + false_positive)
    recall = _rounded_ratio(true_positive, true_positive + false_negative)
    specificity = _rounded_ratio(true_negative, true_negative + false_positive)
    accuracy = _rounded_ratio(true_positive + true_negative, evaluated)
    f1 = _rounded_ratio(2 * true_positive, 2 * true_positive + false_positive + false_negative)

    return ReviewEvalReport(
        reviewed=len(rows),
        evaluated=evaluated,
        skipped_uncertain=skipped_uncertain,
        skipped_missing_prediction=skipped_missing_prediction,
        true_positive=true_positive,
        false_positive=false_positive,
        true_negative=true_negative,
        false_negative=false_negative,
        precision=precision,
        recall=recall,
        specificity=specificity,
        accuracy=accuracy,
        f1=f1,
        by_verdict=dict(Counter(row.verdict or "unknown" for row in rows)),
        false_positives=false_positives,
        false_negatives=false_negatives,
    )


async def load_review_eval_rows(*, limit: int | None = None) -> list[ReviewEvalRow]:
    session_factory = create_sessionmaker()
    statement = (
        sa.select(
            message_reviews.c.source_message_id,
            message_reviews.c.verdict,
            telegram_source_messages.c.telegram_message_id,
            telegram_source_messages.c.text,
            telegram_source_chats.c.title.label("source_chat_title"),
            enrichment_results.c.result,
        )
        .select_from(
            message_reviews.join(
                telegram_source_messages,
                telegram_source_messages.c.id == message_reviews.c.source_message_id,
            )
            .outerjoin(
                telegram_source_chats,
                telegram_source_chats.c.id == telegram_source_messages.c.source_chat_id,
            )
            .outerjoin(
                enrichment_results,
                enrichment_results.c.job_id == telegram_source_messages.c.enrichment_job_id,
            )
        )
        .order_by(message_reviews.c.updated_at.desc())
    )
    if limit is not None:
        statement = statement.limit(limit)

    async with session_factory() as session:
        result = await session.execute(statement)
        return [_eval_row_from_mapping(row._mapping) for row in result]


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


def _eval_row_from_mapping(row: Mapping[Any, Any]) -> ReviewEvalRow:
    result = row.get("result")
    assessment = result.get("lead_assessment") if isinstance(result, dict) else None
    if not isinstance(assessment, dict):
        assessment = {}
    raw_lane = assessment.get("review_lane")
    review_lane = str(raw_lane.get("key", "")) if isinstance(raw_lane, dict) else ""
    raw_predicted = assessment.get("is_lead")
    predicted_is_lead = raw_predicted if isinstance(raw_predicted, bool) else None

    return ReviewEvalRow(
        source_message_id=str(row["source_message_id"]),
        telegram_message_id=_optional_int(row.get("telegram_message_id")),
        source_chat_title=_optional_str(row.get("source_chat_title")),
        verdict=_optional_str(row.get("verdict")),
        predicted_is_lead=predicted_is_lead,
        score=_int_or_zero(assessment.get("score")),
        temperature=str(assessment.get("temperature") or ""),
        review_lane=review_lane,
        text=str(row.get("text") or ""),
    )


def _row_example(row: ReviewEvalRow) -> dict[str, Any]:
    return {
        "source_message_id": row.source_message_id,
        "telegram_message_id": row.telegram_message_id,
        "source_chat_title": row.source_chat_title,
        "verdict": row.verdict,
        "predicted_is_lead": row.predicted_is_lead,
        "score": row.score,
        "temperature": row.temperature,
        "review_lane": row.review_lane,
        "text_preview": _text_preview(row.text),
    }


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


def _text_preview(text: str, *, limit: int = 240) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _escape_markdown_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _rounded_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _int_or_zero(value)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _int_or_zero(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float | str | bytes | bytearray):
        return int(value)
    raise TypeError(f"cannot convert {type(value).__name__} to int")


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
