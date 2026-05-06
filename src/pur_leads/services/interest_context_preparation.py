"""Manual data preparation for an interest context."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.models.telegram_sources import (
    monitored_sources_table,
    telegram_raw_export_runs_table,
)
from pur_leads.services.telegram_artifact_texts import TelegramArtifactTextExtractionService
from pur_leads.services.telegram_aggregated_stats import TelegramAggregatedStatsService
from pur_leads.services.telegram_chroma_index import TelegramChromaIndexService
from pur_leads.services.telegram_entity_extraction import TelegramEntityExtractionService
from pur_leads.services.telegram_entity_ranking import TelegramEntityRankingService
from pur_leads.services.telegram_feature_enrichment import TelegramFeatureEnrichmentService
from pur_leads.services.telegram_fts_index import TelegramFtsIndexService
from pur_leads.services.telegram_text_normalization import TelegramTextNormalizationService

PREPARE_INTEREST_CONTEXT_DATA_JOB = "prepare_interest_context_data"
DEFAULT_PREPARE_EMBEDDING_PROFILE = "local_hashing_v1"

ProgressCallback = Callable[[dict[str, Any]], None]

STAGES: tuple[dict[str, str], ...] = (
    {"key": "text_normalization", "label": "Нормализация текста"},
    {"key": "artifact_text_extraction", "label": "Тексты вложений"},
    {"key": "fts_index", "label": "Полнотекстовый индекс"},
    {"key": "chroma_index", "label": "Семантический индекс"},
    {"key": "feature_enrichment", "label": "Признаки сообщений"},
    {"key": "aggregated_stats", "label": "Агрегаты"},
    {"key": "entity_extraction", "label": "Кандидаты сущностей"},
    {"key": "entity_ranking", "label": "Очистка и ранжирование"},
)


@dataclass(frozen=True)
class InterestContextPreparationResult:
    context_id: str
    raw_export_run_count: int
    total_steps: int
    completed_steps: int
    stage_results: list[dict[str, Any]]

    def as_jsonable(self) -> dict[str, Any]:
        return {
            "context_id": self.context_id,
            "raw_export_run_count": self.raw_export_run_count,
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "stage_results": self.stage_results,
        }


class InterestContextPreparationService:
    def __init__(
        self,
        session: Session,
        *,
        processed_root: Path | str = "./data/processed",
        enriched_root: Path | str = "./data/enriched",
        search_root: Path | str = "./data/search",
        chroma_root: Path | str = "./data/chroma",
    ) -> None:
        self.session = session
        self.processed_root = Path(processed_root)
        self.enriched_root = Path(enriched_root)
        self.search_root = Path(search_root)
        self.chroma_root = Path(chroma_root)

    def prepare(
        self,
        context_id: str,
        *,
        embedding_profile: str = DEFAULT_PREPARE_EMBEDDING_PROFILE,
        progress: ProgressCallback | None = None,
    ) -> InterestContextPreparationResult:
        raw_runs = self._raw_export_runs(context_id)
        if not raw_runs:
            raise ValueError("Нет успешных raw-выгрузок для подготовки данных")

        total_steps = len(STAGES) * len(raw_runs)
        completed_steps = 0
        stage_results: list[dict[str, Any]] = []
        started_at = utc_now().isoformat()

        self._report(
            progress,
            status="running",
            started_at=started_at,
            updated_at=started_at,
            current_stage=None,
            current_stage_label="Ожидание этапа",
            stage_index=0,
            stage_count=len(STAGES),
            stage_percent=0,
            overall_percent=0,
            completed_steps=0,
            total_steps=total_steps,
            raw_export_run_count=len(raw_runs),
            stage_results=stage_results,
            message="Подготовка данных началась",
        )

        for stage_index, stage in enumerate(STAGES, start=1):
            stage_completed_runs = 0
            for run_index, run in enumerate(raw_runs, start=1):
                self._report(
                    progress,
                    status="running",
                    started_at=started_at,
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
                    stage_results=stage_results,
                    message=f"{stage['label']}: запуск {run_index}/{len(raw_runs)}",
                )
                result = self._run_stage(
                    stage["key"],
                    str(run["id"]),
                    embedding_profile=embedding_profile,
                )
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
                self._report(
                    progress,
                    status="running",
                    started_at=started_at,
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
                    stage_results=stage_results,
                    message=f"{stage['label']}: готово {stage_completed_runs}/{len(raw_runs)}",
                )

        finished_at = utc_now().isoformat()
        final = InterestContextPreparationResult(
            context_id=context_id,
            raw_export_run_count=len(raw_runs),
            total_steps=total_steps,
            completed_steps=completed_steps,
            stage_results=stage_results,
        )
        self._report(
            progress,
            status="succeeded",
            started_at=started_at,
            updated_at=finished_at,
            finished_at=finished_at,
            current_stage="done",
            current_stage_label="Готово",
            stage_index=len(STAGES),
            stage_count=len(STAGES),
            stage_percent=100,
            overall_percent=100,
            completed_steps=completed_steps,
            total_steps=total_steps,
            raw_export_run_count=len(raw_runs),
            stage_results=stage_results,
            message="Данные подготовлены для поиска и анализа",
        )
        return final

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

    def _run_stage(
        self,
        stage: str,
        raw_export_run_id: str,
        *,
        embedding_profile: str,
    ) -> dict[str, Any]:
        if stage == "text_normalization":
            result = TelegramTextNormalizationService(
                self.session,
                processed_root=self.processed_root,
            ).write_texts(raw_export_run_id)
            return {
                "texts_parquet_path": str(result.texts_parquet_path),
                "summary_path": str(result.summary_path),
                **result.metrics,
            }
        if stage == "artifact_text_extraction":
            result = TelegramArtifactTextExtractionService(
                self.session,
                processed_root=self.processed_root,
                fetch_external_pages=True,
                parse_documents=True,
                external_fetch_timeout_seconds=600.0,
                document_parse_timeout_seconds=600.0,
            ).write_texts(raw_export_run_id)
            return {
                "artifact_texts_parquet_path": str(result.texts_parquet_path),
                "summary_path": str(result.summary_path),
                **result.metrics,
            }
        if stage == "fts_index":
            result = TelegramFtsIndexService(
                self.session,
                search_root=self.search_root,
            ).write_index(raw_export_run_id)
            return {
                "search_table_name": result.search_table_name,
                "summary_path": str(result.summary_path),
                **result.metrics,
            }
        if stage == "chroma_index":
            result = TelegramChromaIndexService(
                self.session,
                chroma_root=self.chroma_root,
            ).write_index(
                raw_export_run_id,
                embedding_profile=embedding_profile,
            )
            return {
                "chroma_path": str(result.chroma_path),
                "collection_name": result.collection_name,
                "summary_path": str(result.summary_path),
                **result.metrics,
            }
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
                "source_quality_path": str(result.source_quality_path),
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
        raise ValueError(f"unsupported preparation stage: {stage}")

    @staticmethod
    def _report(progress: ProgressCallback | None, **payload: Any) -> None:
        if progress is not None:
            progress(
                {
                    "kind": "interest_context_data_preparation",
                    **payload,
                }
            )


def _percent(value: int, total: int) -> int:
    if total <= 0:
        return 0
    return max(0, min(100, round(value * 100 / total)))
