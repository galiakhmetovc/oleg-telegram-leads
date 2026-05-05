"""Build reviewable interest-context draft knowledge without LLM calls."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
from sqlalchemy import desc, insert, select, update
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.models.interest_context_drafts import (
    interest_context_draft_items_table,
    interest_context_draft_runs_table,
)
from pur_leads.models.telegram_sources import (
    monitored_sources_table,
    telegram_raw_export_runs_table,
)
from pur_leads.services.telegram_aggregated_stats import TelegramAggregatedStatsService
from pur_leads.services.telegram_entity_extraction import TelegramEntityExtractionService
from pur_leads.services.telegram_entity_ranking import TelegramEntityRankingService
from pur_leads.services.telegram_feature_enrichment import TelegramFeatureEnrichmentService

BUILD_INTEREST_CONTEXT_DRAFT_JOB = "build_interest_context_draft"
DRAFT_ALGORITHM_VERSION = "interest-draft-rule-based-v1"

ProgressCallback = Callable[[dict[str, Any]], None]

STAGES: tuple[dict[str, str], ...] = (
    {"key": "feature_enrichment", "label": "Признаки сообщений"},
    {"key": "aggregated_stats", "label": "Агрегаты"},
    {"key": "entity_extraction", "label": "Кандидаты сущностей"},
    {"key": "entity_ranking", "label": "Очистка и ранжирование"},
    {"key": "draft_assembly", "label": "Черновик ядра"},
)


@dataclass(frozen=True)
class InterestContextDraftBuildResult:
    context_id: str
    draft_run_id: str
    raw_export_run_count: int
    total_steps: int
    completed_steps: int
    candidate_count: int
    stage_results: list[dict[str, Any]]

    def as_jsonable(self) -> dict[str, Any]:
        return {
            "context_id": self.context_id,
            "draft_run_id": self.draft_run_id,
            "raw_export_run_count": self.raw_export_run_count,
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "candidate_count": self.candidate_count,
            "stage_results": self.stage_results,
            "algorithm_version": DRAFT_ALGORITHM_VERSION,
        }


class InterestContextDraftService:
    """Build a deterministic, auditable draft of an interest core."""

    def __init__(
        self,
        session: Session,
        *,
        processed_root: Path | str = "./data/processed",
        enriched_root: Path | str = "./data/enriched",
    ) -> None:
        self.session = session
        self.processed_root = Path(processed_root)
        self.enriched_root = Path(enriched_root)

    def build(
        self,
        context_id: str,
        *,
        actor: str,
        max_items: int = 120,
        progress: ProgressCallback | None = None,
    ) -> InterestContextDraftBuildResult:
        raw_runs = self._raw_export_runs(context_id)
        if not raw_runs:
            raise ValueError("Нет успешных raw-выгрузок для сборки черновика")
        total_steps = (len(STAGES) - 1) * len(raw_runs) + 1
        completed_steps = 0
        stage_results: list[dict[str, Any]] = []
        started_at = utc_now()
        draft_run_id = self._create_run(
            context_id,
            actor=actor,
            started_at=started_at,
            raw_runs=raw_runs,
        )

        self._report(
            progress,
            status="running",
            draft_run_id=draft_run_id,
            started_at=started_at.isoformat(),
            updated_at=started_at.isoformat(),
            current_stage=None,
            current_stage_label="Ожидание этапа",
            stage_index=0,
            stage_count=len(STAGES),
            stage_percent=0,
            overall_percent=0,
            completed_steps=0,
            total_steps=total_steps,
            raw_export_run_count=len(raw_runs),
            candidate_count=0,
            stage_results=stage_results,
            message="Сборка черновика началась без LLM",
        )

        try:
            for stage_index, stage in enumerate(STAGES[:-1], start=1):
                stage_completed_runs = 0
                for run_index, run in enumerate(raw_runs, start=1):
                    self._report_stage_start(
                        progress,
                        draft_run_id=draft_run_id,
                        started_at=started_at,
                        stage=stage,
                        stage_index=stage_index,
                        completed_steps=completed_steps,
                        total_steps=total_steps,
                        raw_runs=raw_runs,
                        run=run,
                        run_index=run_index,
                        stage_completed_runs=stage_completed_runs,
                        stage_results=stage_results,
                    )
                    result = self._run_stage(stage["key"], str(run["id"]))
                    stage_results.append(
                        {
                            "stage": stage["key"],
                            "stage_label": stage["label"],
                            "raw_export_run_id": run["id"],
                            "metrics": result,
                        }
                    )
                    completed_steps += 1
                    stage_completed_runs += 1
                    self._report_stage_done(
                        progress,
                        draft_run_id=draft_run_id,
                        started_at=started_at,
                        stage=stage,
                        stage_index=stage_index,
                        completed_steps=completed_steps,
                        total_steps=total_steps,
                        raw_runs=raw_runs,
                        run=run,
                        run_index=run_index,
                        stage_completed_runs=stage_completed_runs,
                        stage_results=stage_results,
                    )

            assembly_stage = STAGES[-1]
            self._report(
                progress,
                status="running",
                draft_run_id=draft_run_id,
                started_at=started_at.isoformat(),
                updated_at=utc_now().isoformat(),
                current_stage=assembly_stage["key"],
                current_stage_label=assembly_stage["label"],
                stage_index=len(STAGES),
                stage_count=len(STAGES),
                stage_percent=0,
                overall_percent=_percent(completed_steps, total_steps),
                completed_steps=completed_steps,
                total_steps=total_steps,
                raw_export_run_count=len(raw_runs),
                candidate_count=0,
                stage_results=stage_results,
                message="Собираю проверяемые карточки ядра интересов",
            )
            refreshed_raw_runs = self._raw_export_runs(context_id)
            items = self._assemble_items(
                context_id,
                draft_run_id,
                refreshed_raw_runs,
                max_items=max_items,
            )
            completed_steps += 1
            assembly_result = {
                "draft_run_id": draft_run_id,
                "candidate_count": len(items),
                "max_items": max_items,
                "algorithm_version": DRAFT_ALGORITHM_VERSION,
                "uses_llm": False,
            }
            stage_results.append(
                {
                    "stage": assembly_stage["key"],
                    "stage_label": assembly_stage["label"],
                    "raw_export_run_id": None,
                    "metrics": assembly_result,
                }
            )
            finished_at = utc_now()
            output_summary = {
                "candidate_count": len(items),
                "status_counts": _count_by(items, "status"),
                "confidence_counts": _count_by(items, "confidence"),
                "item_type_counts": _count_by(items, "item_type"),
                "algorithm_version": DRAFT_ALGORITHM_VERSION,
                "uses_llm": False,
            }
            self._finish_run(
                draft_run_id,
                status="succeeded",
                finished_at=finished_at,
                output_summary=output_summary,
            )
            result = InterestContextDraftBuildResult(
                context_id=context_id,
                draft_run_id=draft_run_id,
                raw_export_run_count=len(raw_runs),
                total_steps=total_steps,
                completed_steps=completed_steps,
                candidate_count=len(items),
                stage_results=stage_results,
            )
            self._report(
                progress,
                status="succeeded",
                draft_run_id=draft_run_id,
                started_at=started_at.isoformat(),
                updated_at=finished_at.isoformat(),
                finished_at=finished_at.isoformat(),
                current_stage="done",
                current_stage_label="Готово",
                stage_index=len(STAGES),
                stage_count=len(STAGES),
                stage_percent=100,
                overall_percent=100,
                completed_steps=completed_steps,
                total_steps=total_steps,
                raw_export_run_count=len(raw_runs),
                candidate_count=len(items),
                stage_results=stage_results,
                message=f"Черновик собран: {len(items)} кандидатов",
            )
            return result
        except Exception:
            self._finish_run(
                draft_run_id, status="failed", finished_at=utc_now(), output_summary=None
            )
            raise

    def latest_payload(self, context_id: str, *, limit: int = 120) -> dict[str, Any]:
        run = self._latest_run(context_id)
        if run is None:
            return {"draft_run": None, "items": [], "summary": None}
        items = self._items_for_run(str(run["id"]), limit=limit)
        return {
            "draft_run": dict(run),
            "items": items,
            "summary": run.get("output_summary_json"),
        }

    def _raw_export_runs(self, context_id: str) -> list[dict[str, Any]]:
        rows = (
            self.session.execute(
                select(telegram_raw_export_runs_table)
                .select_from(
                    telegram_raw_export_runs_table.join(
                        monitored_sources_table,
                        telegram_raw_export_runs_table.c.monitored_source_id
                        == monitored_sources_table.c.id,
                    )
                )
                .where(monitored_sources_table.c.interest_context_id == context_id)
                .where(telegram_raw_export_runs_table.c.status == "succeeded")
                .order_by(desc(telegram_raw_export_runs_table.c.started_at))
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    def _run_stage(self, stage: str, raw_export_run_id: str) -> dict[str, Any]:
        if stage == "feature_enrichment":
            result = TelegramFeatureEnrichmentService(
                self.session,
                processed_root=self.processed_root,
            ).write_features(raw_export_run_id)
            return {
                "features_parquet_path": str(result.features_parquet_path),
                "summary_path": str(result.summary_path),
                **result.metrics,
            }
        if stage == "aggregated_stats":
            result = TelegramAggregatedStatsService(
                self.session,
                enriched_root=self.enriched_root,
            ).write_stats(raw_export_run_id)
            return {
                "summary_path": str(result.summary_path),
                "ngrams_path": str(result.ngrams_path),
                "entity_candidates_path": str(result.entity_candidates_path),
                "url_summary_path": str(result.url_summary_path),
                **result.metrics,
            }
        if stage == "entity_extraction":
            result = TelegramEntityExtractionService(
                self.session,
                enriched_root=self.enriched_root,
            ).write_entities(raw_export_run_id)
            return {
                "entities_parquet_path": str(result.entities_parquet_path),
                "entity_groups_path": str(result.entity_groups_path),
                "summary_path": str(result.summary_path),
                **result.metrics,
            }
        if stage == "entity_ranking":
            result = TelegramEntityRankingService(
                self.session,
                enriched_root=self.enriched_root,
            ).write_rankings(raw_export_run_id)
            return {
                "ranked_entities_parquet_path": str(result.ranked_entities_parquet_path),
                "ranked_entities_json_path": str(result.ranked_entities_json_path),
                "summary_path": str(result.summary_path),
                **result.metrics,
            }
        raise ValueError(f"unsupported draft stage: {stage}")

    def _assemble_items(
        self,
        context_id: str,
        draft_run_id: str,
        raw_runs: list[dict[str, Any]],
        *,
        max_items: int,
    ) -> list[dict[str, Any]]:
        buckets: dict[str, dict[str, Any]] = {}
        for run in raw_runs:
            ranking_path = _ranking_path_from_run(run)
            if ranking_path is None or not ranking_path.exists():
                continue
            rows = pq.read_table(ranking_path).to_pylist()
            for row in rows:
                status = str(row.get("ranking_status") or "")
                if status not in {"promote_candidate", "review_candidate"}:
                    continue
                normalized_key = str(row.get("normalized_text") or "").strip()
                if not normalized_key:
                    continue
                bucket = buckets.setdefault(
                    normalized_key,
                    {
                        "normalized_key": normalized_key,
                        "title": str(row.get("canonical_text") or normalized_key),
                        "score": 0.0,
                        "mention_count": 0,
                        "source_refs": set(),
                        "examples": [],
                        "reasons": set(),
                        "penalties": set(),
                        "pos_patterns": set(),
                        "ranking_statuses": set(),
                    },
                )
                score = float(row.get("score") or 0.0)
                if score > float(bucket["score"]):
                    bucket["score"] = score
                    bucket["title"] = str(row.get("canonical_text") or normalized_key)
                bucket["mention_count"] += int(row.get("mention_count") or 0)
                bucket["source_refs"].update(_json_list(row.get("source_refs_json")))
                bucket["examples"].extend(_json_list(row.get("example_contexts_json"))[:3])
                bucket["reasons"].update(_json_list(row.get("reasons_json")))
                bucket["penalties"].update(_json_list(row.get("penalties_json")))
                bucket["pos_patterns"].add(" ".join(_json_list(row.get("pos_pattern_json"))))
                bucket["ranking_statuses"].add(status)

        rows = [_item_row(context_id, draft_run_id, bucket) for bucket in buckets.values()]
        rows.sort(
            key=lambda item: (
                -float(item["score"]),
                -int((item["metadata_json"] or {}).get("mention_count") or 0),
                str(item["normalized_key"]),
            )
        )
        rows = rows[: max(1, max_items)]
        now = utc_now()
        for row in rows:
            row["created_at"] = now
            row["updated_at"] = now
        if rows:
            self.session.execute(insert(interest_context_draft_items_table), rows)
            self.session.commit()
        return rows

    def _create_run(
        self,
        context_id: str,
        *,
        actor: str,
        started_at: Any,
        raw_runs: list[dict[str, Any]],
    ) -> str:
        draft_run_id = new_id()
        self.session.execute(
            insert(interest_context_draft_runs_table).values(
                id=draft_run_id,
                context_id=context_id,
                status="running",
                algorithm_version=DRAFT_ALGORITHM_VERSION,
                input_summary_json={
                    "raw_export_run_ids": [row["id"] for row in raw_runs],
                    "raw_export_run_count": len(raw_runs),
                    "uses_llm": False,
                },
                output_summary_json=None,
                created_by=actor,
                started_at=started_at,
                finished_at=None,
                created_at=started_at,
                updated_at=started_at,
            )
        )
        self.session.commit()
        return draft_run_id

    def _finish_run(
        self,
        draft_run_id: str,
        *,
        status: str,
        finished_at: Any,
        output_summary: dict[str, Any] | None,
    ) -> None:
        self.session.execute(
            update(interest_context_draft_runs_table)
            .where(interest_context_draft_runs_table.c.id == draft_run_id)
            .values(
                status=status,
                output_summary_json=output_summary,
                finished_at=finished_at,
                updated_at=finished_at,
            )
        )
        self.session.commit()

    def _latest_run(self, context_id: str) -> dict[str, Any] | None:
        row = (
            self.session.execute(
                select(interest_context_draft_runs_table)
                .where(interest_context_draft_runs_table.c.context_id == context_id)
                .order_by(desc(interest_context_draft_runs_table.c.created_at))
                .limit(1)
            )
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None

    def _items_for_run(self, draft_run_id: str, *, limit: int) -> list[dict[str, Any]]:
        rows = (
            self.session.execute(
                select(interest_context_draft_items_table)
                .where(interest_context_draft_items_table.c.draft_run_id == draft_run_id)
                .order_by(desc(interest_context_draft_items_table.c.score))
                .limit(max(1, limit))
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    def _report_stage_start(
        self,
        progress: ProgressCallback | None,
        *,
        draft_run_id: str,
        started_at: Any,
        stage: dict[str, str],
        stage_index: int,
        completed_steps: int,
        total_steps: int,
        raw_runs: list[dict[str, Any]],
        run: dict[str, Any],
        run_index: int,
        stage_completed_runs: int,
        stage_results: list[dict[str, Any]],
    ) -> None:
        self._report(
            progress,
            status="running",
            draft_run_id=draft_run_id,
            started_at=started_at.isoformat(),
            updated_at=utc_now().isoformat(),
            current_stage=stage["key"],
            current_stage_label=stage["label"],
            stage_index=stage_index,
            stage_count=len(STAGES),
            stage_percent=_percent(stage_completed_runs, len(raw_runs)),
            overall_percent=_percent(completed_steps, total_steps),
            completed_steps=completed_steps,
            total_steps=total_steps,
            raw_export_run_count=len(raw_runs),
            current_raw_export_run_id=run["id"],
            run_index=run_index,
            run_count=len(raw_runs),
            candidate_count=0,
            stage_results=stage_results,
            message=f"{stage['label']}: запуск {run_index}/{len(raw_runs)}",
        )

    def _report_stage_done(
        self,
        progress: ProgressCallback | None,
        *,
        draft_run_id: str,
        started_at: Any,
        stage: dict[str, str],
        stage_index: int,
        completed_steps: int,
        total_steps: int,
        raw_runs: list[dict[str, Any]],
        run: dict[str, Any],
        run_index: int,
        stage_completed_runs: int,
        stage_results: list[dict[str, Any]],
    ) -> None:
        self._report(
            progress,
            status="running",
            draft_run_id=draft_run_id,
            started_at=started_at.isoformat(),
            updated_at=utc_now().isoformat(),
            current_stage=stage["key"],
            current_stage_label=stage["label"],
            stage_index=stage_index,
            stage_count=len(STAGES),
            stage_percent=_percent(stage_completed_runs, len(raw_runs)),
            overall_percent=_percent(completed_steps, total_steps),
            completed_steps=completed_steps,
            total_steps=total_steps,
            raw_export_run_count=len(raw_runs),
            current_raw_export_run_id=run["id"],
            run_index=run_index,
            run_count=len(raw_runs),
            candidate_count=0,
            stage_results=stage_results,
            message=f"{stage['label']}: готово {stage_completed_runs}/{len(raw_runs)}",
        )

    @staticmethod
    def _report(progress: ProgressCallback | None, **payload: Any) -> None:
        if progress is not None:
            progress({"kind": "interest_context_draft_build", **payload})


def _item_row(context_id: str, draft_run_id: str, bucket: dict[str, Any]) -> dict[str, Any]:
    source_refs = sorted(str(item) for item in bucket["source_refs"] if item)
    examples = _unique_limited(str(item) for item in bucket["examples"] if item)
    score = round(float(bucket["score"] or 0.0), 6)
    normalized_key = str(bucket["normalized_key"])
    item_type = "theme" if " " in normalized_key else "term"
    return {
        "id": new_id(),
        "draft_run_id": draft_run_id,
        "context_id": context_id,
        "item_type": item_type,
        "title": str(bucket["title"])[:300],
        "normalized_key": normalized_key[:300],
        "description": (
            f"Найдено {int(bucket['mention_count'])} упоминаний; источников: {len(source_refs)}."
        ),
        "score": score,
        "confidence": _confidence(score),
        "status": "pending_review",
        "evidence_count": int(bucket["mention_count"]),
        "source_message_count": len(source_refs),
        "metadata_json": {
            "mention_count": int(bucket["mention_count"]),
            "ranking_statuses": sorted(bucket["ranking_statuses"]),
            "reasons": sorted(bucket["reasons"]),
            "penalties": sorted(bucket["penalties"]),
            "pos_patterns": sorted(pattern for pattern in bucket["pos_patterns"] if pattern),
            "algorithm_version": DRAFT_ALGORITHM_VERSION,
            "uses_llm": False,
        },
        "evidence_json": [
            {"source_ref": source_ref, "example": examples[index] if index < len(examples) else ""}
            for index, source_ref in enumerate(source_refs[:5])
        ],
    }


def _ranking_path_from_run(run: dict[str, Any]) -> Path | None:
    metadata = dict(run.get("metadata_json") or {})
    ranking = metadata.get("entity_ranking")
    if not isinstance(ranking, dict):
        return None
    path_value = ranking.get("ranked_entities_parquet_path")
    if not path_value:
        return None
    path = Path(str(path_value))
    return path if path.is_absolute() else Path(".") / path


def _json_list(value: Any) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _unique_limited(values: Any, *, limit: int = 5) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = " ".join(str(raw).split())
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value[:500])
        if len(result) >= limit:
            break
    return result


def _confidence(score: float) -> str:
    if score >= 0.65:
        return "high"
    if score >= 0.35:
        return "medium"
    return "low"


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _percent(done: int, total: int) -> int:
    if total <= 0:
        return 100
    return max(0, min(100, round((done / total) * 100)))
