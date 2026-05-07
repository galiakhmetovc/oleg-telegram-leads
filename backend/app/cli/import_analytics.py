from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.db.session import create_sessionmaker
from app.domain.analytics import AnalyticsAggregate, AnalyticsCandidate, AnalyticsRun
from app.infrastructure.persistence.analytics_repository import PostgresAnalyticsRepository

SCORE_BUCKETS: tuple[tuple[str, str, int, int | None], ...] = (
    ("35-59", "35-59", 35, 59),
    ("60-89", "60-89", 60, 89),
    ("90-129", "90-129", 90, 129),
    ("130+", "130+", 130, None),
)


async def import_analytics_run(
    *,
    summary_path: Path,
    lead_candidates_path: Path,
    name: str | None,
) -> AnalyticsRun:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    candidates = _read_candidates(lead_candidates_path)
    run_id = uuid4()
    run = AnalyticsRun(
        id=run_id,
        name=name or _default_run_name(summary_path),
        source="batch",
        input_path=str(summary.get("input_path", "")),
        run_dir=str(summary.get("run_dir", summary_path.parent)),
        processed=int(summary.get("processed", 0)),
        skipped=int(summary.get("skipped", 0)),
        failed=int(summary.get("failed", 0)),
        leads=int(summary.get("leads", len(candidates))),
        started_at=_earliest_worker_started_at(summary),
        finished_at=_parse_datetime(summary.get("finished_at")),
        imported_at=datetime.now(UTC),
        summary=summary,
    )
    aggregates = _build_aggregates(candidates)
    repository = PostgresAnalyticsRepository(create_sessionmaker())
    return await repository.replace_import(run, candidates, aggregates)


def _read_candidates(path: Path) -> list[AnalyticsCandidate]:
    candidates: list[AnalyticsCandidate] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        assessment = raw.get("lead_assessment") or {}
        candidates.append(
            AnalyticsCandidate(
                run_id=uuid4(),
                message_id=str(raw.get("message_id")),
                text=str(raw.get("text", "")),
                score=int(assessment.get("score", 0)),
                temperature=str(assessment.get("temperature", "unknown")),
                solution_areas=list(assessment.get("solution_areas", [])),
                customer_segments=list(assessment.get("customer_segments", [])),
                intent_signals=list(assessment.get("intent_signals", [])),
                noise_signals=list(assessment.get("noise_signals", [])),
                reasons=list(assessment.get("reasons", [])),
                domain_signals=list(raw.get("domain_signals", [])),
                facts=list(raw.get("facts", [])),
            )
        )
    return candidates


def _build_aggregates(candidates: list[AnalyticsCandidate]) -> list[AnalyticsAggregate]:
    aggregates: list[AnalyticsAggregate] = []
    aggregates.extend(_score_bucket_aggregates(candidates))
    aggregates.extend(_counter_aggregates("temperature", _temperature_counts(candidates)))
    aggregates.extend(_counter_aggregates("signal", _typed_item_counts(candidates, "domain_signals")))
    aggregates.extend(_counter_aggregates("fact", _typed_item_counts(candidates, "facts")))
    aggregates.extend(_counter_aggregates("reason", _reason_counts(candidates)))
    aggregates.extend(_counter_aggregates("solution_area", _category_counts(candidates, "solution_areas")))
    aggregates.extend(_counter_aggregates("customer_segment", _category_counts(candidates, "customer_segments")))
    aggregates.extend(_counter_aggregates("intent_signal", _category_counts(candidates, "intent_signals")))
    aggregates.extend(_counter_aggregates("noise_signal", _category_counts(candidates, "noise_signals")))
    return aggregates


def _score_bucket_aggregates(candidates: list[AnalyticsCandidate]) -> list[AnalyticsAggregate]:
    results: list[AnalyticsAggregate] = []
    for key, label, minimum, maximum in SCORE_BUCKETS:
        count = sum(
            1
            for candidate in candidates
            if candidate.score >= minimum and (maximum is None or candidate.score <= maximum)
        )
        results.append(
            AnalyticsAggregate(
                kind="score_bucket",
                key=key,
                label=label,
                count=count,
                payload={"min_score": minimum, "max_score": maximum},
            )
        )
    return results


def _temperature_counts(candidates: list[AnalyticsCandidate]) -> dict[str, tuple[str, int, dict[str, Any]]]:
    counter = Counter(candidate.temperature for candidate in candidates)
    return {
        key: (key, count, {})
        for key, count in counter.items()
    }


