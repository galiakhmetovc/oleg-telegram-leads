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
from pur_leads.models.leads import feedback_events_table
from pur_leads.models.telegram_sources import (
    monitored_sources_table,
    source_messages_table,
    telegram_raw_export_runs_table,
)
from pur_leads.services.audit import AuditService
from pur_leads.services.telegram_chroma_index import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    LocalHashingEmbedder,
    TOKEN_RE,
)


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

PROJECT_OPPORTUNITY_PROFILE = "pur_designer_project_opportunity_v1"

PROJECT_OPPORTUNITY_PROJECT_TERMS = [
    "проект",
    "объект",
    "заказчик",
    "клиент",
    "квартира",
    "дом",
    "коттедж",
    "таунхаус",
    "ремонт",
    "стройка",
    "чертеж",
    "план",
    "планировка",
    "смета",
    "гардеробная",
    "детская",
    "кухня",
    "санузел",
    "ванная",
    "спальня",
]

PROJECT_OPPORTUNITY_PUR_TERMS = [
    "умный дом",
    "home assistant",
    "автоматизация",
    "сценарий",
    "алиса",
    "яндекс",
    "электрика",
    "щит",
    "автомат",
    "реле",
    "диммер",
    "слаботочка",
    "кабель",
    "провод",
    "вывод",
    "розетка",
    "выключатель",
    "датчик",
    "протечка",
    "термостат",
    "климат",
    "кондиционирование",
    "камера",
    "видеокамера",
    "видеонаблюдение",
    "домофон",
    "контроль доступа",
    "скуд",
    "замок",
    "сигнализация",
    "охрана",
    "wi-fi",
    "wifi",
    "сеть",
    "роутер",
    "интернет",
    "штора",
    "карниз",
    "жалюзи",
]

PROJECT_OPPORTUNITY_COMMERCIAL_TERMS = [
    "нужен",
    "нужна",
    "нужно",
    "нужны",
    "подскажите",
    "посоветуйте",
    "помогите",
    "подобрать",
    "предусмотреть",
    "спроектировать",
    "рассчитать",
    "смета",
    "стоимость",
    "цена",
    "сколько стоит",
    "бюджет",
    "заказать",
    "купить",
    "установить",
    "подключить",
    "смонтировать",
    "поставить",
    "кто делает",
    "кто может",
    "ищу",
    "хочет",
]

