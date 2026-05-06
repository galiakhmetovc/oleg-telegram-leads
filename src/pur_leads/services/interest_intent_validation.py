"""LLM-assisted validation of intent-layer matches."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import json
import re
from typing import Any

import pyarrow.parquet as pq
from sqlalchemy import desc, func, insert, select, update
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.integrations.ai.chat import AiChatClient, AiChatMessage
from pur_leads.models.interest_context_drafts import (
    interest_core_analysis_runs_table,
    interest_core_items_table,
    interest_intent_analysis_matches_table,
    interest_intent_analysis_runs_table,
    interest_intent_layers_table,
    interest_intent_validation_recommendations_table,
    interest_intent_validation_runs_table,
)
from pur_leads.models.interest_contexts import interest_contexts_table
from pur_leads.models.interest_core_briefs import interest_core_briefs_table
from pur_leads.models.leads import feedback_events_table
from pur_leads.models.telegram_sources import telegram_raw_export_runs_table
from pur_leads.services.audit import AuditService
from pur_leads.services.interest_core_briefs import parse_interest_core_brief_response
from pur_leads.services.interest_intent_layers import (
    InterestIntentLayerService,
    _PreparedMessageText,
    _compile_lemma_rules,
    _compile_phrase_rules,
    _json_list,
    _lemma_rule_hits,
    _phrase_rule_hits,
    _prepared_from_raw,
    _resolve_path,
)
from pur_leads.services.telegram_chroma_index import DEFAULT_EMBEDDING_DIMENSIONS, LocalHashingEmbedder

INTENT_VALIDATION_PROMPT_VERSION = "interest-intent-validation-v1"
REVIEW_ACTIONS = {
    "correct": "intent_match_correct",
    "incorrect": "intent_match_incorrect",
}
REVIEW_ACTION_TO_DECISION = {value: key for key, value in REVIEW_ACTIONS.items()}
VALID_RECOMMENDATION_STATUSES = {"pending_review", "approved", "rejected", "applied"}


@dataclass(frozen=True)
class IntentValidationRunRecord:
    id: str
    context_id: str
    source_intent_run_id: str
    source_intent_layer_id: str
    status: str
    provider: str | None
    model: str | None
    model_profile: str | None
    ai_provider_account_id: str | None
    ai_model_id: str | None
    ai_model_profile_id: str | None
    ai_agent_route_id: str | None
    prompt_version: str
    prompt_text: str | None
    request_json: Any
    response_json: Any
    parsed_response_json: Any
    summary_json: Any
    recommendation_count: int
    created_layer_id: str | None
    error: str | None
    created_by: str
    started_at: Any
    finished_at: Any
    created_at: Any
    updated_at: Any

    def as_jsonable(self) -> dict[str, Any]:
        return asdict(self)


class InterestIntentValidationService:
    """Build AI recommendations from operator-reviewed intent matches."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.audit = AuditService(session)

    def latest_runs_payload(self, context_id: str, *, limit: int = 10, offset: int = 0) -> dict[str, Any]:
        safe_limit = max(1, min(100, int(limit)))
        safe_offset = max(0, int(offset))
        total = int(
            self.session.execute(
                select(func.count())
                .select_from(interest_intent_validation_runs_table)
                .where(interest_intent_validation_runs_table.c.context_id == context_id)
            ).scalar_one()
            or 0
        )
        rows = (
            self.session.execute(
                select(interest_intent_validation_runs_table)
                .where(interest_intent_validation_runs_table.c.context_id == context_id)
                .order_by(desc(interest_intent_validation_runs_table.c.created_at))
                .limit(safe_limit)
                .offset(safe_offset)
            )
            .mappings()
            .all()
        )
        return {
            "summary": {"total": total, "page_count": len(rows)},
            "items": [_run_record(row).as_jsonable() for row in rows],
            "pagination": _pagination(limit=safe_limit, offset=safe_offset, total=total),
        }

    def recommendations_payload(
        self,
        context_id: str,
        *,
        validation_run_id: str | None,
        limit: int = 10,
        offset: int = 0,
    ) -> dict[str, Any]:
        run = self._selected_run(context_id, validation_run_id)
        if run is None:
            return {
                "run": None,
                "items": [],
                "summary": {"total": 0, "approved": 0, "pending_review": 0, "rejected": 0},
                "pagination": _pagination(limit=limit, offset=offset, total=0),
            }
        safe_limit = max(1, min(100, int(limit)))
        safe_offset = max(0, int(offset))
        total = int(
            self.session.execute(
                select(func.count())
                .select_from(interest_intent_validation_recommendations_table)
                .where(
                    interest_intent_validation_recommendations_table.c.validation_run_id == run.id
                )
            ).scalar_one()
            or 0
        )
        rows = (
            self.session.execute(
                select(interest_intent_validation_recommendations_table)
                .where(interest_intent_validation_recommendations_table.c.validation_run_id == run.id)
                .order_by(
                    desc(interest_intent_validation_recommendations_table.c.created_at)
                )
                .limit(safe_limit)
                .offset(safe_offset)
            )
            .mappings()
            .all()
        )
        items = self._recommendation_rows_for_display(
            context_id,
            run.source_intent_run_id,
            [dict(row) for row in rows],
        )
        status_counts = Counter(
            str(row["status"])
            for row in self.session.execute(
                select(interest_intent_validation_recommendations_table.c.status).where(
                    interest_intent_validation_recommendations_table.c.validation_run_id == run.id
                )
            )
            .mappings()
            .all()
        )
        run_payload = run.as_jsonable()
        run_payload["created_intent_run"] = self._latest_intent_run_for_created_layer(
            context_id,
            run.created_layer_id,
        )
        return {
            "run": run_payload,
            "items": items,
            "summary": {
                "total": total,
                "approved": status_counts.get("approved", 0),
                "pending_review": status_counts.get("pending_review", 0),
                "rejected": status_counts.get("rejected", 0),
                "applied": status_counts.get("applied", 0),
            },
            "pagination": _pagination(limit=safe_limit, offset=safe_offset, total=total),
        }

    def recommendations_payload_for_source_run(
        self,
        context_id: str,
        *,
        source_intent_run_id: str,
        limit: int = 10,
        offset: int = 0,
    ) -> dict[str, Any]:
        intent_run = self._intent_run(context_id, source_intent_run_id)
        if intent_run is None:
            raise KeyError(source_intent_run_id)
        safe_limit = max(1, min(100, int(limit)))
        safe_offset = max(0, int(offset))
        run_ids_query = (
            select(interest_intent_validation_runs_table.c.id)
            .where(interest_intent_validation_runs_table.c.context_id == context_id)
            .where(
                interest_intent_validation_runs_table.c.source_intent_run_id
                == source_intent_run_id
            )
            .where(interest_intent_validation_runs_table.c.status == "succeeded")
        )
        total = int(
            self.session.execute(
                select(func.count())
                .select_from(interest_intent_validation_recommendations_table)
                .where(
                    interest_intent_validation_recommendations_table.c.validation_run_id.in_(
                        run_ids_query
                    )
                )
            ).scalar_one()
            or 0
        )
        rows = (
            self.session.execute(
                select(interest_intent_validation_recommendations_table)
                .where(
                    interest_intent_validation_recommendations_table.c.validation_run_id.in_(
                        run_ids_query
                    )
                )
                .order_by(
                    desc(interest_intent_validation_recommendations_table.c.created_at)
                )
                .limit(safe_limit)
                .offset(safe_offset)
            )
            .mappings()
            .all()
        )
        status_counts = Counter(
            str(row["status"])
            for row in self.session.execute(
                select(interest_intent_validation_recommendations_table.c.status).where(
                    interest_intent_validation_recommendations_table.c.validation_run_id.in_(
                        run_ids_query
                    )
                )
            )
            .mappings()
            .all()
        )
        run_count = int(
            self.session.execute(
                select(func.count()).select_from(run_ids_query.subquery())
            ).scalar_one()
            or 0
        )
        created_layer = self._latest_batch_layer_for_source_run(
            context_id=context_id,
            source_intent_run_id=source_intent_run_id,
        )
        created_layer_id = str(created_layer["id"]) if created_layer is not None else None
        run_payload = {
            "id": source_intent_run_id,
            "source_intent_run_id": source_intent_run_id,
            "source_intent_layer_id": intent_run["intent_layer_id"],
            "status": "batch",
            "batch_mode": True,
            "batch_run_count": run_count,
            "created_layer_id": created_layer_id,
            "created_intent_run": self._latest_intent_run_for_created_layer(
                context_id,
                created_layer_id,
            ),
        }
        return {
            "run": run_payload,
            "items": self._recommendation_rows_for_display(
                context_id,
                source_intent_run_id,
                [dict(row) for row in rows],
            ),
            "summary": {
                "total": total,
                "approved": status_counts.get("approved", 0),
                "pending_review": status_counts.get("pending_review", 0),
                "rejected": status_counts.get("rejected", 0),
                "applied": status_counts.get("applied", 0),
                "batch_run_count": run_count,
            },
            "pagination": _pagination(limit=safe_limit, offset=safe_offset, total=total),
        }

    async def generate_recommendations(
        self,
        *,
        context_id: str,
        source_intent_run_id: str,
        actor: str,
        client: AiChatClient,
        provider: str,
        model: str,
        model_profile: str | None,
        ai_provider_account_id: str | None,
        ai_model_id: str | None,
        ai_model_profile_id: str | None,
        ai_agent_route_id: str | None,
        temperature: float,
        max_tokens: int,
        max_reviews: int = 80,
        review_offset: int = 0,
    ) -> dict[str, Any]:
        payload = self.build_validation_payload(
            context_id=context_id,
            source_intent_run_id=source_intent_run_id,
            max_reviews=max_reviews,
            review_offset=review_offset,
        )
        if not payload["reviewed_matches"]:
            raise ValueError("Сначала разметьте хотя бы одно сообщение как правильное или неправильное")
        prompt_text = render_intent_validation_prompt(payload)
        messages = [
            AiChatMessage(
                role="system",
                content=(
                    "Ты валидируешь второй слой фильтрации лидов по ручной разметке оператора. "
                    "Не меняй правила сам. Верни только валидный JSON без markdown."
                ),
            ),
            AiChatMessage(role="user", content=prompt_text),
        ]
        now = utc_now()
        run_id = new_id()
        request_json = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "prompt_version": INTENT_VALIDATION_PROMPT_VERSION,
            "messages": [{"role": message.role, "content": message.content} for message in messages],
            "source_intent_run_id": source_intent_run_id,
            "review_offset": review_offset,
            "review_count": len(payload["reviewed_matches"]),
        }
        self.session.execute(
            insert(interest_intent_validation_runs_table).values(
                id=run_id,
                context_id=context_id,
                source_intent_run_id=source_intent_run_id,
                source_intent_layer_id=payload["intent_layer"]["id"],
                status="running",
                provider=provider,
                model=model,
                model_profile=model_profile,
                ai_provider_account_id=ai_provider_account_id,
                ai_model_id=ai_model_id,
                ai_model_profile_id=ai_model_profile_id,
                ai_agent_route_id=ai_agent_route_id,
                prompt_version=INTENT_VALIDATION_PROMPT_VERSION,
                prompt_text=prompt_text,
                request_json=request_json,
                response_json=None,
                parsed_response_json=None,
                summary_json={"input": payload["summary"]},
                recommendation_count=0,
                created_layer_id=None,
                error=None,
                created_by=actor,
                started_at=now,
                finished_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        self.session.commit()
        try:
            completion = await client.complete(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            parsed = normalize_intent_validation_response(
                parse_interest_core_brief_response(completion.content)
            )
            recommendations = parsed["recommendations"]
            match_rows = self._intent_match_rows(context_id, source_intent_run_id)
            prepared_texts = self._prepared_texts_for_intent_run(source_intent_run_id, match_rows)
            reviews = self._latest_reviews_by_match_id(source_intent_run_id)
            inserted = []
            for recommendation in recommendations:
                preview = self.preview_changes(
                    match_rows=match_rows,
                    reviews_by_match_id=reviews,
                    proposed_changes=recommendation["proposed_changes"],
                    prepared_texts=prepared_texts,
                )
                rec_id = new_id()
                inserted.append(rec_id)
                self.session.execute(
                    insert(interest_intent_validation_recommendations_table).values(
                        id=rec_id,
                        validation_run_id=run_id,
                        context_id=context_id,
                        source_intent_run_id=source_intent_run_id,
                        recommendation_type=recommendation["type"],
                        title=recommendation["title"][:300],
                        rationale=recommendation.get("rationale"),
                        confidence=recommendation.get("confidence") or "medium",
                        proposed_changes_json=recommendation["proposed_changes"],
                        impact_preview_json=preview,
                        status="pending_review",
                        review_note=None,
                        reviewed_by=None,
                        reviewed_at=None,
                        applied_at=None,
                        metadata_json={"llm_index": recommendation.get("index")},
                        created_at=utc_now(),
                        updated_at=utc_now(),
                    )
                )
            finished_at = utc_now()
            response_json = {
                "content": completion.content,
                "model": completion.model,
                "request_id": completion.request_id,
                "usage": completion.usage,
                "raw_response": completion.raw_response,
            }
            self.session.execute(
                update(interest_intent_validation_runs_table)
                .where(interest_intent_validation_runs_table.c.id == run_id)
                .values(
                    status="succeeded",
                    response_json=response_json,
                    parsed_response_json=parsed,
                    summary_json={"input": payload["summary"], "llm": parsed.get("summary", {})},
                    recommendation_count=len(inserted),
                    finished_at=finished_at,
                    updated_at=finished_at,
                )
            )
            self.audit.record_change(
                actor=actor,
                action="interest_intent_validation.generate",
                entity_type="interest_intent_validation_run",
                entity_id=run_id,
                old_value_json=None,
                new_value_json={
                    "source_intent_run_id": source_intent_run_id,
                    "review_offset": review_offset,
                    "recommendation_count": len(inserted),
                },
            )
            self.session.commit()
        except Exception as exc:
            failed_at = utc_now()
            self.session.execute(
                update(interest_intent_validation_runs_table)
                .where(interest_intent_validation_runs_table.c.id == run_id)
                .values(
                    status="failed",
                    error=str(exc) or exc.__class__.__name__,
                    finished_at=failed_at,
                    updated_at=failed_at,
                )
            )
            self.session.commit()
            raise
        return self.recommendations_payload(context_id, validation_run_id=run_id)

    def build_validation_payload(
        self,
        *,
        context_id: str,
        source_intent_run_id: str,
        max_reviews: int,
        review_offset: int = 0,
    ) -> dict[str, Any]:
        context = self._context(context_id)
        if context is None:
            raise KeyError(context_id)
        run = self._intent_run(context_id, source_intent_run_id)
        if run is None:
            raise KeyError(source_intent_run_id)
        layer = self._layer(str(run["intent_layer_id"]))
        reviews = self._reviewed_matches(
            context_id,
            source_intent_run_id,
            max_reviews=max_reviews,
            review_offset=review_offset,
        )
        correct_count = sum(1 for item in reviews if item["review"]["decision"] == "correct")
        incorrect_count = sum(1 for item in reviews if item["review"]["decision"] == "incorrect")
        brief = self._active_brief(context_id)
        core_items = self._core_items(context_id)
        return {
            "context": {
                "id": context_id,
                "name": context["name"],
                "description": context["description"],
            },
            "brief": brief,
            "intent_run": dict(run),
            "intent_layer": dict(layer),
            "core_items": core_items,
            "reviewed_matches": reviews,
            "summary": {
                "reviewed": len(reviews),
                "correct": correct_count,
                "incorrect": incorrect_count,
                "review_offset": max(0, int(review_offset)),
                "review_limit": max(1, int(max_reviews)),
                "source_intent_run_id": source_intent_run_id,
                "source_intent_layer_id": run["intent_layer_id"],
            },
        }

    def update_recommendation_status(
        self,
        recommendation_id: str,
        *,
        context_id: str,
        status: str,
        actor: str,
        note: str | None = None,
    ) -> dict[str, Any]:
        if status not in VALID_RECOMMENDATION_STATUSES - {"applied"}:
            raise ValueError("Unsupported recommendation status")
        row = self._recommendation(recommendation_id, context_id=context_id)
        if row is None:
            raise KeyError(recommendation_id)
        now = utc_now()
        self.session.execute(
            update(interest_intent_validation_recommendations_table)
            .where(interest_intent_validation_recommendations_table.c.id == recommendation_id)
            .values(
                status=status,
                review_note=note,
                reviewed_by=actor,
                reviewed_at=now,
                updated_at=now,
            )
        )
        self.session.commit()
        return dict(self._recommendation(recommendation_id, context_id=context_id) or {})

    def create_layer_from_approved(
        self,
        validation_run_id: str,
        *,
        context_id: str,
        actor: str,
    ) -> dict[str, Any]:
        run = self._validation_run(validation_run_id, context_id=context_id)
        if run is None:
            raise KeyError(validation_run_id)
        recommendations = (
            self.session.execute(
                select(interest_intent_validation_recommendations_table)
                .where(
                    interest_intent_validation_recommendations_table.c.validation_run_id
                    == validation_run_id
                )
                .where(interest_intent_validation_recommendations_table.c.status == "approved")
                .order_by(interest_intent_validation_recommendations_table.c.created_at)
            )
            .mappings()
            .all()
        )
        if not recommendations:
            raise ValueError("Нет одобренных рекомендаций для создания слоя")
        base_layer = self._layer(str(run["source_intent_layer_id"]))
        values = self._layer_values_with_recommendations(base_layer, recommendations)
        review_exclusions = self._incorrect_review_exclusions(
            context_id=context_id,
            source_intent_run_id=str(run["source_intent_run_id"]),
        )
        layer = InterestIntentLayerService(self.session).create_layer(
            context_id=context_id,
            actor=actor,
            name=f"AI-фильтр от {utc_now().strftime('%d.%m.%Y %H:%M')}",
            description=(
                "Повторная фильтрация намерений, созданная из одобренных AI-рекомендаций "
                f"по ручной разметке run {validation_run_id}."
            ),
            metadata_json={
                "source": "interest_intent_validation",
                "validation_run_id": validation_run_id,
                "base_intent_layer_id": base_layer["id"],
                "approved_recommendation_ids": [row["id"] for row in recommendations],
                **review_exclusions,
            },
            **values,
        )
        now = utc_now()
        recommendation_ids = [row["id"] for row in recommendations]
        self.session.execute(
            update(interest_intent_validation_recommendations_table)
            .where(interest_intent_validation_recommendations_table.c.id.in_(recommendation_ids))
            .values(status="applied", applied_at=now, updated_at=now)
        )
        self.session.execute(
            update(interest_intent_validation_runs_table)
            .where(interest_intent_validation_runs_table.c.id == validation_run_id)
            .values(created_layer_id=layer.id, updated_at=now)
        )
        self.session.commit()
        return {"layer": layer.as_jsonable(), "applied_recommendation_ids": recommendation_ids}

    def create_layer_from_source_run_approved(
        self,
        source_intent_run_id: str,
        *,
        context_id: str,
        actor: str,
    ) -> dict[str, Any]:
        source_intent_run = self._intent_run(context_id, source_intent_run_id)
        if source_intent_run is None:
            raise KeyError(source_intent_run_id)
        run_ids_query = (
            select(interest_intent_validation_runs_table.c.id)
            .where(interest_intent_validation_runs_table.c.context_id == context_id)
            .where(
                interest_intent_validation_runs_table.c.source_intent_run_id
                == source_intent_run_id
            )
            .where(interest_intent_validation_runs_table.c.status == "succeeded")
        )
        recommendations = [
            dict(row)
            for row in self.session.execute(
                select(interest_intent_validation_recommendations_table)
                .where(
                    interest_intent_validation_recommendations_table.c.validation_run_id.in_(
                        run_ids_query
                    )
                )
                .where(interest_intent_validation_recommendations_table.c.status == "approved")
                .order_by(interest_intent_validation_recommendations_table.c.created_at)
            )
            .mappings()
            .all()
        ]
        existing_layer = self._latest_batch_layer_for_source_run(
            context_id=context_id,
            source_intent_run_id=source_intent_run_id,
        )
        if not recommendations:
            if existing_layer is not None:
                metadata = dict(existing_layer.get("metadata_json") or {})
                return {
                    "layer": dict(existing_layer),
                    "applied_recommendation_ids": _string_list(
                        metadata.get("approved_recommendation_ids")
                    ),
                    "validation_run_ids": _string_list(metadata.get("batch_validation_run_ids")),
                    "reused": True,
                }
            raise ValueError("Нет одобренных рекомендаций для создания слоя")

        base_layer = self._layer(str(source_intent_run["intent_layer_id"]))
        values = self._layer_values_with_recommendations(base_layer, recommendations)
        review_exclusions = self._incorrect_review_exclusions(
            context_id=context_id,
            source_intent_run_id=source_intent_run_id,
        )
        validation_run_ids = _merge_lists(
            [],
            [str(row["validation_run_id"]) for row in recommendations],
        )
        layer = InterestIntentLayerService(self.session).create_layer(
            context_id=context_id,
            actor=actor,
            name=f"AI-фильтр по всем пачкам от {utc_now().strftime('%d.%m.%Y %H:%M')}",
            description=(
                "Повторная фильтрация намерений, созданная из всех одобренных "
                f"AI-рекомендаций по batch-разметке source run {source_intent_run_id}."
            ),
            metadata_json={
                "source": "interest_intent_validation_batches",
                "source_intent_run_id": source_intent_run_id,
                "base_intent_layer_id": base_layer["id"],
                "approved_recommendation_ids": [row["id"] for row in recommendations],
                "batch_validation_run_ids": validation_run_ids,
                **review_exclusions,
            },
            **values,
        )
        now = utc_now()
        recommendation_ids = [row["id"] for row in recommendations]
        self.session.execute(
            update(interest_intent_validation_recommendations_table)
            .where(interest_intent_validation_recommendations_table.c.id.in_(recommendation_ids))
            .values(status="applied", applied_at=now, updated_at=now)
        )
        self.session.execute(
            update(interest_intent_validation_runs_table)
            .where(interest_intent_validation_runs_table.c.id.in_(validation_run_ids))
            .values(created_layer_id=layer.id, updated_at=now)
        )
        self.session.commit()
        return {
            "layer": layer.as_jsonable(),
            "applied_recommendation_ids": recommendation_ids,
            "validation_run_ids": validation_run_ids,
            "reused": False,
        }

    def ensure_created_layer_review_exclusions(
        self,
        validation_run_id: str,
        *,
        context_id: str,
    ) -> dict[str, Any]:
        run = self._validation_run(validation_run_id, context_id=context_id)
        if run is None:
            raise KeyError(validation_run_id)
        layer_id = run["created_layer_id"]
        if not layer_id:
            raise ValueError("Сначала создайте AI-фильтр")
        layer = self._layer(str(layer_id))
        metadata = dict(layer.get("metadata_json") or {})
        review_exclusions = self._incorrect_review_exclusions(
            context_id=context_id,
            source_intent_run_id=str(run["source_intent_run_id"]),
        )
        changed = False
        for key, values in review_exclusions.items():
            if isinstance(values, list):
                existing = [str(item) for item in metadata.get(key, []) if str(item)]
                merged = _merge_lists(existing, [str(item) for item in values if str(item)])
                if merged != existing:
                    metadata[key] = merged
                    changed = True
                continue
            if metadata.get(key) != values:
                metadata[key] = values
                changed = True
        if changed:
            self.session.execute(
                update(interest_intent_layers_table)
                .where(interest_intent_layers_table.c.id == layer_id)
                .values(metadata_json=metadata, updated_at=utc_now())
            )
            self.session.commit()
        return metadata

    def preview_changes(
        self,
        *,
        match_rows: list[dict[str, Any]],
        reviews_by_match_id: dict[str, dict[str, Any]],
        proposed_changes: dict[str, Any],
        prepared_texts: dict[int, _PreparedMessageText] | None = None,
    ) -> dict[str, Any]:
        proposed_changes = _effective_proposed_changes(proposed_changes)
        removed: list[dict[str, Any]] = []
        exclude_lemma_rules = _compile_lemma_rules(_string_list(proposed_changes.get("exclude_lemmas")))
        exclude_phrase_rules = _compile_phrase_rules(
            _string_list(proposed_changes.get("exclude_phrases"))
        )
        semantic_negative_examples = _string_list(proposed_changes.get("semantic_negative_examples"))
        semantic_negative_threshold = _optional_float(
            proposed_changes.get("semantic_negative_threshold")
        ) or 0.78
        semantic_embedder = (
            LocalHashingEmbedder(dimensions=DEFAULT_EMBEDDING_DIMENSIONS)
            if semantic_negative_examples
            else None
        )
        semantic_vectors = (
            semantic_embedder.embed_texts(semantic_negative_examples)
            if semantic_embedder is not None
            else []
        )
        exclude_patterns = _string_list(proposed_changes.get("exclude_patterns"))
        exclude_core_names = {_fold(item) for item in _string_list(proposed_changes.get("exclude_core_names"))}
        min_score = _optional_float(proposed_changes.get("min_score"))
        compiled_patterns = _compile_patterns(exclude_patterns)
        for row in match_rows:
            reasons = []
            prepared = (prepared_texts or {}).get(int(row["telegram_message_id"])) or _prepared_from_raw(
                str(row.get("message_text") or "")
            )
            text = prepared.search_text
            core_name = _fold(row.get("canonical_name"))
            if exclude_core_names and core_name in exclude_core_names:
                reasons.append("exclude_core_name")
            for source in _lemma_rule_hits(exclude_lemma_rules, prepared):
                reasons.append(f"exclude_lemma:{source}")
            for source in _phrase_rule_hits(exclude_phrase_rules, prepared):
                reasons.append(f"exclude_phrase:{source}")
            if semantic_embedder is not None and semantic_vectors:
                vector = semantic_embedder.embed_texts([prepared.search_text])[0]
                for example, example_vector in zip(
                    semantic_negative_examples,
                    semantic_vectors,
                    strict=False,
                ):
                    score = _dot(vector, example_vector)
                    if score >= semantic_negative_threshold:
                        reasons.append(f"semantic_negative:{example}:{score:.3f}")
            for source, pattern in compiled_patterns:
                if pattern.search(text):
                    reasons.append(f"advanced_regex:{source}")
            if min_score is not None and float(row.get("score") or 0) < min_score:
                reasons.append("min_score")
            if reasons:
                removed.append({**row, "_remove_reasons": reasons})
        removed_ids = {str(row["id"]) for row in removed}
        correct_removed = sum(
            1
            for match_id, review in reviews_by_match_id.items()
            if match_id in removed_ids and review.get("decision") == "correct"
        )
        incorrect_removed = sum(
            1
            for match_id, review in reviews_by_match_id.items()
            if match_id in removed_ids and review.get("decision") == "incorrect"
        )
        return {
            "total_matches": len(match_rows),
            "removed_count": len(removed),
            "remaining_count": max(0, len(match_rows) - len(removed)),
            "reviewed_correct_removed": correct_removed,
            "reviewed_incorrect_removed": incorrect_removed,
            "removed_samples": [
                {
                    "id": row["id"],
                    "telegram_message_id": row["telegram_message_id"],
                    "canonical_name": row["canonical_name"],
                    "score": row["score"],
                    "message_text": _truncate(row.get("message_text"), 240),
                    "remove_reasons": row["_remove_reasons"],
                }
                for row in removed[:10]
            ],
        }

    def _layer_values_with_recommendations(self, base_layer: dict[str, Any], rows: Any) -> dict[str, Any]:
        values = {
            "include_patterns": _string_list(base_layer.get("include_patterns_json")),
            "context_patterns": _string_list(base_layer.get("context_patterns_json")),
            "exclude_patterns": _string_list(base_layer.get("exclude_patterns_json")),
            "exclude_lemmas": _string_list(base_layer.get("exclude_lemmas_json")),
            "exclude_phrases": _string_list(base_layer.get("exclude_phrases_json")),
            "semantic_negative_examples": _string_list(
                base_layer.get("semantic_negative_examples_json")
            ),
            "semantic_negative_threshold": _optional_float(
                base_layer.get("semantic_negative_threshold")
            )
            or 0.78,
            "include_categories": _string_list(base_layer.get("include_categories_json")),
            "exclude_categories": _string_list(base_layer.get("exclude_categories_json")),
            "include_core_names": _string_list(base_layer.get("include_core_names_json")),
            "exclude_core_names": _string_list(base_layer.get("exclude_core_names_json")),
            "require_include_match": bool(base_layer["require_include_match"]),
            "require_context_match": bool(base_layer["require_context_match"]),
            "min_score": float(base_layer["min_score"]),
            "max_results": int(base_layer["max_results"]),
            "broad_score_weight": float(base_layer["broad_score_weight"]),
            "intent_hit_weight": float(base_layer["intent_hit_weight"]),
        }
        for row in rows:
            changes = _effective_proposed_changes(row["proposed_changes_json"])
            values["exclude_lemmas"] = _merge_lists(
                values["exclude_lemmas"], _string_list(changes.get("exclude_lemmas"))
            )
            values["exclude_phrases"] = _merge_lists(
                values["exclude_phrases"], _string_list(changes.get("exclude_phrases"))
            )
            values["semantic_negative_examples"] = _merge_lists(
                values["semantic_negative_examples"],
                _string_list(changes.get("semantic_negative_examples")),
            )
            values["exclude_patterns"] = _merge_lists(
                values["exclude_patterns"], _string_list(changes.get("exclude_patterns"))
            )
            values["context_patterns"] = _merge_lists(
                values["context_patterns"], _string_list(changes.get("context_patterns"))
            )
            values["exclude_core_names"] = _merge_lists(
                values["exclude_core_names"], _string_list(changes.get("exclude_core_names"))
            )
            values["exclude_categories"] = _merge_lists(
                values["exclude_categories"], _string_list(changes.get("exclude_categories"))
            )
            min_score = _optional_float(changes.get("min_score"))
            if min_score is not None:
                values["min_score"] = max(values["min_score"], min_score)
            if changes.get("require_context_match") is True:
                values["require_context_match"] = True
            semantic_threshold = _optional_float(changes.get("semantic_negative_threshold"))
            if semantic_threshold is not None:
                values["semantic_negative_threshold"] = max(
                    values["semantic_negative_threshold"], semantic_threshold
                )
        return values

    def _incorrect_review_exclusions(
        self,
        *,
        context_id: str,
        source_intent_run_id: str,
    ) -> dict[str, Any]:
        reviews = self._latest_reviews_by_match_id(source_intent_run_id)
        if not reviews:
            return {
                "excluded_source_message_ids": [],
                "excluded_telegram_message_ids": [],
                "positive_source_message_ids": [],
                "positive_telegram_message_ids": [],
                "operator_semantic_negative_examples": [],
                "operator_semantic_positive_examples": [],
                "operator_review_counts": {"correct": 0, "incorrect": 0},
            }
        rows = self._intent_match_rows(context_id, source_intent_run_id)
        source_ids = []
        telegram_ids = []
        positive_source_ids = []
        positive_telegram_ids = []
        negative_examples = []
        positive_examples = []
        for row in rows:
            review = reviews.get(str(row["id"]))
            if not review:
                continue
            decision = review.get("decision")
            text = _truncate(row.get("message_text"), 800)
            if decision == "incorrect":
                source_ids.append(str(row["source_message_id"]))
                telegram_ids.append(str(row["telegram_message_id"]))
                if text:
                    negative_examples.append(text)
            elif decision == "correct":
                positive_source_ids.append(str(row["source_message_id"]))
                positive_telegram_ids.append(str(row["telegram_message_id"]))
                if text:
                    positive_examples.append(text)
        return {
            "excluded_source_message_ids": _merge_lists([], source_ids),
            "excluded_telegram_message_ids": _merge_lists([], telegram_ids),
            "positive_source_message_ids": _merge_lists([], positive_source_ids),
            "positive_telegram_message_ids": _merge_lists([], positive_telegram_ids),
            "operator_semantic_negative_examples": _merge_lists([], negative_examples),
            "operator_semantic_positive_examples": _merge_lists([], positive_examples),
            "operator_semantic_negative_threshold": 0.55,
            "operator_semantic_positive_margin": 0.03,
            "operator_positive_boost_threshold": 0.55,
            "operator_positive_score_boost": 0.08,
            "operator_review_counts": {
                "correct": len(_merge_lists([], positive_source_ids)),
                "incorrect": len(_merge_lists([], source_ids)),
            },
        }

    def _recommendation_rows_for_display(
        self,
        context_id: str,
        source_intent_run_id: str,
        rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not rows:
            return []
        match_rows: list[dict[str, Any]] | None = None
        reviews: dict[str, dict[str, Any]] | None = None
        prepared_texts: dict[int, _PreparedMessageText] | None = None
        result = []
        for row in rows:
            original_changes = row["proposed_changes_json"] if isinstance(row.get("proposed_changes_json"), dict) else {}
            effective_changes = _effective_proposed_changes(original_changes)
            if effective_changes != original_changes:
                if match_rows is None:
                    match_rows = self._intent_match_rows(context_id, source_intent_run_id)
                    reviews = self._latest_reviews_by_match_id(source_intent_run_id)
                    prepared_texts = self._prepared_texts_for_intent_run(
                        source_intent_run_id,
                        match_rows,
                    )
                row["proposed_changes_json"] = effective_changes
                row["impact_preview_json"] = self.preview_changes(
                    match_rows=match_rows,
                    reviews_by_match_id=reviews or {},
                    proposed_changes=effective_changes,
                    prepared_texts=prepared_texts,
                )
            result.append(row)
        return result

    def _latest_intent_run_for_created_layer(
        self,
        context_id: str,
        layer_id: str | None,
    ) -> dict[str, Any] | None:
        if not layer_id:
            return None
        row = (
            self.session.execute(
                select(interest_intent_analysis_runs_table)
                .where(interest_intent_analysis_runs_table.c.context_id == context_id)
                .where(interest_intent_analysis_runs_table.c.intent_layer_id == layer_id)
                .order_by(desc(interest_intent_analysis_runs_table.c.created_at))
                .limit(1)
            )
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None

    def _latest_batch_layer_for_source_run(
        self,
        *,
        context_id: str,
        source_intent_run_id: str,
    ) -> dict[str, Any] | None:
        rows = (
            self.session.execute(
                select(interest_intent_layers_table)
                .where(interest_intent_layers_table.c.context_id == context_id)
                .where(interest_intent_layers_table.c.status != "archived")
                .order_by(desc(interest_intent_layers_table.c.created_at))
                .limit(50)
            )
            .mappings()
            .all()
        )
        for row in rows:
            metadata = dict(row.get("metadata_json") or {})
            if (
                metadata.get("source") == "interest_intent_validation_batches"
                and metadata.get("source_intent_run_id") == source_intent_run_id
            ):
                return dict(row)
        return None

    def _context(self, context_id: str) -> dict[str, Any] | None:
        row = (
            self.session.execute(
                select(interest_contexts_table).where(interest_contexts_table.c.id == context_id)
            )
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None

    def _intent_run(self, context_id: str, run_id: str) -> dict[str, Any] | None:
        row = (
            self.session.execute(
                select(interest_intent_analysis_runs_table)
                .where(interest_intent_analysis_runs_table.c.id == run_id)
                .where(interest_intent_analysis_runs_table.c.context_id == context_id)
            )
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None

    def _layer(self, layer_id: str) -> dict[str, Any]:
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
        return dict(row)

    def _validation_run(self, run_id: str, *, context_id: str) -> dict[str, Any] | None:
        row = (
            self.session.execute(
                select(interest_intent_validation_runs_table)
                .where(interest_intent_validation_runs_table.c.id == run_id)
                .where(interest_intent_validation_runs_table.c.context_id == context_id)
            )
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None

    def _selected_run(self, context_id: str, run_id: str | None) -> IntentValidationRunRecord | None:
        query = select(interest_intent_validation_runs_table).where(
            interest_intent_validation_runs_table.c.context_id == context_id
        )
        if run_id:
            query = query.where(interest_intent_validation_runs_table.c.id == run_id)
        else:
            query = query.order_by(desc(interest_intent_validation_runs_table.c.created_at)).limit(1)
        row = self.session.execute(query).mappings().first()
        return _run_record(row) if row is not None else None

    def _recommendation(self, recommendation_id: str, *, context_id: str) -> dict[str, Any] | None:
        row = (
            self.session.execute(
                select(interest_intent_validation_recommendations_table)
                .where(interest_intent_validation_recommendations_table.c.id == recommendation_id)
                .where(interest_intent_validation_recommendations_table.c.context_id == context_id)
            )
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None

    def _active_brief(self, context_id: str) -> dict[str, Any] | None:
        row = (
            self.session.execute(
                select(interest_core_briefs_table)
                .where(interest_core_briefs_table.c.context_id == context_id)
                .where(interest_core_briefs_table.c.status == "active")
                .order_by(desc(interest_core_briefs_table.c.version))
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        return {"title": row["title"], "brief_text": row["brief_text"], "brief_json": row["brief_json"]}

    def _core_items(self, context_id: str) -> list[dict[str, Any]]:
        rows = (
            self.session.execute(
                select(
                    interest_core_items_table.c.canonical_name,
                    interest_core_items_table.c.category,
                    interest_core_items_table.c.description,
                    interest_core_items_table.c.synonyms_json,
                    interest_core_items_table.c.lead_signals_json,
                    interest_core_items_table.c.noise_patterns_json,
                )
                .where(interest_core_items_table.c.context_id == context_id)
                .where(interest_core_items_table.c.status == "active")
                .order_by(desc(interest_core_items_table.c.updated_at))
                .limit(120)
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    def _reviewed_matches(
        self,
        context_id: str,
        source_intent_run_id: str,
        *,
        max_reviews: int,
        review_offset: int = 0,
    ) -> list[dict[str, Any]]:
        reviews = self._latest_reviews_by_match_id(source_intent_run_id)
        if not reviews:
            return []
        rows = self._intent_match_rows(context_id, source_intent_run_id)
        prepared_texts = self._prepared_texts_for_intent_run(source_intent_run_id, rows)
        reviewed = []
        for row in rows:
            review = reviews.get(str(row["id"]))
            if not review:
                continue
            prepared = prepared_texts.get(int(row["telegram_message_id"]))
            reviewed.append(
                {
                    "match": {
                        "id": row["id"],
                        "telegram_message_id": row["telegram_message_id"],
                        "message_date": row["message_date"].isoformat()
                        if row.get("message_date")
                        else None,
                        "sender_id": row["sender_id"],
                        "canonical_name": row["canonical_name"],
                        "category": row["category"],
                        "score": row["score"],
                        "broad_score": row["broad_score"],
                        "message_text": row["message_text"],
                        "evidence_json": row["evidence_json"],
                        "prepared_text": {
                            "clean_text": prepared.clean_text,
                            "lemmas": list(prepared.lemmas),
                            "source": prepared.source,
                        }
                        if prepared is not None
                        else None,
                    },
                    "review": review,
                }
            )
        safe_offset = max(0, int(review_offset))
        safe_limit = max(1, int(max_reviews))
        return reviewed[safe_offset : safe_offset + safe_limit]

    def _intent_match_rows(self, context_id: str, run_id: str) -> list[dict[str, Any]]:
        rows = (
            self.session.execute(
                select(interest_intent_analysis_matches_table)
                .where(interest_intent_analysis_matches_table.c.context_id == context_id)
                .where(interest_intent_analysis_matches_table.c.run_id == run_id)
                .order_by(desc(interest_intent_analysis_matches_table.c.score))
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    def _prepared_texts_for_intent_run(
        self,
        source_intent_run_id: str,
        rows: list[dict[str, Any]],
    ) -> dict[int, _PreparedMessageText]:
        wanted_message_ids = {
            int(row["telegram_message_id"]) for row in rows if row.get("telegram_message_id") is not None
        }
        if not wanted_message_ids:
            return {}
        intent_run = self._intent_run_for_prepared_texts(source_intent_run_id)
        if intent_run is None:
            return {}
        broad_run = (
            self.session.execute(
                select(interest_core_analysis_runs_table).where(
                    interest_core_analysis_runs_table.c.id == intent_run["broad_analysis_run_id"]
                )
            )
            .mappings()
            .first()
        )
        if broad_run is None:
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
        text_normalization = dict(raw_run["metadata_json"] or {}).get("text_normalization")
        if not isinstance(text_normalization, dict) or not text_normalization.get("texts_parquet_path"):
            return {}
        texts_path = _resolve_path(text_normalization["texts_parquet_path"])
        if not texts_path.exists():
            return {}
        prepared: dict[int, _PreparedMessageText] = {}
        parquet_file = pq.ParquetFile(texts_path)
        for batch in parquet_file.iter_batches(batch_size=5000):
            for item in batch.to_pylist():
                telegram_message_id = item.get("telegram_message_id")
                if telegram_message_id is None:
                    continue
                message_id = int(telegram_message_id)
                if message_id not in wanted_message_ids:
                    continue
                lemmas = _json_list(item.get("lemmas_json"))
                prepared[message_id] = _PreparedMessageText(
                    raw_text=str(item.get("raw_text") or ""),
                    clean_text=str(item.get("clean_text") or ""),
                    lemmas_text=" ".join(str(lemma) for lemma in lemmas if str(lemma).strip()),
                    lemmas=tuple(_fold(lemma) for lemma in lemmas if _fold(lemma)),
                    source="text_normalization",
                )
        return prepared

    def _intent_run_for_prepared_texts(self, run_id: str) -> dict[str, Any] | None:
        row = (
            self.session.execute(
                select(interest_intent_analysis_runs_table).where(
                    interest_intent_analysis_runs_table.c.id == run_id
                )
            )
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None

    def _latest_reviews_by_match_id(self, run_id: str) -> dict[str, dict[str, Any]]:
        rows = (
            self.session.execute(
                select(feedback_events_table)
                .join(
                    interest_intent_analysis_matches_table,
                    interest_intent_analysis_matches_table.c.id == feedback_events_table.c.target_id,
                )
                .where(feedback_events_table.c.target_type == "interest_intent_match")
                .where(feedback_events_table.c.action.in_(list(REVIEW_ACTION_TO_DECISION)))
                .where(feedback_events_table.c.application_status != "ignored")
                .where(interest_intent_analysis_matches_table.c.run_id == run_id)
                .order_by(desc(feedback_events_table.c.created_at))
            )
            .mappings()
            .all()
        )
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            target_id = str(row["target_id"])
            if target_id in result:
                continue
            result[target_id] = {
                "id": row["id"],
                "decision": REVIEW_ACTION_TO_DECISION.get(str(row["action"]), "unknown"),
                "action": row["action"],
                "comment": row["comment"],
                "created_by": row["created_by"],
                "created_at": row["created_at"],
            }
        return result


def render_intent_validation_prompt(payload: dict[str, Any]) -> str:
    compact_payload = {
        "context": payload["context"],
        "brief": payload["brief"],
        "intent_layer": {
            key: payload["intent_layer"].get(key)
            for key in (
                "name",
                "description",
                "include_patterns_json",
                "context_patterns_json",
                "exclude_patterns_json",
                "exclude_lemmas_json",
                "exclude_phrases_json",
                "semantic_negative_examples_json",
                "semantic_negative_threshold",
                "include_categories_json",
                "exclude_categories_json",
                "include_core_names_json",
                "exclude_core_names_json",
                "require_include_match",
                "require_context_match",
                "min_score",
                "broad_score_weight",
                "intent_hit_weight",
            )
        },
        "core_items": payload["core_items"],
        "reviewed_matches": payload["reviewed_matches"],
    }
    return (
        "Нужно предложить повторную фильтрацию слоя намерений по ручной разметке оператора.\n"
        "Оператор помечает сообщения как correct/incorrect и оставляет комментарии.\n"
        "Цель: убрать типовые false positive, не потеряв правильные сообщения.\n\n"
        "Верни строго JSON-объект:\n"
        "{\n"
        '  "summary": {"diagnosis": string, "main_false_positive_patterns": [string], "risk_notes": [string]},\n'
        '  "recommendations": [\n'
        "    {\n"
        '      "type": "add_exclude_lemmas|add_exclude_phrase|add_semantic_negative_example|exclude_core_name|add_context_pattern|require_context_match|increase_min_score|advanced_regex|no_change",\n'
        '      "title": string,\n'
        '      "rationale": string,\n'
        '      "confidence": "high|medium|low",\n'
        '      "proposed_changes": {\n'
        '        "exclude_lemmas": [string],\n'
        '        "exclude_phrases": [string],\n'
        '        "semantic_negative_examples": [string],\n'
        '        "semantic_negative_threshold": number|null,\n'
        '        "exclude_patterns": [string],\n'
        '        "exclude_core_names": [string],\n'
        '        "exclude_categories": [string],\n'
        '        "context_patterns": [string],\n'
        '        "require_context_match": boolean|null,\n'
        '        "min_score": number|null\n'
        "      }\n"
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Правила:\n"
        "- Не предлагай широкие исключения, если они могут убрать correct-сообщения.\n"
        "- Если операторский комментарий объясняет, почему incorrect, используй его как главный сигнал.\n"
        "- Предпочитай exclude_lemmas и exclude_phrases: они применяются по Stage 2 lemmas/clean_text, а не regex.\n"
        "- semantic_negative_examples используй для типовых нерелевантных смыслов целыми короткими примерами.\n"
        "- exclude_patterns это advanced-regex fallback; используй только если lemma/phrase недостаточно.\n"
        "- Предпочитай конкретные предметные исключения широким словам типа нужно/помогите.\n"
        "- Если данных мало, верни no_change или low confidence.\n\n"
        f"Данные:\n{json.dumps(compact_payload, ensure_ascii=False, default=str)}"
    )


def normalize_intent_validation_response(value: dict[str, Any]) -> dict[str, Any]:
    raw_recommendations = value.get("recommendations")
    if not isinstance(raw_recommendations, list):
        raw_recommendations = []
    recommendations = []
    for index, raw in enumerate(raw_recommendations[:30], start=1):
        if not isinstance(raw, dict):
            continue
        proposed = raw.get("proposed_changes") if isinstance(raw.get("proposed_changes"), dict) else {}
        rec_type = str(raw.get("type") or "no_change").strip() or "no_change"
        title = str(raw.get("title") or rec_type).strip() or rec_type
        recommendations.append(
            {
                "index": index,
                "type": rec_type[:80],
                "title": title,
                "rationale": str(raw.get("rationale") or "").strip() or None,
                "confidence": _confidence(raw.get("confidence")),
                "proposed_changes": {
                    "exclude_lemmas": _string_list(proposed.get("exclude_lemmas")),
                    "exclude_phrases": _string_list(proposed.get("exclude_phrases")),
                    "semantic_negative_examples": _string_list(
                        proposed.get("semantic_negative_examples")
                    ),
                    "semantic_negative_threshold": _optional_float(
                        proposed.get("semantic_negative_threshold")
                    ),
                    "exclude_patterns": _string_list(proposed.get("exclude_patterns")),
                    "exclude_core_names": _string_list(proposed.get("exclude_core_names")),
                    "exclude_categories": _string_list(proposed.get("exclude_categories")),
                    "context_patterns": _string_list(proposed.get("context_patterns")),
                    "require_context_match": proposed.get("require_context_match")
                    if isinstance(proposed.get("require_context_match"), bool)
                    else None,
                    "min_score": _optional_float(proposed.get("min_score")),
                },
            }
        )
    if not recommendations:
        recommendations.append(
            {
                "index": 1,
                "type": "no_change",
                "title": "Недостаточно сигнала для изменения слоя",
                "rationale": "Модель не предложила безопасных изменений.",
                "confidence": "low",
                "proposed_changes": {},
            }
        )
    summary = value.get("summary") if isinstance(value.get("summary"), dict) else {}
    return {"summary": summary, "recommendations": recommendations}


def _run_record(row: Any) -> IntentValidationRunRecord:
    return IntentValidationRunRecord(**dict(row))


def _pagination(*, limit: int, offset: int, total: int) -> dict[str, Any]:
    return {"limit": limit, "offset": offset, "total": total, "has_more": offset + limit < total}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _merge_lists(left: list[str], right: list[str]) -> list[str]:
    result = list(left)
    seen = {item.casefold().strip() for item in result}
    for item in right:
        key = item.casefold().strip()
        if key and key not in seen:
            result.append(item)
            seen.add(key)
    return result


def _effective_proposed_changes(value: Any) -> dict[str, Any]:
    changes = dict(value) if isinstance(value, dict) else {}
    plain_exclusions, advanced_regex = _split_plain_and_regex(
        _string_list(changes.get("exclude_patterns"))
    )
    lemma_exclusions = []
    phrase_exclusions = []
    for item in plain_exclusions:
        if len(item.split()) <= 1:
            lemma_exclusions.append(item)
        else:
            phrase_exclusions.append(item)
    if lemma_exclusions:
        changes["exclude_lemmas"] = _merge_lists(
            _string_list(changes.get("exclude_lemmas")),
            lemma_exclusions,
        )
    if phrase_exclusions:
        changes["exclude_phrases"] = _merge_lists(
            _string_list(changes.get("exclude_phrases")),
            phrase_exclusions,
        )
    changes["exclude_patterns"] = advanced_regex
    return changes


def _split_plain_and_regex(values: list[str]) -> tuple[list[str], list[str]]:
    plain = []
    regex = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        if _looks_like_regex(text):
            regex.append(text)
        else:
            plain.append(text)
    return plain, regex


def _looks_like_regex(value: str) -> bool:
    return bool(re.search(r"[\\\[\]().|^$*+?{}]", value))


def _optional_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, number))


def _compile_patterns(values: list[str]) -> list[tuple[str, re.Pattern[str]]]:
    patterns = []
    for value in values:
        try:
            patterns.append((value, re.compile(value, re.IGNORECASE)))
        except re.error:
            patterns.append((value, re.compile(re.escape(value), re.IGNORECASE)))
    return patterns


def _dot(left: list[float], right: list[float]) -> float:
    return sum(float(a) * float(b) for a, b in zip(left, right, strict=False))


def _fold(value: Any) -> str:
    return str(value or "").casefold().replace("ё", "е").strip()


def _confidence(value: Any) -> str:
    text = str(value or "").casefold().strip()
    return text if text in {"high", "medium", "low"} else "medium"


def _truncate(value: Any, limit: int) -> str:
    text = str(value or "")
    return text if len(text) <= limit else f"{text[: limit - 1]}…"