def _typed_item_counts(
    candidates: list[AnalyticsCandidate],
    field_name: str,
) -> dict[str, tuple[str, int, dict[str, Any]]]:
    counter: Counter[str] = Counter()
    labels: dict[str, str] = {}
    examples: dict[str, list[str]] = {}
    for candidate in candidates:
        seen_in_candidate: set[str] = set()
        for item in getattr(candidate, field_name):
            key = str(item.get("type", "unknown"))
            if key in seen_in_candidate:
                continue
            seen_in_candidate.add(key)
            counter[key] += 1
            labels.setdefault(key, str(item.get("label") or key))
            examples.setdefault(key, [])
            if item.get("text") and len(examples[key]) < 5:
                examples[key].append(str(item["text"]))
    return {
        key: (labels.get(key, key), count, {"examples": examples.get(key, [])})
        for key, count in counter.items()
    }


def _reason_counts(candidates: list[AnalyticsCandidate]) -> dict[str, tuple[str, int, dict[str, Any]]]:
    counter: Counter[str] = Counter()
    labels: dict[str, str] = {}
    examples: dict[str, list[str]] = {}
    weights: dict[str, int] = {}
    for candidate in candidates:
        seen_in_candidate: set[str] = set()
        for reason in candidate.reasons:
            key = str(reason.get("key", "unknown"))
            if key in seen_in_candidate:
                continue
            seen_in_candidate.add(key)
            counter[key] += 1
            labels.setdefault(key, str(reason.get("label") or key))
            weights.setdefault(key, int(reason.get("weight", 0)))
            examples.setdefault(key, [])
            for text in reason.get("matched_texts", []):
                if len(examples[key]) >= 5:
                    break
                examples[key].append(str(text))
    return {
        key: (
            labels.get(key, key),
            count,
            {"examples": examples.get(key, []), "weight": weights.get(key, 0)},
        )
        for key, count in counter.items()
    }


def _category_counts(
    candidates: list[AnalyticsCandidate],
    field_name: str,
) -> dict[str, tuple[str, int, dict[str, Any]]]:
    counter: Counter[str] = Counter()
    labels: dict[str, str] = {}
    matched_types: dict[str, set[str]] = {}
    for candidate in candidates:
        seen_in_candidate: set[str] = set()
        for item in getattr(candidate, field_name):
            key = str(item.get("type", "unknown"))
            if key in seen_in_candidate:
                continue
            seen_in_candidate.add(key)
            counter[key] += 1
            labels.setdefault(key, str(item.get("label") or key))
            matched_types.setdefault(key, set()).update(str(value) for value in item.get("matched_types", []))
    return {
        key: (labels.get(key, key), count, {"matched_types": sorted(matched_types.get(key, set()))})
        for key, count in counter.items()
    }


def _counter_aggregates(
    kind: str,
    values: dict[str, tuple[str, int, dict[str, Any]]],
) -> list[AnalyticsAggregate]:
    return [
        AnalyticsAggregate(kind=kind, key=key, label=label, count=count, payload=payload)
        for key, (label, count, payload) in sorted(
            values.items(),
            key=lambda item: (-item[1][1], item[0]),
        )
    ]


def _earliest_worker_started_at(summary: dict[str, Any]) -> datetime | None:
    started_values = [
        _parse_datetime(item.get("started_at"))
        for item in summary.get("worker_summaries", [])
        if isinstance(item, dict)
    ]
    valid_values = [value for value in started_values if value is not None]
    return min(valid_values) if valid_values else None


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def _default_run_name(summary_path: Path) -> str:
    return summary_path.parent.name


def main() -> int:
    parser = argparse.ArgumentParser(description="Import batch lead analytics into PostgreSQL.")
    parser.add_argument("--summary", required=True, type=Path, help="Batch summary JSON path")
    parser.add_argument("--lead-candidates", required=True, type=Path, help="Lead candidates JSONL path")
    parser.add_argument("--name", default=None, help="Stable analytics run name")
    args = parser.parse_args()
    imported = asyncio.run(
        import_analytics_run(
            summary_path=args.summary,
            lead_candidates_path=args.lead_candidates,
            name=args.name,
        )
    )
    print(
        json.dumps(
            {
                "id": str(imported.id),
                "name": imported.name,
                "processed": imported.processed,
                "leads": imported.leads,
                "candidate_rate": imported.candidate_rate,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