PROJECT_OPPORTUNITY_REJECT_TERMS = [
    "ниша",
    "профиль",
    "трек",
    "трековый",
    "светильник",
    "натяжной",
    "eurokraab",
    "раковина",
    "ванна",
    "унитаз",
    "плитка",
    "обои",
    "столешница",
    "камень",
    "мебель",
    "фасад",
    "archicad",
    "архикад",
    "визуализатор",
    "визуализация",
    "рендер",
    "3d",
    "видеокарта",
    "процессор",
    "системник",
    "компьютер",
    "коллаж",
    "вакансия",
    "резюме",
    "ищу дизайнера",
    "ищу архитектора",
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
    exclude_lemmas_json: Any
    exclude_phrases_json: Any
    semantic_negative_examples_json: Any
    semantic_negative_threshold: float
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
    operator_feedback_json: Any = None
    operator_review_json: Any = None

    def as_jsonable(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _PreparedMessageText:
    raw_text: str
    clean_text: str
    lemmas_text: str
    lemmas: tuple[str, ...]
    source: str

    @property
    def search_text(self) -> str:
        return " ".join(
            part
            for part in (self.raw_text, self.clean_text, self.lemmas_text)
            if part.strip()
        )


@dataclass(frozen=True)
class _LexiconTerm:
    source: str
    folded: str
    is_phrase: bool
    lemmas: tuple[str, ...]


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

    def ensure_project_opportunity_layer(
        self,
        context_id: str,
        *,
        actor: str,
    ) -> InterestIntentLayerRecord:
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
        for row in rows:
            metadata = row["metadata_json"] if isinstance(row["metadata_json"], dict) else {}
            if metadata.get("opportunity_profile") == PROJECT_OPPORTUNITY_PROFILE:
                return _layer_record(row)
        return self.create_layer(
            context_id=context_id,
            name="Проектные возможности для ПУР",
            description=(
                "Специальный слой для чата дизайнеров: ищет не обычный лид, а проект, "
                "где ПУР может помочь оборудованием, инженерией, интеграцией или консультацией."
            ),
            actor=actor,
            include_patterns=PROJECT_OPPORTUNITY_COMMERCIAL_TERMS,
            context_patterns=PROJECT_OPPORTUNITY_PUR_TERMS,
            exclude_patterns=[],
            exclude_lemmas=[],
            exclude_phrases=[],
            semantic_negative_examples=[
                "Нужно определить размер ниши для подсветки декоративной скалы.",
                "Подскажите профиль для натяжного потолка или декоративной подсветки.",
                "Ищу 3D визуализатора, видеокарту или системник для Archicad.",
                "Нужна раковина, столешница, мебель, плитка или отделочные материалы.",
            ],
            semantic_negative_threshold=0.82,
            require_include_match=False,
            require_context_match=False,
            min_score=0.48,
            max_results=3000,
            broad_score_weight=0.15,
            intent_hit_weight=0.08,
            metadata_json={
                "opportunity_profile": PROJECT_OPPORTUNITY_PROFILE,
                "profile_version": "1.0",
                "profile_title": "Проектные возможности для ПУР в чате дизайнеров",
                "project_terms": PROJECT_OPPORTUNITY_PROJECT_TERMS,
                "pur_fit_terms": PROJECT_OPPORTUNITY_PUR_TERMS,
                "commercial_terms": PROJECT_OPPORTUNITY_COMMERCIAL_TERMS,
                "reject_terms": PROJECT_OPPORTUNITY_REJECT_TERMS,
                "min_pur_fit_score": 0.35,
                "min_project_or_commercial_score": 0.2,
            },
        )

    def run_project_opportunities(
        self,
        *,
        context_id: str,
        broad_analysis_run_id: str,
        actor: str,
    ) -> dict[str, Any]:
        layer = self.ensure_project_opportunity_layer(context_id, actor=actor)
        layer = self._refresh_project_opportunity_review_feedback(layer, actor=actor)
        return self.run_layer(
            context_id=context_id,
            layer_id=layer.id,
            broad_analysis_run_id=broad_analysis_run_id,
            actor=actor,
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
        exclude_lemmas: list[str] | None = None,
        exclude_phrases: list[str] | None = None,
        semantic_negative_examples: list[str] | None = None,
        semantic_negative_threshold: float = 0.78,
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
                exclude_lemmas_json=_clean_list(exclude_lemmas),
                exclude_phrases_json=_clean_list(exclude_phrases),
                semantic_negative_examples_json=_clean_list(semantic_negative_examples),
                semantic_negative_threshold=_score(semantic_negative_threshold, default=0.78),
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
            "exclude_lemmas",
            "exclude_phrases",
            "semantic_negative_examples",
            "include_categories",
            "exclude_categories",
            "include_core_names",
            "exclude_core_names",
        ):
            if field in values:
                patch[f"{field}_json"] = _clean_list(values[field])
        if "semantic_negative_threshold" in values:
            patch["semantic_negative_threshold"] = _score(
                values["semantic_negative_threshold"], default=0.78
            )
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

    def _refresh_project_opportunity_review_feedback(
        self,
        layer: InterestIntentLayerRecord,
        *,
        actor: str,
    ) -> InterestIntentLayerRecord:
        metadata = dict(layer.metadata_json or {}) if isinstance(layer.metadata_json, dict) else {}
        if metadata.get("opportunity_profile") != PROJECT_OPPORTUNITY_PROFILE:
            return layer
        feedback = self._context_intent_review_feedback(layer.context_id)
        merged_metadata = {
            **metadata,
            "positive_source_message_ids": _merge_string_lists(
                metadata.get("positive_source_message_ids"),
                feedback["positive_source_message_ids"],
            ),
            "positive_telegram_message_ids": _merge_string_lists(
                metadata.get("positive_telegram_message_ids"),
                feedback["positive_telegram_message_ids"],
            ),
            "excluded_source_message_ids": _merge_string_lists(
                metadata.get("excluded_source_message_ids"),
                feedback["excluded_source_message_ids"],
            ),
            "excluded_telegram_message_ids": _merge_string_lists(
                metadata.get("excluded_telegram_message_ids"),
                feedback["excluded_telegram_message_ids"],
            ),
            "operator_review_counts": feedback["operator_review_counts"],
            "operator_review_feedback_refreshed_at": utc_now().isoformat(),
        }
        if merged_metadata == metadata:
            return layer
        self.session.execute(
            update(interest_intent_layers_table)
            .where(interest_intent_layers_table.c.id == layer.id)
            .values(metadata_json=merged_metadata, updated_at=utc_now())
        )
        self.session.commit()
        self.audit.record_change(
            actor=actor,
            action="interest_intent_layer.feedback_refresh",
            entity_type="interest_context",
            entity_id=layer.context_id,
            old_value_json={"layer_id": layer.id},
            new_value_json={
                "layer_id": layer.id,
                "positive_count": len(merged_metadata["positive_telegram_message_ids"]),
                "negative_count": len(merged_metadata["excluded_telegram_message_ids"]),
            },
        )
        return self._layer(layer.id)

    def _context_intent_review_feedback(self, context_id: str) -> dict[str, Any]:
        rows = (
            self.session.execute(
                select(
                    feedback_events_table.c.action,
                    interest_intent_analysis_matches_table.c.source_message_id,
                    interest_intent_analysis_matches_table.c.telegram_message_id,
                )
                .join(
                    interest_intent_analysis_matches_table,
                    interest_intent_analysis_matches_table.c.id == feedback_events_table.c.target_id,
                )
                .where(feedback_events_table.c.target_type == "interest_intent_match")
                .where(feedback_events_table.c.application_status != "ignored")
                .where(interest_intent_analysis_matches_table.c.context_id == context_id)
                .where(
                    feedback_events_table.c.action.in_(
                        ["intent_match_correct", "intent_match_incorrect", "not_lead"]
                    )
                )
            )
            .mappings()
            .all()
        )
        positive_source_ids: list[str] = []
        positive_telegram_ids: list[str] = []
        negative_source_ids: list[str] = []
        negative_telegram_ids: list[str] = []
        counts: Counter[str] = Counter()
        for row in rows:
            action = str(row["action"] or "")
            counts["correct" if action == "intent_match_correct" else "incorrect"] += 1
            source_id = str(row["source_message_id"] or "")
            telegram_id = str(row["telegram_message_id"] or "")
            if action == "intent_match_correct":
                positive_source_ids.append(source_id)
                positive_telegram_ids.append(telegram_id)
            else:
                negative_source_ids.append(source_id)
                negative_telegram_ids.append(telegram_id)
        positive_telegram_set = {item for item in positive_telegram_ids if item}
        return {
            "positive_source_message_ids": _dedupe_strings(positive_source_ids),
            "positive_telegram_message_ids": _dedupe_strings(positive_telegram_ids),
            "excluded_source_message_ids": _dedupe_strings(negative_source_ids),
            "excluded_telegram_message_ids": [
                item
                for item in _dedupe_strings(negative_telegram_ids)
                if item not in positive_telegram_set
            ],
            "operator_review_counts": dict(counts),
        }

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
            match_rows, compiled_layer = self._build_intent_matches(
                run_id=run_id,
                context_id=context_id,
                layer=layer,
                broad_run=broad_run,
                created_at=now,
            )
            if match_rows:
                self.session.execute(insert(interest_intent_analysis_matches_table), match_rows)
            summary = _intent_summary(
                match_rows,
                layer,
                compiled_layer,
                broad_match_count=int(broad_run["match_count"] or 0),
            )
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

    def project_opportunity_runs_payload(
        self,
        context_id: str,
        *,
        limit: int = 10,
        offset: int = 0,
    ) -> dict[str, Any]:
        safe_limit = max(1, min(100, int(limit)))
        safe_offset = max(0, int(offset))
        layer_ids = self._project_opportunity_layer_ids(context_id)
        if not layer_ids:
            return {
                "summary": {
                    "total": 0,
                    "page_count": 0,
                    "latest_match_count": 0,
                    "latest_matched_message_count": 0,
                },
                "items": [],
                "pagination": _pagination(limit=safe_limit, offset=safe_offset, total=0),
            }
        total = int(
            self.session.execute(
                select(func.count())
                .select_from(interest_intent_analysis_runs_table)
                .where(interest_intent_analysis_runs_table.c.context_id == context_id)
                .where(interest_intent_analysis_runs_table.c.intent_layer_id.in_(layer_ids))
            ).scalar_one()
            or 0
        )
        rows = (
            self.session.execute(
                select(interest_intent_analysis_runs_table)
                .where(interest_intent_analysis_runs_table.c.context_id == context_id)
                .where(interest_intent_analysis_runs_table.c.intent_layer_id.in_(layer_ids))
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
        feedback_by_match_id = self._intent_match_feedback_by_match_id(
            [str(row["id"]) for row in rows]
        )
        review_by_match_id = self._intent_match_review_by_match_id([str(row["id"]) for row in rows])
        return {
            "run": run.as_jsonable(),
            "items": [
                _match_record(
                    {
                        **dict(row),
                        "operator_feedback_json": feedback_by_match_id.get(str(row["id"])),
                        "operator_review_json": review_by_match_id.get(str(row["id"])),
                    }
                )
                for row in rows
            ],
            "pagination": _pagination(limit=safe_limit, offset=safe_offset, total=total),
        }

    def _intent_match_feedback_by_match_id(self, match_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not match_ids:
            return {}
        rows = (
            self.session.execute(
                select(
                    feedback_events_table.c.id,
                    feedback_events_table.c.target_id,
                    feedback_events_table.c.action,
                    feedback_events_table.c.reason_code,
                    feedback_events_table.c.feedback_scope,
                    feedback_events_table.c.learning_effect,
                    feedback_events_table.c.application_status,
                    feedback_events_table.c.applied_entity_type,
                    feedback_events_table.c.applied_entity_id,
                    feedback_events_table.c.applied_at,
                    feedback_events_table.c.comment,
                    feedback_events_table.c.created_by,
                    feedback_events_table.c.created_at,
                    feedback_events_table.c.metadata_json,
                )
                .where(feedback_events_table.c.target_type == "interest_intent_match")
                .where(feedback_events_table.c.action == "not_lead")
                .where(feedback_events_table.c.application_status != "ignored")
                .where(feedback_events_table.c.target_id.in_(match_ids))
                .order_by(desc(feedback_events_table.c.created_at))
            )
            .mappings()
            .all()
        )
        feedback_by_match_id: dict[str, dict[str, Any]] = {}
        for row in rows:
            target_id = str(row["target_id"])
            if target_id in feedback_by_match_id:
                continue
            feedback_by_match_id[target_id] = {
                "id": row["id"],
                "action": row["action"],
                "reason_code": row["reason_code"],
                "feedback_scope": row["feedback_scope"],
                "learning_effect": row["learning_effect"],
                "application_status": row["application_status"],
                "applied_entity_type": row["applied_entity_type"],
                "applied_entity_id": row["applied_entity_id"],
                "applied_at": row["applied_at"],
                "comment": row["comment"],
                "created_by": row["created_by"],
                "created_at": row["created_at"],
                "metadata_json": row["metadata_json"],
            }
        return feedback_by_match_id

    def _intent_match_review_by_match_id(self, match_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not match_ids:
            return {}
        rows = (
            self.session.execute(
                select(
                    feedback_events_table.c.id,
                    feedback_events_table.c.target_id,
                    feedback_events_table.c.action,
                    feedback_events_table.c.reason_code,
                    feedback_events_table.c.feedback_scope,
                    feedback_events_table.c.learning_effect,
                    feedback_events_table.c.application_status,
                    feedback_events_table.c.comment,
                    feedback_events_table.c.created_by,
                    feedback_events_table.c.created_at,
                    feedback_events_table.c.metadata_json,
                )
                .where(feedback_events_table.c.target_type == "interest_intent_match")
                .where(
                    feedback_events_table.c.action.in_(
                        ["intent_match_correct", "intent_match_incorrect"]
                    )
                )
                .where(feedback_events_table.c.application_status != "ignored")
                .where(feedback_events_table.c.target_id.in_(match_ids))
                .order_by(desc(feedback_events_table.c.created_at))
            )
            .mappings()
            .all()
        )
        review_by_match_id: dict[str, dict[str, Any]] = {}
        for row in rows:
            target_id = str(row["target_id"])
            if target_id in review_by_match_id:
                continue
            action = str(row["action"])
            review_by_match_id[target_id] = {
                "id": row["id"],
                "decision": "correct" if action == "intent_match_correct" else "incorrect",
                "action": action,
                "reason_code": row["reason_code"],
                "feedback_scope": row["feedback_scope"],
                "learning_effect": row["learning_effect"],
                "application_status": row["application_status"],
                "comment": row["comment"],
                "created_by": row["created_by"],
                "created_at": row["created_at"],
                "metadata_json": row["metadata_json"],
            }
        return review_by_match_id

    def _build_intent_matches(
        self,
        *,
        run_id: str,
        context_id: str,
        layer: InterestIntentLayerRecord,
        broad_run: dict[str, Any],
        created_at: Any,
    ) -> tuple[list[dict[str, Any]], "_CompiledIntentLayer"]:
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
                    "semantic_negative_score": match["semantic_negative_score"],
                    "semantic_positive_score": match["semantic_positive_score"],
                    "positive_boost": match["positive_boost"],
                    "core_item": row["canonical_name"],
                    "category": row["category"],
                    **(
                        {"opportunity": match["opportunity"]}
                        if isinstance(match.get("opportunity"), dict)
                        else {}
                    ),
                },
                "created_at": created_at,
            }
            current = best_by_message.get(str(row["source_message_id"]))
            if current is None or candidate["score"] > current["score"]:
                best_by_message[str(row["source_message_id"])] = candidate
        return (
            sorted(best_by_message.values(), key=lambda item: item["score"], reverse=True)[
                : layer.max_results
            ],
            config,
        )

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
                    lemmas=tuple(_fold(lemma) for lemma in lemmas if _fold(lemma)),
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

    def _project_opportunity_layer_ids(self, context_id: str) -> list[str]:
        rows = (
            self.session.execute(
                select(
                    interest_intent_layers_table.c.id,
                    interest_intent_layers_table.c.metadata_json,
                )
                .where(interest_intent_layers_table.c.context_id == context_id)
                .where(interest_intent_layers_table.c.status != "archived")
            )
            .mappings()
            .all()
        )
        layer_ids: list[str] = []
        for row in rows:
            metadata = row["metadata_json"] if isinstance(row["metadata_json"], dict) else {}
            if metadata.get("opportunity_profile") == PROJECT_OPPORTUNITY_PROFILE:
                layer_ids.append(str(row["id"]))
        return layer_ids

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
        metadata = layer.metadata_json if isinstance(layer.metadata_json, dict) else {}
        self.opportunity_profile = str(metadata.get("opportunity_profile") or "")
        self.opportunity_project_terms = _compile_lexicon_terms(
            _string_items(metadata.get("project_terms") or PROJECT_OPPORTUNITY_PROJECT_TERMS)
        )
        self.opportunity_pur_fit_terms = _compile_lexicon_terms(
            _string_items(metadata.get("pur_fit_terms") or PROJECT_OPPORTUNITY_PUR_TERMS)
        )
        self.opportunity_commercial_terms = _compile_lexicon_terms(
            _string_items(metadata.get("commercial_terms") or PROJECT_OPPORTUNITY_COMMERCIAL_TERMS)
        )
        self.opportunity_reject_terms = _compile_lexicon_terms(
            _string_items(metadata.get("reject_terms") or PROJECT_OPPORTUNITY_REJECT_TERMS)
        )
        self.min_pur_fit_score = _score(metadata.get("min_pur_fit_score"), default=0.35)
        self.min_project_or_commercial_score = _score(
            metadata.get("min_project_or_commercial_score"), default=0.2
        )
        self.include_patterns = _compile_patterns(_json_list(layer.include_patterns_json))
        self.context_patterns = _compile_patterns(_json_list(layer.context_patterns_json))
        self.exclude_patterns = _compile_patterns(_json_list(layer.exclude_patterns_json))
        self.exclude_lemma_rules = _compile_lemma_rules(_json_list(layer.exclude_lemmas_json))
        self.exclude_phrase_rules = _compile_phrase_rules(_json_list(layer.exclude_phrases_json))
        self.semantic_negative_examples = _merge_casefold_strings(
            _string_items(layer.semantic_negative_examples_json),
            _string_items(metadata.get("operator_semantic_negative_examples")),
        )
        self.semantic_negative_threshold = _score(
            metadata.get("operator_semantic_negative_threshold"),
            default=_score(layer.semantic_negative_threshold, default=0.78),
        )
        self.semantic_positive_examples = _string_items(
            metadata.get("operator_semantic_positive_examples")
        )
        self.semantic_positive_threshold = _score(
            metadata.get("operator_positive_boost_threshold"), default=0.55
        )
        self.semantic_positive_margin = _score(
            metadata.get("operator_semantic_positive_margin"), default=0.03
        )
        self.positive_score_boost = min(
            0.3,
            _score(metadata.get("operator_positive_score_boost"), default=0.08),
        )
        self._semantic_embedder = (
            LocalHashingEmbedder(dimensions=DEFAULT_EMBEDDING_DIMENSIONS)
            if self.semantic_negative_examples or self.semantic_positive_examples
            else None
        )
        self._semantic_negative_vectors = (
            self._semantic_embedder.embed_texts(self.semantic_negative_examples)
            if self._semantic_embedder is not None
            else []
        )
        self._semantic_positive_vectors = (
            self._semantic_embedder.embed_texts(self.semantic_positive_examples)
            if self._semantic_embedder is not None
            else []
        )
        self.include_categories = _casefold_set(layer.include_categories_json)
        self.exclude_categories = _casefold_set(layer.exclude_categories_json)
        self.include_core_names = _casefold_set(layer.include_core_names_json)
        self.exclude_core_names = _casefold_set(layer.exclude_core_names_json)
        self.excluded_source_message_ids = {
            str(item) for item in metadata.get("excluded_source_message_ids", []) if str(item)
        }
        self.excluded_telegram_message_ids = {
            str(item) for item in metadata.get("excluded_telegram_message_ids", []) if str(item)
        }
        self.positive_source_message_ids = {
            str(item) for item in metadata.get("positive_source_message_ids", []) if str(item)
        }
        self.positive_telegram_message_ids = {
            str(item) for item in metadata.get("positive_telegram_message_ids", []) if str(item)
        }
        self.operator_review_counts = (
            dict(metadata.get("operator_review_counts"))
            if isinstance(metadata.get("operator_review_counts"), dict)
            else {}
        )
        self.exclusion_counts: Counter[str] = Counter()
        self.exclusion_samples: list[dict[str, Any]] = []
        self.positive_boosted_count = 0
        self.positive_boosted_samples: list[dict[str, Any]] = []

    def match(
        self,
        row: Any,
        *,
        prepared_text: _PreparedMessageText | None = None,
    ) -> dict[str, Any] | None:
        raw_text = str(row["message_text"] or "")
        prepared = prepared_text or _prepared_from_raw(raw_text)
        text = prepared.search_text
        source_message_id = str(row["source_message_id"])
        telegram_message_id = str(row["telegram_message_id"])
        positive_protected = (
            source_message_id in self.positive_source_message_ids
            or telegram_message_id in self.positive_telegram_message_ids
        )
        if source_message_id in self.excluded_source_message_ids and not positive_protected:
            self._record_exclusion("exact_operator_incorrect", row)
            return None
        if telegram_message_id in self.excluded_telegram_message_ids and not positive_protected:
            self._record_exclusion("exact_operator_incorrect", row)
            return None
        semantic_scores = self._semantic_scores(prepared)
        semantic_negative_score = semantic_scores["negative_score"]
        semantic_positive_score = semantic_scores["positive_score"]
        semantic_positive_protected = (
            semantic_positive_score >= self.semantic_positive_threshold
            and semantic_positive_score + self.semantic_positive_margin >= semantic_negative_score
        )
        positive_signal = positive_protected or semantic_positive_protected
        normalized_category = _fold(row["category"])
        normalized_name = _fold(row["canonical_name"])
        if (
            self.include_categories
            and normalized_category not in self.include_categories
            and not positive_signal
        ):
            self._record_exclusion("include_category_miss", row)
            return None
        if (
            self.include_core_names
            and normalized_name not in self.include_core_names
            and not positive_signal
        ):
            self._record_exclusion("include_core_name_miss", row)
            return None
        if normalized_category in self.exclude_categories and not positive_signal:
            self._record_exclusion("exclude_category", row)
            return None
        if normalized_name in self.exclude_core_names and not positive_signal:
            self._record_exclusion("exclude_core_name", row)
            return None
        if _lemma_rule_hits(self.exclude_lemma_rules, prepared) and not positive_signal:
            self._record_exclusion("exclude_lemma", row)
            return None
        if _phrase_rule_hits(self.exclude_phrase_rules, prepared) and not positive_signal:
            self._record_exclusion("exclude_phrase", row)
            return None
        if (
            semantic_negative_score >= self.semantic_negative_threshold
            and semantic_negative_score >= semantic_positive_score + self.semantic_positive_margin
            and self.opportunity_profile != PROJECT_OPPORTUNITY_PROFILE
            and not positive_signal
        ):
            self._record_exclusion(
                "semantic_negative",
                row,
                {
                    "semantic_negative_score": round(semantic_negative_score, 4),
                    "semantic_positive_score": round(semantic_positive_score, 4),
                    "semantic_negative_example": semantic_scores.get("negative_example"),
                },
            )
            return None
        if _pattern_hits(self.exclude_patterns, text) and not positive_signal:
            self._record_exclusion("advanced_regex", row)
            return None
        if self.opportunity_profile == PROJECT_OPPORTUNITY_PROFILE:
            return self._match_project_opportunity(
                row,
                prepared=prepared,
                positive_signal=positive_signal,
                semantic_negative_score=semantic_negative_score,
                semantic_positive_score=semantic_positive_score,
                semantic_scores=semantic_scores,
            )
        include_hits = _pattern_hits(self.include_patterns, text)
        if self.layer.require_include_match and not include_hits and not positive_signal:
            self._record_exclusion("include_pattern_miss", row)
            return None
        context_hits = _pattern_hits(self.context_patterns, text)
        if self.layer.require_context_match and not context_hits and not positive_signal:
            self._record_exclusion("context_pattern_miss", row)
            return None
        broad_score = float(row["score"] or 0)
        intent_score = min(0.55, len(include_hits) * self.layer.intent_hit_weight)
        context_score = min(0.28, len(context_hits) * 0.14)
        positive_boost = (
            self.positive_score_boost
            if positive_signal
            else 0.0
        )
        score = min(
            0.99,
            broad_score * self.layer.broad_score_weight
            + intent_score
            + context_score
            + positive_boost,
        )
        if positive_signal and score < self.layer.min_score:
            score = min(0.99, max(score, self.layer.min_score))
        if score < self.layer.min_score:
            self._record_exclusion("min_score", row)
            return None
        if positive_boost > 0:
            self.positive_boosted_count += 1
            self._record_positive_boost(
                row,
                {
                    "semantic_positive_score": round(semantic_positive_score, 4),
                    "semantic_negative_score": round(semantic_negative_score, 4),
                    "positive_boost": round(positive_boost, 4),
                    "semantic_positive_example": semantic_scores.get("positive_example"),
                },
            )
        return {
            "include_hits": include_hits,
            "context_hits": context_hits,
            "score": round(score, 4),
            "score_parts": {
                "broad": round(broad_score * self.layer.broad_score_weight, 4),
                "intent": round(intent_score, 4),
                "context": round(context_score, 4),
                "positive_boost": round(positive_boost, 4),
            },
            "prepared_text": {
                "source": prepared.source,
                "used_clean_text": bool(prepared.clean_text),
                "used_lemmas": bool(prepared.lemmas_text),
            },
            "semantic_negative_score": round(semantic_negative_score, 4),
            "semantic_positive_score": round(semantic_positive_score, 4),
            "semantic_positive_signal": bool(semantic_positive_protected),
            "operator_positive_signal": bool(positive_protected),
            "positive_boost": round(positive_boost, 4),
        }

    def _match_project_opportunity(
        self,
        row: Any,
        *,
        prepared: _PreparedMessageText,
        positive_signal: bool,
        semantic_negative_score: float,
        semantic_positive_score: float,
        semantic_scores: dict[str, Any],
    ) -> dict[str, Any] | None:
        project_hits = _lexicon_hits(prepared, self.opportunity_project_terms)
        pur_fit_hits = _lexicon_hits(prepared, self.opportunity_pur_fit_terms)
        commercial_hits = _lexicon_hits(prepared, self.opportunity_commercial_terms)
        reject_hits = _lexicon_hits(prepared, self.opportunity_reject_terms)
        category_boost = _opportunity_category_boost(row)
        broad_score = float(row["score"] or 0)
        topic_score = max(0.0, min(1.0, broad_score))
        project_score = min(1.0, len(project_hits) * 0.22)
        pur_fit_score = min(1.0, len(pur_fit_hits) * 0.2 + category_boost)
        commercial_score = min(1.0, len(commercial_hits) * 0.18)
        reject_score = min(1.0, len(reject_hits) * 0.16)
        if (
            semantic_negative_score >= self.semantic_negative_threshold
            and semantic_negative_score > semantic_positive_score + self.semantic_positive_margin
        ):
            reject_score = max(reject_score, min(1.0, semantic_negative_score))
        protected = positive_signal
        reject_penalty = 0.18 if pur_fit_score >= 0.65 and project_score >= 0.2 else 0.38
        final_score = (
            topic_score * 0.15
            + project_score * 0.25
            + pur_fit_score * 0.35
            + commercial_score * 0.25
            - reject_score * reject_penalty
        )
        if protected:
            final_score += self.positive_score_boost
        final_score = max(0.0, min(0.99, final_score))
        reject_reason = _opportunity_reject_reason(
            reject_hits=reject_hits,
            pur_fit_score=pur_fit_score,
            project_score=project_score,
            commercial_score=commercial_score,
        )
        if pur_fit_score < self.min_pur_fit_score and not protected:
            self._record_exclusion(
                "opportunity_pur_fit_miss",
                row,
                {
                    "pur_fit_score": round(pur_fit_score, 4),
                    "project_score": round(project_score, 4),
                    "commercial_score": round(commercial_score, 4),
                    "reject_reason": reject_reason,
                },
            )
            return None
        if (
            max(project_score, commercial_score) < self.min_project_or_commercial_score
            and not protected
        ):
            self._record_exclusion(
                "opportunity_project_context_miss",
                row,
                {
                    "pur_fit_score": round(pur_fit_score, 4),
                    "project_score": round(project_score, 4),
                    "commercial_score": round(commercial_score, 4),
                    "reject_reason": reject_reason,
                },
            )
            return None
        if reject_score >= 0.48 and pur_fit_score < 0.65 and not protected:
            self._record_exclusion(
                "opportunity_designer_noise",
                row,
                {
                    "reject_score": round(reject_score, 4),
                    "reject_reason": reject_reason,
                    "reject_hits": reject_hits[:8],
                },
            )
            return None
        if final_score < self.layer.min_score and not protected:
            self._record_exclusion(
                "opportunity_min_score",
                row,
                {
                    "final_score": round(final_score, 4),
                    "pur_fit_score": round(pur_fit_score, 4),
                    "project_score": round(project_score, 4),
                    "commercial_score": round(commercial_score, 4),
                    "reject_score": round(reject_score, 4),
                    "reject_reason": reject_reason,
                },
            )
            return None
        if protected and final_score < self.layer.min_score:
            final_score = min(0.99, self.layer.min_score)
        opportunity_type = _opportunity_type(pur_fit_hits, row)
        if protected:
            self.positive_boosted_count += 1
            self._record_positive_boost(
                row,
                {
                    "semantic_positive_score": round(semantic_positive_score, 4),
                    "semantic_negative_score": round(semantic_negative_score, 4),
                    "positive_boost": round(self.positive_score_boost, 4),
                    "semantic_positive_example": semantic_scores.get("positive_example"),
                },
            )
        return {
            "include_hits": commercial_hits,
            "context_hits": pur_fit_hits,
            "score": round(final_score, 4),
            "score_parts": {
                "topic": round(topic_score, 4),
                "project": round(project_score, 4),
                "pur_fit": round(pur_fit_score, 4),
                "commercial": round(commercial_score, 4),
                "reject": round(reject_score, 4),
                "positive_boost": round(self.positive_score_boost if protected else 0.0, 4),
            },
            "prepared_text": {
                "source": prepared.source,
                "used_clean_text": bool(prepared.clean_text),
                "used_lemmas": bool(prepared.lemmas_text),
            },
            "semantic_negative_score": round(semantic_negative_score, 4),
            "semantic_positive_score": round(semantic_positive_score, 4),
            "semantic_positive_signal": bool(protected and not positive_signal),
            "operator_positive_signal": bool(positive_signal),
            "positive_boost": round(self.positive_score_boost if protected else 0.0, 4),
            "opportunity": {
                "profile": PROJECT_OPPORTUNITY_PROFILE,
                "decision": "yes" if final_score >= 0.62 else "maybe",
                "opportunity_type": opportunity_type,
                "topic_score": round(topic_score, 4),
                "project_score": round(project_score, 4),
                "pur_fit_score": round(pur_fit_score, 4),
                "commercial_intent_score": round(commercial_score, 4),
                "reject_score": round(reject_score, 4),
                "reject_reason": None if reject_score < 0.48 or pur_fit_score >= 0.65 else reject_reason,
                "project_hits": project_hits[:10],
                "pur_fit_hits": pur_fit_hits[:10],
                "commercial_hits": commercial_hits[:10],
                "reject_hits": reject_hits[:10],
                "operator_summary": _opportunity_summary(
                    opportunity_type=opportunity_type,
                    pur_fit_hits=pur_fit_hits,
                    project_hits=project_hits,
                    commercial_hits=commercial_hits,
                ),
            },
        }

    def _semantic_scores(self, prepared: _PreparedMessageText) -> dict[str, Any]:
        if self._semantic_embedder is None:
            return {
                "negative_score": 0.0,
                "positive_score": 0.0,
                "negative_example": None,
                "positive_example": None,
            }
        vector = self._semantic_embedder.embed_texts([prepared.search_text])[0]
        negative_score = 0.0
        negative_example = None
        for example, example_vector in zip(self.semantic_negative_examples, self._semantic_negative_vectors, strict=False):
            score = _dot(vector, example_vector)
            if score > negative_score:
                negative_score = score
                negative_example = example
        positive_score = 0.0
        positive_example = None
        for example, example_vector in zip(self.semantic_positive_examples, self._semantic_positive_vectors, strict=False):
            score = _dot(vector, example_vector)
            if score > positive_score:
                positive_score = score
                positive_example = example
        return {
            "negative_score": negative_score,
            "positive_score": positive_score,
            "negative_example": negative_example,
            "positive_example": positive_example,
        }

    def _record_exclusion(
        self,
        reason: str,
        row: Any,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.exclusion_counts[reason] += 1
        if len(self.exclusion_samples) >= 20:
            return
        self.exclusion_samples.append(
            {
                "reason": reason,
                "source_message_id": str(row["source_message_id"]),
                "telegram_message_id": row["telegram_message_id"],
                "canonical_name": row["canonical_name"],
                "message_text": _truncate(row["message_text"], 180),
                **(details or {}),
            }
        )

    def _record_positive_boost(self, row: Any, details: dict[str, Any]) -> None:
        if len(self.positive_boosted_samples) >= 20:
            return
        self.positive_boosted_samples.append(
            {
                "source_message_id": str(row["source_message_id"]),
                "telegram_message_id": row["telegram_message_id"],
                "canonical_name": row["canonical_name"],
                "message_text": _truncate(row["message_text"], 180),
                **details,
            }
        )


def _intent_summary(
    match_rows: list[dict[str, Any]],
    layer: InterestIntentLayerRecord,
    compiled_layer: _CompiledIntentLayer,
    *,
    broad_match_count: int,
) -> dict[str, Any]:
    message_ids = {row["source_message_id"] for row in match_rows}
    by_category = Counter(str(row["category"] or "без категории") for row in match_rows)
    by_core_item = Counter(str(row["canonical_name"] or row["interest_core_item_id"]) for row in match_rows)
    by_opportunity_type = Counter(
        str((row.get("evidence_json") or {}).get("opportunity", {}).get("opportunity_type"))
        for row in match_rows
        if isinstance((row.get("evidence_json") or {}).get("opportunity"), dict)
    )
    by_opportunity_decision = Counter(
        str((row.get("evidence_json") or {}).get("opportunity", {}).get("decision"))
        for row in match_rows
        if isinstance((row.get("evidence_json") or {}).get("opportunity"), dict)
    )
    exclusion_counts = dict(compiled_layer.exclusion_counts)
    exclusion_total = sum(exclusion_counts.values())
    cleaned_total = max(0, int(broad_match_count) - len(match_rows))
    return {
        "matched_message_count": len(message_ids),
        "match_count": len(match_rows),
        "input_broad_match_count": int(broad_match_count),
        "cleaned_total": cleaned_total,
        "exclusions": {
            "total": exclusion_total,
            **exclusion_counts,
            "samples": compiled_layer.exclusion_samples,
        },
        "review_training": {
            "operator_review_counts": compiled_layer.operator_review_counts,
            "exact_negative_ids": len(compiled_layer.excluded_source_message_ids),
            "exact_positive_ids": len(compiled_layer.positive_source_message_ids),
            "semantic_negative_examples": len(compiled_layer.semantic_negative_examples),
            "semantic_positive_examples": len(compiled_layer.semantic_positive_examples),
            "semantic_negative_threshold": compiled_layer.semantic_negative_threshold,
            "semantic_positive_margin": compiled_layer.semantic_positive_margin,
            "positive_boost_threshold": compiled_layer.semantic_positive_threshold,
            "positive_score_boost": compiled_layer.positive_score_boost,
        },
        "positive_boosted_count": compiled_layer.positive_boosted_count,
        "positive_boosted_samples": compiled_layer.positive_boosted_samples,
        "by_category": dict(by_category.most_common(20)),
        "top_core_items": dict(by_core_item.most_common(20)),
        "by_opportunity_type": dict(by_opportunity_type.most_common(20)),
        "by_opportunity_decision": dict(by_opportunity_decision.most_common(20)),
        "algorithm": "local_intent_layer_v1",
        "intent_layer": {
            "id": layer.id,
            "name": layer.name,
            "min_score": layer.min_score,
            "max_results": layer.max_results,
            "exclude_lemmas_count": len(_json_list(layer.exclude_lemmas_json)),
            "exclude_phrases_count": len(_json_list(layer.exclude_phrases_json)),
            "semantic_negative_examples_count": len(
                _json_list(layer.semantic_negative_examples_json)
            ),
        },
    }


def _score(value: Any, *, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(0.0, min(1.0, number))


def _clean_list(value: list[str] | None) -> list[str]:
    if not value:
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _string_items(value: Any) -> list[str]:
    return [str(item).strip() for item in _json_list(value) if str(item or "").strip()]


def _merge_casefold_strings(left: list[str], right: list[str]) -> list[str]:
    result = list(left)
    seen = {item.casefold().strip() for item in result}
    for item in right:
        key = item.casefold().strip()
        if key and key not in seen:
            result.append(item)
            seen.add(key)
    return result


def _dedupe_strings(value: Any) -> list[str]:
    return _merge_string_lists(value, [])


def _merge_string_lists(left: Any, right: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for source in (_json_list(left), _json_list(right)):
        for item in source:
            clean = str(item or "").strip()
            if clean and clean not in seen:
                result.append(clean)
                seen.add(clean)
    return result


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


def _compile_lemma_rules(values: list[Any]) -> list[tuple[str, tuple[str, ...]]]:
    rules: list[tuple[str, tuple[str, ...]]] = []
    for value in values:
        text = str(value or "").strip()
        lemmas = tuple(_normal_lemmas(text))
        if text and lemmas:
            rules.append((text, lemmas))
    return rules


def _compile_phrase_rules(values: list[Any]) -> list[tuple[str, tuple[str, ...]]]:
    return _compile_lemma_rules(values)


def _lemma_rule_hits(
    rules: list[tuple[str, tuple[str, ...]]],
    prepared: _PreparedMessageText,
) -> list[str]:
    if not rules:
        return []
    lemma_set = set(prepared.lemmas) or set(_normal_lemmas(prepared.search_text))
    hits = []
    for source, lemmas in rules:
        if all(lemma in lemma_set for lemma in lemmas):
            hits.append(source)
    return hits[:10]


def _phrase_rule_hits(
    rules: list[tuple[str, tuple[str, ...]]],
    prepared: _PreparedMessageText,
) -> list[str]:
    if not rules:
        return []
    lemmas = prepared.lemmas or tuple(_normal_lemmas(prepared.search_text))
    text = f" {' '.join(lemmas)} "
    hits = []
    for source, phrase_lemmas in rules:
        phrase = f" {' '.join(phrase_lemmas)} "
        if phrase.strip() and phrase in text:
            hits.append(source)
    return hits[:10]


def _compile_lexicon_terms(terms: list[str]) -> list[_LexiconTerm]:
    compiled: list[_LexiconTerm] = []
    seen: set[str] = set()
    for term in terms:
        source = str(term or "").strip()
        if not source:
            continue
        folded = _fold(source)
        if not folded or folded in seen:
            continue
        seen.add(folded)
        compiled.append(
            _LexiconTerm(
                source=source,
                folded=folded,
                is_phrase=bool(" " in folded or "-" in folded),
                lemmas=tuple(_normal_lemmas(folded)),
            )
        )
    return compiled


def _lexicon_hits(prepared: _PreparedMessageText, terms: list[_LexiconTerm]) -> list[str]:
    text = _fold(prepared.search_text)
    lemmas_text = _fold(prepared.lemmas_text)
    token_set = set(TOKEN_RE.findall(text))
    lemma_set = set(prepared.lemmas) or set(_normal_lemmas(prepared.search_text))
    hits: list[str] = []
    for term in terms:
        if term.is_phrase:
            lemma_phrase = " ".join(term.lemmas)
            if term.folded in text or (lemma_phrase and lemma_phrase in lemmas_text):
                hits.append(term.source)
            continue
        if (
            term.folded in token_set
            or term.folded in lemma_set
            or any(lemma in lemma_set for lemma in term.lemmas)
        ):
            hits.append(term.source)
    return list(dict.fromkeys(hits))[:20]


def _opportunity_category_boost(row: Any) -> float:
    category = _fold(row["category"])
    canonical_name = _fold(row["canonical_name"])
    text = f"{category} {canonical_name}"
    if any(
        token in text
        for token in (
            "автоматизация",
            "безопасность",
            "инфраструктура",
            "электр",
            "камер",
            "домофон",
            "видеонаблюдение",
        )
    ):
        return 0.15
    return 0.0


def _opportunity_reject_reason(
    *,
    reject_hits: list[str],
    pur_fit_score: float,
    project_score: float,
    commercial_score: float,
) -> str | None:
    if pur_fit_score < 0.35:
        return "not_pur_scope"
    if max(project_score, commercial_score) < 0.2:
        return "no_project_or_action"
    folded_hits = {_fold(hit) for hit in reject_hits}
    if folded_hits & {"архикад", "archicad", "визуализатор", "визуализация", "рендер", "3d"}:
        return "software_or_visualization"
    if folded_hits & {"раковина", "ванна", "унитаз", "плитка", "обои", "столешница", "камень", "мебель"}:
        return "materials_or_furniture_only"
    if folded_hits & {"ниша", "профиль", "трек", "трековый", "светильник", "натяжной"}:
        return "interior_lighting_only"
    return "designer_noise"


def _opportunity_type(pur_fit_hits: list[str], row: Any) -> str:
    text = _fold(" ".join([*pur_fit_hits, str(row["canonical_name"] or ""), str(row["category"] or "")]))
    if any(token in text for token in ("камера", "видеокамера", "видеонаблюдение", "домофон", "скуд", "замок")):
        return "equipment_or_security"
    if any(token in text for token in ("умный дом", "home assistant", "автоматизация", "алиса", "яндекс", "сценарий")):
        return "integration"
    if any(token in text for token in ("электрика", "щит", "кабель", "провод", "вывод", "реле", "диммер")):
        return "engineering_consulting"
    if any(token in text for token in ("wi-fi", "wifi", "сеть", "роутер", "интернет")):
        return "infrastructure"
    return "partner_referral"


def _opportunity_summary(
    *,
    opportunity_type: str,
    pur_fit_hits: list[str],
    project_hits: list[str],
    commercial_hits: list[str],
) -> str:
    subject = ", ".join(pur_fit_hits[:3]) or "тема ПУР"
    project = ", ".join(project_hits[:2]) or "проектный контекст"
    action = ", ".join(commercial_hits[:2]) or "возможный следующий шаг"
    return f"{opportunity_type}: {subject}; контекст: {project}; действие: {action}"


def _prepared_from_raw(raw_text: str) -> _PreparedMessageText:
    clean_text = " ".join(TOKEN_RE.findall(raw_text.casefold().replace("ё", "е")))
    lemmas = tuple(_normal_lemmas(raw_text))
    return _PreparedMessageText(
        raw_text=raw_text,
        clean_text=clean_text,
        lemmas_text=" ".join(lemmas),
        lemmas=lemmas,
        source="raw_message_text",
    )


def _normal_lemmas(text: str) -> list[str]:
    tokens = [_fold(token) for token in TOKEN_RE.findall(str(text or ""))]
    tokens = [token for token in tokens if token]
    if not tokens:
        return []
    try:
        import pymorphy3

        morph = pymorphy3.MorphAnalyzer()
        return [_fold(morph.parse(token)[0].normal_form) for token in tokens]
    except Exception:
        return tokens


def _dot(left: list[float], right: list[float]) -> float:
    return sum(float(a) * float(b) for a, b in zip(left, right, strict=False))


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
