"""Configurable intent layers over broad interest-core matches."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Any

import pyarrow.parquet as pq
from sqlalchemy import desc, func, insert, select, update
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.models.interest_context_drafts import (
    interest_core_analysis_matches_table,
    interest_core_analysis_runs_table,
    interest_intent_analysis_matches_table,
    interest_intent_analysis_runs_table,
    interest_intent_layers_table,
)
from pur_leads.models.telegram_sources import (
    monitored_sources_table,
    source_messages_table,
    telegram_raw_export_runs_table,
)
from pur_leads.services.audit import AuditService


DEFAULT_INTENT_INCLUDE_PATTERNS = [
    "ищу",
    "ищем",
    "нужен",
    "нужна",
    "нужно",
    "нужны",
    "подскажите",
    "посоветуйте",
    "помогите",
    "где купить",
    "где заказать",
    "где найти",
    "купить",
    "заказать",
    "поставить",
    "установить",
    "подключить",
    "смонтировать",
    "сделать",
    "стоимость",
    "цена",
    "сколько стоит",
    "бюджет",
    "смета",
    "кто может",
    "кто делает",
    "кто занимается",
    "хочу",
    "планирую",
    "интересует",
    "что нужно предусмотреть",
]

DEFAULT_INTENT_EXCLUDE_PATTERNS = [
    "вакансия",
    "вакансии",
    "резюме",
    "в команду",
    "требуется дизайнер",
    "требуется архитектор",
    "требуется визуализатор",
    "требуется комплектатор",
    "ищу дизайнера",
    "ищу архитектора",
    "продам",
    "продаю",
    "отдам",
    "аренда рабочего места",
]

DEFAULT_CONTEXT_PATTERNS = [
    "видеонаблюдение",
    "камера",
    "видеокамера",
    "умный дом",
    "home assistant",
    "алиса",
    "розетка",
    "выключатель",
    "диммер",
    "реле",
    "щит",
    "автомат",
    "эл вывод",
    "электрика",
    "проводка",
    "датчик",
    "протечка",
    "термостат",
    "климат",
    "отопление",
    "подсветка",
    "освещение",
    "светильник",
    "трек",
    "домофон",
    "контроль доступа",
    "замок",
    "сигнализация",
    "охрана",
    "штора",
    "карниз",
    "жалюзи",
    "ворота",
    "роллета",
]

DEFAULT_INTENT_EXCLUDED_CORE_NAMES = [
    "консультирование",
    "клиенты",
    "комплексное проектирование",
    "детали_проекта",
    "заявки на услуги",
    "проектирование",
    "смета",
    "стоимость услуг",
    "сроки_реализации",
    "затраты",
]


@dataclass(frozen=True)
class InterestIntentLayerRecord:
    id: str
    context_id: str
    name: str
    description: str | None
    status: str
    include_patterns_json: Any
    context_patterns_json: Any
    exclude_patterns_json: Any
    include_categories_json: Any
    exclude_categories_json: Any
    include_core_names_json: Any
    exclude_core_names_json: Any
    require_include_match: bool
    require_context_match: bool
    min_score: float
    max_results: int
    broad_score_weight: float
    intent_hit_weight: float
    metadata_json: Any
    created_by: str
    created_at: Any
    updated_at: Any

    def as_jsonable(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InterestIntentRunRecord:
    id: str
    context_id: str
    intent_layer_id: str
    broad_analysis_run_id: str
    status: str
    source_title: str | None
    source_message_count: int
    broad_match_count: int
    matched_message_count: int
    match_count: int
    summary_json: Any
    created_by: str
    started_at: Any
    finished_at: Any
    created_at: Any
    updated_at: Any

    def as_jsonable(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InterestIntentMatchRecord:
    id: str
    run_id: str
    context_id: str
    intent_layer_id: str
    source_message_id: str
    interest_core_match_id: str
    interest_core_item_id: str
    telegram_message_id: int
    message_date: Any
    sender_id: str | None
    message_text: str | None
    canonical_name: str | None
    category: str | None
    matched_text: str | None
    match_kind: str
    score: float
    broad_score: float
    evidence_json: Any
    created_at: Any
    message_url: str | None = None

    def as_jsonable(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _PreparedMessageText:
    raw_text: str
    clean_text: str
    lemmas_text: str
    source: str

    @property
    def search_text(self) -> str:
        return " ".join(
            part
            for part in (self.raw_text, self.clean_text, self.lemmas_text)
            if part.strip()
        )


class InterestIntentLayerService:
    """Manage and execute configurable intent layers."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.audit = AuditService(session)

    def ensure_default_layer(self, context_id: str, *, actor: str) -> InterestIntentLayerRecord:
        existing = (
            self.session.execute(
                select(interest_intent_layers_table)
                .where(interest_intent_layers_table.c.context_id == context_id)
                .where(interest_intent_layers_table.c.status != "archived")
                .order_by(desc(interest_intent_layers_table.c.created_at))
                .limit(1)
            )
            .mappings()
            .first()
        )
        if existing is not None:
            return _layer_record(existing)
        return self.create_layer(
            context_id=context_id,
            name="Намерение: запрос помощи, покупки или заказа",
            description=(
                "Второй слой поверх широкого совпадения по ядру. Ищет явное намерение: "
                "нужно, ищу, подскажите, где заказать, сколько стоит, кто может сделать."
            ),
            actor=actor,
            include_patterns=DEFAULT_INTENT_INCLUDE_PATTERNS,
            context_patterns=DEFAULT_CONTEXT_PATTERNS,
            exclude_patterns=DEFAULT_INTENT_EXCLUDE_PATTERNS,
            exclude_core_names=DEFAULT_INTENT_EXCLUDED_CORE_NAMES,
            require_context_match=False,
            min_score=0.55,
            max_results=3000,
        )

    def list_layers(self, context_id: str, *, actor: str | None = None) -> dict[str, Any]:
        if actor:
            self.ensure_default_layer(context_id, actor=actor)
        rows = (
            self.session.execute(
                select(interest_intent_layers_table)
                .where(interest_intent_layers_table.c.context_id == context_id)
                .where(interest_intent_layers_table.c.status != "archived")
                .order_by(desc(interest_intent_layers_table.c.created_at))
            )
            .mappings()
            .all()
        )
        return {"items": [_layer_record(row).as_jsonable() for row in rows]}

    def create_layer(
        self,
        *,
        context_id: str,
        name: str,
        actor: str,
        description: str | None = None,
        include_patterns: list[str] | None = None,
        context_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
        include_categories: list[str] | None = None,
        exclude_categories: list[str] | None = None,
        include_core_names: list[str] | None = None,
        exclude_core_names: list[str] | None = None,
        require_include_match: bool = True,
        require_context_match: bool = False,
        min_score: float = 0.55,
        max_results: int = 3000,
        broad_score_weight: float = 0.45,
        intent_hit_weight: float = 0.18,
        metadata_json: Any = None,
    ) -> InterestIntentLayerRecord:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Название слоя намерений обязательно")
        now = utc_now()
        layer_id = new_id()
        self.session.execute(
            insert(interest_intent_layers_table).values(
                id=layer_id,
                context_id=context_id,
                name=clean_name[:200],
                description=description.strip() if description and description.strip() else None,
                status="active",
                include_patterns_json=_clean_list(include_patterns),
                context_patterns_json=_clean_list(context_patterns),
                exclude_patterns_json=_clean_list(exclude_patterns),
                include_categories_json=_clean_list(include_categories),
                exclude_categories_json=_clean_list(exclude_categories),
                include_core_names_json=_clean_list(include_core_names),
                exclude_core_names_json=_clean_list(exclude_core_names),
                require_include_match=bool(require_include_match),
                require_context_match=bool(require_context_match),
                min_score=max(0.0, min(1.0, float(min_score))),
                max_results=max(1, min(20000, int(max_results))),
                broad_score_weight=max(0.0, min(1.0, float(broad_score_weight))),
                intent_hit_weight=max(0.0, min(1.0, float(intent_hit_weight))),
                metadata_json=metadata_json,
                created_by=actor,
                created_at=now,
                updated_at=now,
            )
        )
        self.session.commit()
        self.audit.record_change(
            actor=actor,
            action="interest_intent_layer.create",
            entity_type="interest_context",
            entity_id=context_id,
            old_value_json=None,
            new_value_json={"layer_id": layer_id, "name": clean_name},
        )
        return self._layer(layer_id)

    def update_layer(
        self,
        layer_id: str,
        *,
        context_id: str,
        actor: str,
        values: dict[str, Any],
    ) -> InterestIntentLayerRecord:
        layer = self._layer(layer_id)
        if layer.context_id != context_id:
            raise KeyError(layer_id)
        patch: dict[str, Any] = {}
        if "name" in values:
            name = str(values["name"] or "").strip()
            if not name:
                raise ValueError("Название слоя намерений обязательно")
            patch["name"] = name[:200]
        if "description" in values:
            description = str(values["description"] or "").strip()
            patch["description"] = description or None
        for field in (
            "include_patterns",
            "context_patterns",
            "exclude_patterns",
            "include_categories",
            "exclude_categories",
            "include_core_names",
            "exclude_core_names",
        ):
            if field in values:
                patch[f"{field}_json"] = _clean_list(values[field])
        if "require_include_match" in values:
            patch["require_include_match"] = bool(values["require_include_match"])
        if "require_context_match" in values:
            patch["require_context_match"] = bool(values["require_context_match"])
        for field in ("min_score", "broad_score_weight", "intent_hit_weight"):
            if field in values:
                patch[field] = max(0.0, min(1.0, float(values[field])))
        if "max_results" in values:
            patch["max_results"] = max(1, min(20000, int(values["max_results"])))
        if "status" in values:
            status = str(values["status"] or "active")
            if status not in {"active", "disabled", "archived"}:
                raise ValueError("Некорректный статус слоя намерений")
            patch["status"] = status
        if not patch:
            return layer
        patch["updated_at"] = utc_now()
        self.session.execute(
            update(interest_intent_layers_table)
            .where(interest_intent_layers_table.c.id == layer_id)
            .values(**patch)
        )
        self.session.commit()
        self.audit.record_change(
            actor=actor,
            action="interest_intent_layer.update",
            entity_type="interest_context",
            entity_id=context_id,
            old_value_json=layer.as_jsonable(),
            new_value_json={"layer_id": layer_id, "patch": patch},
        )
        return self._layer(layer_id)

    def archive_layer(self, layer_id: str, *, context_id: str, actor: str) -> None:
        self.update_layer(layer_id, context_id=context_id, actor=actor, values={"status": "archived"})

    def run_layer(
        self,
        *,
        context_id: str,
        layer_id: str,
        broad_analysis_run_id: str,
        actor: str,
    ) -> dict[str, Any]:
        layer = self._layer(layer_id)
        if layer.context_id != context_id:
            raise KeyError(layer_id)
        if layer.status != "active":
            raise ValueError("Слой намерений не активен")
        broad_run = self._broad_run(broad_analysis_run_id)
        if broad_run is None or broad_run["context_id"] != context_id:
            raise KeyError(broad_analysis_run_id)
        if broad_run["status"] != "succeeded":
            raise ValueError("Широкий анализ еще не завершен")

        now = utc_now()
        run_id = new_id()
        source_title = f"{broad_run['source_title'] or broad_analysis_run_id} / {layer.name}"
        self.session.execute(
            insert(interest_intent_analysis_runs_table).values(
                id=run_id,
                context_id=context_id,
                intent_layer_id=layer_id,
                broad_analysis_run_id=broad_analysis_run_id,
                status="running",
                source_title=source_title[:255],
                source_message_count=int(broad_run["message_count"] or 0),
                broad_match_count=int(broad_run["match_count"] or 0),
                matched_message_count=0,
                match_count=0,
                summary_json=None,
                created_by=actor,
                started_at=now,
                finished_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        self.session.commit()
        try:
            match_rows = self._build_intent_matches(
                run_id=run_id,
                context_id=context_id,
                layer=layer,
                broad_run=broad_run,
                created_at=now,
            )
            if match_rows:
                self.session.execute(insert(interest_intent_analysis_matches_table), match_rows)
            summary = _intent_summary(match_rows, layer)
            finished_at = utc_now()
            self.session.execute(
                update(interest_intent_analysis_runs_table)
                .where(interest_intent_analysis_runs_table.c.id == run_id)
                .values(
                    status="succeeded",
                    matched_message_count=summary["matched_message_count"],
                    match_count=len(match_rows),
                    summary_json=summary,
                    finished_at=finished_at,
                    updated_at=finished_at,
                )
            )
            self.session.commit()
        except Exception as exc:
            failed_at = utc_now()
            self.session.execute(
                update(interest_intent_analysis_runs_table)
                .where(interest_intent_analysis_runs_table.c.id == run_id)
                .values(
                    status="failed",
                    summary_json={"error": str(exc) or exc.__class__.__name__},
                    finished_at=failed_at,
                    updated_at=failed_at,
                )
            )
            self.session.commit()
            raise

        run = self._run(run_id)
        self.audit.record_change(
            actor=actor,
            action="interest_intent_layer.run",
            entity_type="interest_context",
            entity_id=context_id,
            old_value_json=None,
            new_value_json={
                "run_id": run_id,
                "intent_layer_id": layer_id,
                "broad_analysis_run_id": broad_analysis_run_id,
                "match_count": len(match_rows),
                "matched_message_count": summary["matched_message_count"],
            },
        )
        return {
            "run": run.as_jsonable() if run else None,
            "summary": summary,
            "top_matches": [
                row.as_jsonable()
                for row in self.list_matches(
                    context_id=context_id,
                    run_id=run_id,
                    limit=10,
                    offset=0,
                )["items"]
            ],
        }

    def latest_runs_payload(
        self,
        context_id: str,
        *,
        limit: int = 10,
        offset: int = 0,
    ) -> dict[str, Any]:
        safe_limit = max(1, min(100, int(limit)))
        safe_offset = max(0, int(offset))
        total = int(
            self.session.execute(
                select(func.count())
                .select_from(interest_intent_analysis_runs_table)
                .where(interest_intent_analysis_runs_table.c.context_id == context_id)
            ).scalar_one()
            or 0
        )
        rows = (
            self.session.execute(
                select(interest_intent_analysis_runs_table)
                .where(interest_intent_analysis_runs_table.c.context_id == context_id)
                .order_by(desc(interest_intent_analysis_runs_table.c.created_at))
                .limit(safe_limit)
                .offset(safe_offset)
            )
            .mappings()
            .all()
        )
        return {
            "summary": {
                "total": total,
                "page_count": len(rows),
                "latest_match_count": int(rows[0]["match_count"] or 0) if rows else 0,
                "latest_matched_message_count": int(rows[0]["matched_message_count"] or 0)
                if rows
                else 0,
            },
            "items": [_run_record(row).as_jsonable() for row in rows],
            "pagination": _pagination(limit=safe_limit, offset=safe_offset, total=total),
        }

    def list_matches(
        self,
        *,
        context_id: str,
        run_id: str,
        limit: int = 10,
        offset: int = 0,
    ) -> dict[str, Any]:
        run = self._run(run_id)
        if run is None or run.context_id != context_id:
            raise KeyError(run_id)
        safe_limit = max(1, min(100, int(limit)))
        safe_offset = max(0, int(offset))
        total = int(
            self.session.execute(
                select(func.count())
                .select_from(interest_intent_analysis_matches_table)
                .where(interest_intent_analysis_matches_table.c.context_id == context_id)
                .where(interest_intent_analysis_matches_table.c.run_id == run_id)
            ).scalar_one()
            or 0
        )
        rows = (
            self.session.execute(
                select(
                    interest_intent_analysis_matches_table,
                    source_messages_table.c.raw_metadata_json.label("_source_raw_metadata_json"),
                    monitored_sources_table.c.username.label("_source_username"),
                    monitored_sources_table.c.input_ref.label("_source_input_ref"),
                    monitored_sources_table.c.telegram_id.label("_source_telegram_id"),
                )
                .join(
                    source_messages_table,
                    source_messages_table.c.id
                    == interest_intent_analysis_matches_table.c.source_message_id,
                    isouter=True,
                )
                .join(
                    monitored_sources_table,
                    monitored_sources_table.c.id == source_messages_table.c.monitored_source_id,
                    isouter=True,
                )
                .where(interest_intent_analysis_matches_table.c.context_id == context_id)
                .where(interest_intent_analysis_matches_table.c.run_id == run_id)
                .order_by(
                    desc(interest_intent_analysis_matches_table.c.score),
                    desc(interest_intent_analysis_matches_table.c.message_date),
                )
                .limit(safe_limit)
                .offset(safe_offset)
            )
            .mappings()
            .all()
        )
        return {
            "run": run.as_jsonable(),
            "items": [_match_record(row) for row in rows],
            "pagination": _pagination(limit=safe_limit, offset=safe_offset, total=total),
        }

    def _build_intent_matches(
        self,
        *,
        run_id: str,
        context_id: str,
        layer: InterestIntentLayerRecord,
        broad_run: dict[str, Any],
        created_at: Any,
    ) -> list[dict[str, Any]]:
        config = _CompiledIntentLayer(layer)
        best_by_message: dict[str, dict[str, Any]] = {}
        rows = (
            self.session.execute(
                select(interest_core_analysis_matches_table)
                .where(interest_core_analysis_matches_table.c.context_id == context_id)
                .where(interest_core_analysis_matches_table.c.run_id == broad_run["id"])
                .order_by(desc(interest_core_analysis_matches_table.c.score))
            )
            .mappings()
            .all()
        )
        prepared_texts = self._prepared_texts_for_broad_rows(broad_run, rows)
        for row in rows:
            prepared_text = prepared_texts.get(int(row["telegram_message_id"]))
            match = config.match(row, prepared_text=prepared_text)
            if match is None:
                continue
            candidate = {
                "id": new_id(),
                "run_id": run_id,
                "context_id": context_id,
                "intent_layer_id": layer.id,
                "source_message_id": row["source_message_id"],
                "interest_core_match_id": row["id"],
                "interest_core_item_id": row["interest_core_item_id"],
                "telegram_message_id": row["telegram_message_id"],
                "message_date": row["message_date"],
                "sender_id": row["sender_id"],
                "message_text": row["message_text"],
                "canonical_name": row["canonical_name"],
                "category": row["category"],
                "matched_text": _truncate(", ".join(match["include_hits"]), 500),
                "match_kind": "intent_rule",
                "score": match["score"],
                "broad_score": float(row["score"] or 0),
                "evidence_json": {
                    "algorithm": "local_intent_layer_v1",
                    "intent_layer_id": layer.id,
                    "intent_layer_name": layer.name,
                    "broad_analysis_run_id": broad_run["id"],
                    "interest_core_match_id": row["id"],
                    "broad_score": float(row["score"] or 0),
                    "include_hits": match["include_hits"],
                    "context_hits": match["context_hits"],
                    "score_parts": match["score_parts"],
                    "prepared_text": match["prepared_text"],
                    "core_item": row["canonical_name"],
                    "category": row["category"],
                },
                "created_at": created_at,
            }
            current = best_by_message.get(str(row["source_message_id"]))
            if current is None or candidate["score"] > current["score"]:
                best_by_message[str(row["source_message_id"])] = candidate
        return sorted(best_by_message.values(), key=lambda item: item["score"], reverse=True)[
            : layer.max_results
        ]

    def _prepared_texts_for_broad_rows(
        self,
        broad_run: dict[str, Any],
        rows: list[Any],
    ) -> dict[int, _PreparedMessageText]:
        wanted_message_ids = {
            int(row["telegram_message_id"]) for row in rows if row["telegram_message_id"] is not None
        }
        if not wanted_message_ids:
            return {}
        raw_run = (
            self.session.execute(
                select(telegram_raw_export_runs_table).where(
                    telegram_raw_export_runs_table.c.id == broad_run["raw_export_run_id"]
                )
            )
            .mappings()
            .first()
        )
        if raw_run is None:
            return {}
        metadata = dict(raw_run["metadata_json"] or {})
        text_normalization = metadata.get("text_normalization")
        if not isinstance(text_normalization, dict):
            return {}
        path_value = text_normalization.get("texts_parquet_path")
        if not path_value:
            return {}
        texts_path = _resolve_path(path_value)
        if not texts_path.exists():
            return {}
        prepared: dict[int, _PreparedMessageText] = {}
        parquet_file = pq.ParquetFile(texts_path)
        for batch in parquet_file.iter_batches(batch_size=5000):
            for row in batch.to_pylist():
                telegram_message_id = row.get("telegram_message_id")
                if telegram_message_id is None:
                    continue
                message_id = int(telegram_message_id)
                if message_id not in wanted_message_ids:
                    continue
                lemmas = _json_list(row.get("lemmas_json"))
                prepared[message_id] = _PreparedMessageText(
                    raw_text=str(row.get("raw_text") or ""),
                    clean_text=str(row.get("clean_text") or ""),
                    lemmas_text=" ".join(str(lemma) for lemma in lemmas if str(lemma).strip()),
                    source="text_normalization",
                )
        return prepared

    def _layer(self, layer_id: str) -> InterestIntentLayerRecord:
        row = (
            self.session.execute(
                select(interest_intent_layers_table).where(
                    interest_intent_layers_table.c.id == layer_id
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise KeyError(layer_id)
        return _layer_record(row)

    def _run(self, run_id: str) -> InterestIntentRunRecord | None:
        row = (
            self.session.execute(
                select(interest_intent_analysis_runs_table).where(
                    interest_intent_analysis_runs_table.c.id == run_id
                )
            )
            .mappings()
            .first()
        )
        return _run_record(row) if row is not None else None

    def _broad_run(self, run_id: str) -> dict[str, Any] | None:
        row = (
            self.session.execute(
                select(interest_core_analysis_runs_table).where(
                    interest_core_analysis_runs_table.c.id == run_id
                )
            )
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None


class _CompiledIntentLayer:
    def __init__(self, layer: InterestIntentLayerRecord) -> None:
        self.layer = layer
        self.include_patterns = _compile_patterns(_json_list(layer.include_patterns_json))
        self.context_patterns = _compile_patterns(_json_list(layer.context_patterns_json))
        self.exclude_patterns = _compile_patterns(_json_list(layer.exclude_patterns_json))
        self.include_categories = _casefold_set(layer.include_categories_json)
        self.exclude_categories = _casefold_set(layer.exclude_categories_json)
        self.include_core_names = _casefold_set(layer.include_core_names_json)
        self.exclude_core_names = _casefold_set(layer.exclude_core_names_json)

    def match(
        self,
        row: Any,
        *,
        prepared_text: _PreparedMessageText | None = None,
    ) -> dict[str, Any] | None:
        raw_text = str(row["message_text"] or "")
        text = prepared_text.search_text if prepared_text is not None else raw_text
        normalized_category = _fold(row["category"])
        normalized_name = _fold(row["canonical_name"])
        if self.include_categories and normalized_category not in self.include_categories:
            return None
        if self.include_core_names and normalized_name not in self.include_core_names:
            return None
        if normalized_category in self.exclude_categories:
            return None
        if normalized_name in self.exclude_core_names:
            return None
        if _pattern_hits(self.exclude_patterns, text):
            return None
        include_hits = _pattern_hits(self.include_patterns, text)
        if self.layer.require_include_match and not include_hits:
            return None
        context_hits = _pattern_hits(self.context_patterns, text)
        if self.layer.require_context_match and not context_hits:
            return None
        broad_score = float(row["score"] or 0)
        intent_score = min(0.55, len(include_hits) * self.layer.intent_hit_weight)
        context_score = min(0.28, len(context_hits) * 0.14)
        score = min(0.99, broad_score * self.layer.broad_score_weight + intent_score + context_score)
        if score < self.layer.min_score:
            return None
        return {
            "include_hits": include_hits,
            "context_hits": context_hits,
            "score": round(score, 4),
            "score_parts": {
                "broad": round(broad_score * self.layer.broad_score_weight, 4),
                "intent": round(intent_score, 4),
                "context": round(context_score, 4),
            },
            "prepared_text": {
                "source": prepared_text.source if prepared_text is not None else "raw_message_text",
                "used_clean_text": bool(prepared_text and prepared_text.clean_text),
                "used_lemmas": bool(prepared_text and prepared_text.lemmas_text),
            },
        }


def _intent_summary(
    match_rows: list[dict[str, Any]], layer: InterestIntentLayerRecord
) -> dict[str, Any]:
    message_ids = {row["source_message_id"] for row in match_rows}
    by_category = Counter(str(row["category"] or "без категории") for row in match_rows)
    by_core_item = Counter(str(row["canonical_name"] or row["interest_core_item_id"]) for row in match_rows)
    return {
        "matched_message_count": len(message_ids),
        "match_count": len(match_rows),
        "by_category": dict(by_category.most_common(20)),
        "top_core_items": dict(by_core_item.most_common(20)),
        "algorithm": "local_intent_layer_v1",
        "intent_layer": {
            "id": layer.id,
            "name": layer.name,
            "min_score": layer.min_score,
            "max_results": layer.max_results,
        },
    }


def _clean_list(value: list[str] | None) -> list[str]:
    if not value:
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, str) and value.strip():
        stripped = value.strip()
        if stripped.startswith("["):
            try:
                loaded = json.loads(stripped)
            except json.JSONDecodeError:
                return [stripped]
            return loaded if isinstance(loaded, list) else [loaded]
        return [stripped]
    return []


def _compile_patterns(values: list[Any]) -> list[tuple[str, re.Pattern[str]]]:
    patterns: list[tuple[str, re.Pattern[str]]] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        try:
            compiled = re.compile(text, re.IGNORECASE)
        except re.error:
            compiled = re.compile(re.escape(text), re.IGNORECASE)
        patterns.append((text, compiled))
    return patterns


def _pattern_hits(patterns: list[tuple[str, re.Pattern[str]]], text: str) -> list[str]:
    hits: list[str] = []
    for source, pattern in patterns:
        if pattern.search(text):
            hits.append(source)
    return hits[:10]


def _casefold_set(value: Any) -> set[str]:
    return {_fold(item) for item in _json_list(value) if _fold(item)}


def _fold(value: Any) -> str:
    return str(value or "").casefold().replace("ё", "е").strip()


def _resolve_path(value: Any) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else Path(".") / path


def _truncate(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _layer_record(row: Any) -> InterestIntentLayerRecord:
    return InterestIntentLayerRecord(**dict(row))


def _run_record(row: Any) -> InterestIntentRunRecord:
    return InterestIntentRunRecord(**dict(row))


def _match_record(row: Any) -> InterestIntentMatchRecord:
    payload = dict(row)
    raw_metadata = payload.pop("_source_raw_metadata_json", None)
    username = payload.pop("_source_username", None)
    input_ref = payload.pop("_source_input_ref", None)
    telegram_id = payload.pop("_source_telegram_id", None)
    payload["message_url"] = _message_url(
        raw_metadata,
        username=username,
        input_ref=input_ref,
        telegram_id=telegram_id,
        telegram_message_id=payload.get("telegram_message_id"),
    )
    return InterestIntentMatchRecord(**payload)


def _message_url(
    value: Any,
    *,
    username: Any,
    input_ref: Any,
    telegram_id: Any,
    telegram_message_id: Any,
) -> str | None:
    if not isinstance(value, dict):
        value = {}
    message_url = value.get("message_url")
    if isinstance(message_url, str) and message_url.strip() and message_url != "null":
        return message_url
    if telegram_message_id is None:
        return None
    message_id = str(telegram_message_id)
    source_username = str(username or "").strip().lstrip("@") or _username_from_ref(input_ref)
    if source_username:
        return f"https://t.me/{source_username}/{message_id}"
    source_id = str(telegram_id or "").strip()
    if source_id:
        internal_id = source_id.removeprefix("-100").lstrip("-")
        if internal_id.isdigit():
            return f"https://t.me/c/{internal_id}/{message_id}"
    return None


def _username_from_ref(value: Any) -> str:
    text = str(value or "").strip()
    if "t.me/" not in text:
        return ""
    tail = text.split("t.me/", 1)[1].strip("/")
    username = tail.split("/", 1)[0].strip().lstrip("@")
    if not username or username in {"c", "joinchat", "+"} or username.startswith("+"):
        return ""
    return username


def _pagination(*, limit: int, offset: int, total: int) -> dict[str, Any]:
    return {
        "limit": limit,
        "offset": offset,
        "total": total,
        "has_more": offset + limit < total,
    }
