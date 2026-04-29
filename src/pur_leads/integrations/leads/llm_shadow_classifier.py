"""LLM-backed lead classifier for shadow-mode evaluation."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pur_leads.integrations.ai.chat import AiChatClient, AiChatMessage
from pur_leads.workers.runtime import (
    LeadClassifierMatch,
    LeadClassifierResult,
    LeadMessageForClassification,
)

PROMPT_VERSION = "lead-shadow-v1"


class LlmLeadShadowClassifier:
    prompt_version = PROMPT_VERSION

    def __init__(
        self,
        *,
        client: AiChatClient,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> None:
        self.client = client
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.prompt_hash = _prompt_hash()
        self.last_token_usage_json: dict[str, Any] | None = None

    async def classify_message_batch(
        self,
        *,
        messages: list[LeadMessageForClassification],
        payload: dict[str, Any],
    ) -> list[LeadClassifierResult]:
        self.last_token_usage_json = None
        completion = await self.client.complete(
            messages=_prompt_messages(messages),
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        self.last_token_usage_json = {
            **completion.usage,
            "request_id": completion.request_id,
            "model": completion.model,
        }
        parsed = _parse_json_object(completion.content)
        return _results_from_payload(
            parsed,
            known_message_ids={message.source_message_id for message in messages},
            detection_mode=_detection_mode(payload),
        )


def _prompt_messages(messages: list[LeadMessageForClassification]) -> list[AiChatMessage]:
    system = (
        "Return strict JSON only. You are a lead-detection evaluator for PUR, a smart-home, "
        "security, CCTV, intercom, access-control, networking, electrical automation, and "
        "installation/support business. Classify whether each Telegram message is a commercial "
        "opportunity for selling equipment, installation, configuration, support, or follow-up. "
        "Use lead when the user appears to need buying/installing/configuring/support help now. "
        "Use maybe when operator review is needed. Use not_lead for ads, sellers, pure expert "
        "discussion, already solved cases, spam, or unrelated chatter. "
        'Schema: {"items":[{"source_message_id":"exact id","decision":"lead|maybe|not_lead",'
        '"confidence":0.0,"commercial_value_score":0.0,"negative_score":0.0,'
        '"reason":"short reason","signals":["..."],"negative_signals":["..."],'
        '"matched_text":["short source fragments"],"notify_reason":"..."}]}. '
        "Return one item for every input message and do not invent product facts."
    )
    payload = {
        "messages": [
            {
                "source_message_id": message.source_message_id,
                "telegram_message_id": message.telegram_message_id,
                "sender_id": message.sender_id,
                "message_date": (
                    message.message_date.isoformat()
                    if hasattr(message.message_date, "isoformat")
                    else str(message.message_date)
                ),
                "text": message.message_text or "",
            }
            for message in messages
        ]
    }
    user = json.dumps(payload, ensure_ascii=False)
    return [AiChatMessage(role="system", content=system), AiChatMessage(role="user", content=user)]


def _parse_json_object(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < start:
        raise ValueError("LLM lead shadow classifier expected valid JSON object")
    try:
        parsed = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError("LLM lead shadow classifier expected valid JSON object") from exc
    if not isinstance(parsed, dict):
        raise ValueError("LLM lead shadow classifier expected valid JSON object")
    return parsed


def _results_from_payload(
    payload: dict[str, Any],
    *,
    known_message_ids: set[str],
    detection_mode: str,
) -> list[LeadClassifierResult]:
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("LLM lead shadow classifier JSON must contain items array")
    results: list[LeadClassifierResult] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        result = _result_from_raw(
            raw, known_message_ids=known_message_ids, detection_mode=detection_mode
        )
        if result is not None:
            results.append(result)
    return results


def _result_from_raw(
    raw: dict[str, Any],
    *,
    known_message_ids: set[str],
    detection_mode: str,
) -> LeadClassifierResult | None:
    source_message_id = _string(raw.get("source_message_id"))
    if not source_message_id or source_message_id not in known_message_ids:
        return None
    decision = _decision(raw.get("decision"))
    confidence = _score(raw.get("confidence"), default=0.5)
    commercial_value_score = _score(raw.get("commercial_value_score"), default=0.0)
    negative_score = _score(raw.get("negative_score"), default=0.0)
    signals = _string_list(raw.get("signals"))
    negative_signals = _string_list(raw.get("negative_signals"))
    matched_text = _string_list(raw.get("matched_text")) or signals[:5]
    matches = [
        LeadClassifierMatch(
            match_type="llm_signal",
            matched_text=value,
            score=confidence,
        )
        for value in matched_text[:5]
    ]
    return LeadClassifierResult(
        source_message_id=source_message_id,
        classifier_version_id="",
        decision=decision,
        detection_mode=detection_mode,
        confidence=confidence,
        commercial_value_score=commercial_value_score,
        negative_score=negative_score,
        high_value_signals_json=signals,
        negative_signals_json=negative_signals,
        notify_reason=_optional_string(raw.get("notify_reason")),
        reason=_optional_string(raw.get("reason")),
        matches=matches,
    )


def _detection_mode(payload: dict[str, Any]) -> str:
    value = payload.get("detection_mode")
    return value if isinstance(value, str) and value else "live"


def _decision(value: Any) -> str:
    decision = _string(value).casefold()
    if decision in {"lead", "maybe", "not_lead"}:
        return decision
    raise ValueError(f"LLM lead shadow classifier returned unsupported decision: {value!r}")


def _score(value: Any, *, default: float) -> float:
    if value is None or isinstance(value, bool):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, parsed))


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
    return result


def _optional_string(value: Any) -> str | None:
    text = _string(value).strip()
    return text or None


def _string(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _prompt_hash() -> str:
    return hashlib.sha256(PROMPT_VERSION.encode("utf-8")).hexdigest()
