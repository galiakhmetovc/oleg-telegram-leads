"""Manual and LLM-generated interest-core briefs."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
from sqlalchemy import desc, func, insert, select, update
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.integrations.ai.chat import AiChatClient, AiChatMessage
from pur_leads.models.interest_contexts import interest_contexts_table
from pur_leads.models.interest_core_briefs import interest_core_briefs_table
from pur_leads.models.telegram_sources import (
    monitored_sources_table,
    telegram_raw_export_runs_table,
)
from pur_leads.services.audit import AuditService

GENERATE_INTEREST_CORE_BRIEF_JOB = "generate_interest_core_brief"
INTEREST_CORE_BRIEF_PROMPT_VERSION = "interest-core-brief-v1"
DEFAULT_MESSAGE_SAMPLE_LIMIT = 80
DEFAULT_ARTIFACT_SAMPLE_LIMIT = 80
DEFAULT_ENTITY_SAMPLE_LIMIT = 120


@dataclass(frozen=True)
class InterestCoreBriefRecord:
    id: str
    context_id: str
    version: int
    status: str
    source: str
    title: str | None
    brief_text: str
    brief_json: Any
    source_refs_json: Any
    prompt_version: str | None
    prompt_text: str | None
    request_json: Any
    response_json: Any
    parsed_response_json: Any
    provider: str | None
    model: str | None
    model_profile: str | None
    ai_provider_account_id: str | None
    ai_model_id: str | None
    ai_model_profile_id: str | None
    ai_agent_route_id: str | None
    generation_status: str | None
    error: str | None
    created_by: str
    activated_by: str | None
    activated_at: Any
    created_at: Any
    updated_at: Any

    def as_jsonable(self) -> dict[str, Any]:
        return asdict(self)


class InterestCoreBriefService:
    """Persist and generate stable business context for an interest core."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.audit = AuditService(session)

    def list_briefs(self, context_id: str, *, limit: int = 20) -> list[InterestCoreBriefRecord]:
        rows = (
            self.session.execute(
                select(interest_core_briefs_table)
                .where(interest_core_briefs_table.c.context_id == context_id)
                .order_by(desc(interest_core_briefs_table.c.version))
                .limit(max(1, limit))
            )
            .mappings()
            .all()
        )
        return [_record(row) for row in rows]

    def active_brief(self, context_id: str) -> InterestCoreBriefRecord | None:
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
        return _record(row) if row is not None else None

    def latest_payload(self, context_id: str, *, limit: int = 20) -> dict[str, Any]:
        records = self.list_briefs(context_id, limit=limit)
        active = next((record for record in records if record.status == "active"), None)
        if active is None:
            active = self.active_brief(context_id)
        return {
            "active": active.as_jsonable() if active is not None else None,
            "items": [record.as_jsonable() for record in records],
        }

    def create_manual(
        self,
        context_id: str,
        *,
        brief_text: str,
        actor: str,
        title: str | None = None,
        brief_json: dict[str, Any] | None = None,
        activate: bool = True,
    ) -> InterestCoreBriefRecord:
        self._require_context(context_id)
        normalized_text = " ".join(brief_text.split())
        if not normalized_text:
            raise ValueError("brief_text is required")
        now = utc_now()
        record = self._insert_brief(
            context_id=context_id,
            version=self._next_version(context_id),
            status="draft",
            source="manual",
            title=title.strip() if title and title.strip() else None,
            brief_text=normalized_text,
            brief_json=brief_json,
            source_refs_json={"source": "manual"},
            prompt_version=None,
            prompt_text=None,
            request_json=None,
            response_json=None,
            parsed_response_json=None,
            provider=None,
            model=None,
            model_profile=None,
            ai_provider_account_id=None,
            ai_model_id=None,
            ai_model_profile_id=None,
            ai_agent_route_id=None,
            generation_status=None,
            error=None,
            created_by=actor,
            created_at=now,
        )
        if activate:
            record = self.activate(context_id, record.id, actor=actor)
        self.audit.record_change(
            actor=actor,
            action="interest_core_brief.create_manual",
            entity_type="interest_core_brief",
            entity_id=record.id,
            old_value_json=None,
            new_value_json=record.as_jsonable(),
        )
        return record

    def activate(
        self,
        context_id: str,
        brief_id: str,
        *,
        actor: str,
    ) -> InterestCoreBriefRecord:
        self._require_context(context_id)
        existing = self._get(brief_id)
        if existing is None or existing.context_id != context_id:
            raise KeyError(brief_id)
        now = utc_now()
        self.session.execute(
            update(interest_core_briefs_table)
            .where(interest_core_briefs_table.c.context_id == context_id)
            .where(interest_core_briefs_table.c.status == "active")
            .where(interest_core_briefs_table.c.id != brief_id)
            .values(status="archived", updated_at=now)
        )
        self.session.execute(
            update(interest_core_briefs_table)
            .where(interest_core_briefs_table.c.id == brief_id)
            .values(
                status="active",
                activated_by=actor,
                activated_at=now,
                updated_at=now,
            )
        )
        self.session.commit()
        record = self._get(brief_id)
        if record is None:
            raise KeyError(brief_id)
        return record

    def generate_from_sources(
        self,
        context_id: str,
        *,
        client: AiChatClient,
        actor: str,
        provider: str,
        model: str,
        model_profile: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        activate: bool = True,
        ai_provider_account_id: str | None = None,
        ai_model_id: str | None = None,
        ai_model_profile_id: str | None = None,
        ai_agent_route_id: str | None = None,
    ) -> InterestCoreBriefRecord:
        return asyncio.run(
            self.generate_from_sources_async(
                context_id,
                client=client,
                actor=actor,
                provider=provider,
                model=model,
                model_profile=model_profile,
                max_tokens=max_tokens,
                temperature=temperature,
                activate=activate,
                ai_provider_account_id=ai_provider_account_id,
                ai_model_id=ai_model_id,
                ai_model_profile_id=ai_model_profile_id,
                ai_agent_route_id=ai_agent_route_id,
            )
        )

    async def generate_from_sources_async(
        self,
        context_id: str,
        *,
        client: AiChatClient,
        actor: str,
        provider: str,
        model: str,
        model_profile: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        activate: bool = True,
        ai_provider_account_id: str | None = None,
        ai_model_id: str | None = None,
        ai_model_profile_id: str | None = None,
        ai_agent_route_id: str | None = None,
    ) -> InterestCoreBriefRecord:
        context = self._require_context(context_id)
        payload = self.build_generation_payload(context_id)
        prompt_text = render_interest_core_brief_prompt(
            context_name=str(context["name"]),
            context_description=context.get("description"),
            payload=payload,
        )
        messages = [
            AiChatMessage(
                role="system",
                content=(
                    "Ты формируешь проверяемый бизнес-бриф ядра интересов. "
                    "Отвечай только валидным JSON без markdown."
                ),
            ),
            AiChatMessage(role="user", content=prompt_text),
        ]
        request_json = {
            "model": model,
            "messages": [
                {"role": message.role, "content": message.content} for message in messages
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "prompt_version": INTEREST_CORE_BRIEF_PROMPT_VERSION,
            "source_refs": payload["source_refs"],
        }
        completion = await client.complete(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        response_json = {
            "content": completion.content,
            "model": completion.model,
            "request_id": completion.request_id,
            "usage": completion.usage,
            "raw_response": completion.raw_response,
        }
        parsed = parse_interest_core_brief_response(completion.content)
        brief_text = brief_text_from_json(parsed)
        now = utc_now()
        record = self._insert_brief(
            context_id=context_id,
            version=self._next_version(context_id),
            status="draft",
            source="llm_generated",
            title=str(parsed.get("subject_name") or context["name"])[:200],
            brief_text=brief_text,
            brief_json=parsed,
            source_refs_json=payload["source_refs"],
            prompt_version=INTEREST_CORE_BRIEF_PROMPT_VERSION,
            prompt_text=prompt_text,
            request_json=request_json,
            response_json=response_json,
            parsed_response_json=parsed,
            provider=provider,
            model=model,
            model_profile=model_profile,
            ai_provider_account_id=ai_provider_account_id,
            ai_model_id=ai_model_id,
            ai_model_profile_id=ai_model_profile_id,
            ai_agent_route_id=ai_agent_route_id,
            generation_status="succeeded",
            error=None,
            created_by=actor,
            created_at=now,
        )
        if activate:
            record = self.activate(context_id, record.id, actor=actor)
        self.audit.record_change(
            actor=actor,
            action="interest_core_brief.generate",
            entity_type="interest_core_brief",
            entity_id=record.id,
            old_value_json=None,
            new_value_json={
                "context_id": context_id,
                "version": record.version,
                "model": model,
                "model_profile": model_profile,
                "source_refs": payload["source_refs"],
            },
        )
        return record

    def build_generation_payload(self, context_id: str) -> dict[str, Any]:
        self._require_context(context_id)
        raw_runs = self._raw_export_runs(context_id)
        if not raw_runs:
            raise ValueError("Нет успешных raw-выгрузок для формирования брифа")
        messages: list[dict[str, Any]] = []
        artifacts: list[dict[str, Any]] = []
        entities: list[dict[str, Any]] = []
        source_summaries: list[dict[str, Any]] = []
        for run in raw_runs:
            source_summaries.append(
                {
                    "raw_export_run_id": run["id"],
                    "source_ref": run["source_ref"],
                    "source_kind": run["source_kind"],
                    "title": run["title"],
                    "username": run["username"],
                    "message_count": run["message_count"],
                    "attachment_count": run["attachment_count"],
                }
            )
            messages.extend(_sample_text_rows(run, limit=DEFAULT_MESSAGE_SAMPLE_LIMIT))
            artifacts.extend(_sample_artifact_rows(run, limit=DEFAULT_ARTIFACT_SAMPLE_LIMIT))
            entities.extend(_sample_ranked_entities(run, limit=DEFAULT_ENTITY_SAMPLE_LIMIT))
        messages = _dedupe_by(messages, "source_ref")[:DEFAULT_MESSAGE_SAMPLE_LIMIT]
        artifacts = _dedupe_by(artifacts, "source_ref")[:DEFAULT_ARTIFACT_SAMPLE_LIMIT]
        entities = _dedupe_by(entities, "normalized_text")[:DEFAULT_ENTITY_SAMPLE_LIMIT]
        return {
            "sources": source_summaries,
            "messages": messages,
            "artifacts": artifacts,
            "ranked_entities": entities,
            "source_refs": {
                "raw_export_run_ids": [str(run["id"]) for run in raw_runs],
                "message_refs": [row["source_ref"] for row in messages[:40]],
                "artifact_refs": [row["source_ref"] for row in artifacts[:40]],
                "ranked_entity_count": len(entities),
            },
        }

    def _insert_brief(self, **values: Any) -> InterestCoreBriefRecord:
        brief_id = new_id()
        created_at = values.pop("created_at")
        self.session.execute(
            insert(interest_core_briefs_table).values(
                id=brief_id,
                **values,
                activated_by=None,
                activated_at=None,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        self.session.commit()
        record = self._get(brief_id)
        if record is None:
            raise KeyError(brief_id)
        return record

    def _get(self, brief_id: str) -> InterestCoreBriefRecord | None:
        row = (
            self.session.execute(
                select(interest_core_briefs_table).where(
                    interest_core_briefs_table.c.id == brief_id
                )
            )
            .mappings()
            .first()
        )
        return _record(row) if row is not None else None

    def _next_version(self, context_id: str) -> int:
        value = self.session.execute(
            select(func.max(interest_core_briefs_table.c.version)).where(
                interest_core_briefs_table.c.context_id == context_id
            )
        ).scalar_one()
        return int(value or 0) + 1

    def _require_context(self, context_id: str) -> dict[str, Any]:
        row = (
            self.session.execute(
                select(interest_contexts_table).where(interest_contexts_table.c.id == context_id)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise KeyError(context_id)
        return dict(row)

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


def render_interest_core_brief_prompt(
    *,
    context_name: str,
    context_description: str | None,
    payload: dict[str, Any],
) -> str:
    return (
        "Сформируй предварительный бриф ядра интересов для дальнейшего поиска лидов.\n"
        "Бриф должен описывать не только товары, а общий контекст интересов пользователя: "
        "чем занимается проект, какие темы важны, что считается потенциальным лидом, "
        "что похоже на поддержку/повод связаться, а что является шумом.\n\n"
        f"Название контекста: {context_name}\n"
        f"Описание от пользователя: {context_description or 'не задано'}\n\n"
        "Источник данных ниже: сообщения Telegram, тексты документов/страниц и, если уже есть, "
        "локально ранжированные кандидаты сущностей. Используй только эту информацию. "
        "Если вывод является гипотезой, явно помести его в hypotheses или uncertain_assumptions.\n\n"
        "Верни строго JSON-объект со схемой:\n"
        "{\n"
        '  "subject_name": string,\n'
        '  "short_description": string,\n'
        '  "business_focus": string[],\n'
        '  "products_and_services": string[],\n'
        '  "customer_segments": string[],\n'
        '  "important_domains": string[],\n'
        '  "lead_interest_criteria": string[],\n'
        '  "support_interest_criteria": string[],\n'
        '  "noise_criteria": string[],\n'
        '  "hypotheses": string[],\n'
        '  "source_evidence": [{"source_ref": string, "quote": string, "why": string}],\n'
        '  "uncertain_assumptions": string[]\n'
        "}\n\n"
        "ДАННЫЕ:\n"
        f"{json.dumps(_prompt_payload(payload), ensure_ascii=False, indent=2)}"
    )


def parse_interest_core_brief_response(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.casefold().startswith("json"):
            text = text[4:].strip()
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("LLM returned non-object JSON")
    return parsed


def brief_text_from_json(value: dict[str, Any]) -> str:
    lines: list[str] = []
    subject = _string_value(value.get("subject_name"))
    description = _string_value(value.get("short_description"))
    if subject:
        lines.append(subject)
    if description:
        lines.append(description)
    sections = [
        ("Фокус", value.get("business_focus")),
        ("Продукты и услуги", value.get("products_and_services")),
        ("Клиенты", value.get("customer_segments")),
        ("Темы", value.get("important_domains")),
        ("Что считать лидом", value.get("lead_interest_criteria")),
        ("Поддержка и поводы связаться", value.get("support_interest_criteria")),
        ("Шум", value.get("noise_criteria")),
        ("Гипотезы", value.get("hypotheses")),
        ("Непроверенные допущения", value.get("uncertain_assumptions")),
    ]
    for title, raw_items in sections:
        items = _string_list(raw_items)
        if items:
            lines.append(f"{title}: " + "; ".join(items))
    return "\n".join(lines).strip() or json.dumps(value, ensure_ascii=False)


def _record(row: Any) -> InterestCoreBriefRecord:
    return InterestCoreBriefRecord(**dict(row))


def _sample_text_rows(run: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    path = _metadata_path(run, "text_normalization", "texts_parquet_path")
    if path is None or not path.exists():
        return []
    rows = [
        _message_prompt_row(row)
        for row in pq.read_table(path).to_pylist()
        if row.get("has_text") and str(row.get("clean_text") or "").strip()
    ]
    rows.sort(key=lambda row: (-int(row.get("token_count") or 0), row["source_ref"]))
    return rows[:limit]


def _sample_artifact_rows(run: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    path = _metadata_path(run, "artifact_texts", "texts_parquet_path")
    if path is None or not path.exists():
        return []
    rows = [
        _artifact_prompt_row(row)
        for row in pq.read_table(path).to_pylist()
        if row.get("has_text") and str(row.get("clean_text") or "").strip()
    ]
    rows.sort(key=lambda row: (-int(row.get("token_count") or 0), row["source_ref"]))
    return rows[:limit]


def _sample_ranked_entities(run: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    path = _metadata_path(run, "entity_ranking", "ranked_entities_parquet_path")
    if path is None or not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for row in pq.read_table(path).to_pylist():
        status = str(row.get("ranking_status") or "")
        if status not in {"promote_candidate", "review_candidate"}:
            continue
        rows.append(
            {
                "normalized_text": str(row.get("normalized_text") or ""),
                "canonical_text": str(row.get("canonical_text") or ""),
                "score": float(row.get("score") or 0.0),
                "ranking_status": status,
                "reasons": _json_list(row.get("reasons_json")),
                "source_refs": _json_list(row.get("source_refs_json")),
            }
        )
    rows.sort(key=lambda row: (-float(row["score"]), row["normalized_text"]))
    return rows[:limit]


def _message_prompt_row(row: dict[str, Any]) -> dict[str, Any]:
    source_ref = _telegram_source_ref(
        row.get("message_url"),
        row.get("monitored_source_id"),
        row.get("telegram_message_id"),
    )
    return {
        "source_ref": source_ref,
        "telegram_message_id": row.get("telegram_message_id"),
        "date": row.get("date"),
        "text": _truncate(row.get("raw_text") or row.get("clean_text"), 1200),
        "clean_text": _truncate(row.get("clean_text"), 1200),
        "token_count": int(row.get("token_count") or 0),
    }


def _artifact_prompt_row(row: dict[str, Any]) -> dict[str, Any]:
    message_ref = _telegram_source_ref(
        row.get("message_url"),
        row.get("monitored_source_id"),
        row.get("telegram_message_id"),
    )
    source_ref = f"{message_ref}:artifact:{row.get('artifact_id') or row.get('chunk_index')}"
    return {
        "source_ref": source_ref,
        "telegram_message_id": row.get("telegram_message_id"),
        "artifact_kind": row.get("artifact_kind"),
        "file_name": row.get("file_name"),
        "source_url": row.get("source_url"),
        "title": row.get("title"),
        "text": _truncate(row.get("raw_text") or row.get("clean_text"), 1600),
        "clean_text": _truncate(row.get("clean_text"), 1600),
        "token_count": int(row.get("token_count") or 0),
    }


def _metadata_path(run: dict[str, Any], stage: str, key: str) -> Path | None:
    metadata = run.get("metadata_json")
    if not isinstance(metadata, dict):
        return None
    stage_payload = metadata.get(stage)
    if not isinstance(stage_payload, dict):
        return None
    raw_path = stage_payload.get(key)
    if not raw_path:
        return None
    path = Path(str(raw_path))
    return path if path.is_absolute() else Path(".") / path


def _telegram_source_ref(message_url: Any, source_id: Any, message_id: Any) -> str:
    if isinstance(message_url, str) and message_url.strip():
        return message_url.strip()
    return f"telegram:{source_id}:{message_id}"


def _prompt_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "sources": payload.get("sources", []),
        "messages": payload.get("messages", []),
        "artifacts": payload.get("artifacts", []),
        "ranked_entities": payload.get("ranked_entities", []),
    }


def _dedupe_by(rows: Sequence[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        value = str(row.get(key) or "")
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(row)
    return result


def _json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _string_value(value: Any) -> str:
    return str(value).strip() if isinstance(value, str) and value.strip() else ""


def _truncate(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]
