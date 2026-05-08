from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from string import Formatter
from uuid import UUID

from app.domain.enrichment import TextEnrichmentResult
from app.domain.notifications import NotificationRoute
from app.domain.notifications import NotificationRouteConditions


@dataclass(frozen=True)
class NotificationMessageContext:
    source_message_id: UUID | None = None
    enrichment_job_id: UUID | None = None
    telegram_message_url: str | None = None
    app_message_url: str | None = None


def match_notification_routes(
    routes: list[NotificationRoute],
    result: TextEnrichmentResult,
) -> list[NotificationRoute]:
    return [
        route
        for route in sorted(routes, key=lambda item: item.priority, reverse=True)
        if route.enabled and _route_matches(route, result)
    ]


def render_notification_message(
    template: str,
    result: TextEnrichmentResult,
    context: NotificationMessageContext | None = None,
) -> str:
    values = _template_values(result, context)
    safe_template = _safe_template(template, values)
    rendered = safe_template.format(**values)
    return _append_context_links(rendered, context, template)


def _route_matches(route: NotificationRoute, result: TextEnrichmentResult) -> bool:
    checks = _condition_checks(route.conditions, result)
    if not checks:
        return False
    if route.match_mode == "any":
        return any(checks)
    return all(checks)


def _condition_checks(
    conditions: NotificationRouteConditions,
    result: TextEnrichmentResult,
) -> list[bool]:
    assessment = result.lead_assessment
    checks: list[bool] = []
    if conditions.is_lead is not None:
        checks.append(bool(assessment and assessment.is_lead) is conditions.is_lead)
    if conditions.score_min is not None:
        checks.append(bool(assessment and assessment.score >= conditions.score_min))
    if conditions.score_max is not None:
        checks.append(bool(assessment and assessment.score <= conditions.score_max))
    if conditions.temperatures:
        checks.append(bool(assessment and assessment.temperature in conditions.temperatures))
    if conditions.review_lanes:
        lane = assessment.review_lane.key if assessment and assessment.review_lane else None
        checks.append(bool(lane and lane in conditions.review_lanes))
    if conditions.solution_areas:
        checks.append(_any_overlap(conditions.solution_areas, [item.type for item in assessment.solution_areas] if assessment else []))
    if conditions.customer_segments:
        checks.append(_any_overlap(conditions.customer_segments, [item.type for item in assessment.customer_segments] if assessment else []))
    if conditions.domain_signals:
        checks.append(_any_overlap(conditions.domain_signals, [item.type for item in result.domain_signals]))
    if conditions.facts:
        checks.append(_any_overlap(conditions.facts, [item.type for item in result.facts]))
    if conditions.reasons:
        checks.append(_any_overlap(conditions.reasons, [item.key for item in assessment.reasons] if assessment else []))
    if conditions.noise_signals:
        checks.append(_any_overlap(conditions.noise_signals, [item.type for item in assessment.noise_signals] if assessment else []))
    return checks


def _template_values(
    result: TextEnrichmentResult,
    context: NotificationMessageContext | None,
) -> dict[str, str]:
    assessment = result.lead_assessment
    reasons = assessment.reasons if assessment else []
    review_lane = assessment.review_lane if assessment else None
    return {
        "text": result.original_text,
        "text_preview": _truncate_text(result.original_text, max_length=1200),
        "score": str(assessment.score) if assessment else "0",
        "temperature": assessment.temperature if assessment else "none",
        "review_lane": review_lane.key if review_lane else "none",
        "review_lane_label": review_lane.label if review_lane else "не указано",
        "solution_areas": _category_labels(assessment.solution_areas if assessment else []),
        "customer_segments": _category_labels(assessment.customer_segments if assessment else []),
        "reasons": ", ".join(item.label for item in reasons) if reasons else "не указано",
        "reasons_detailed": _reason_lines(reasons),
        "telegram_message_url": context.telegram_message_url if context and context.telegram_message_url else "",
        "app_message_url": context.app_message_url if context and context.app_message_url else "",
    }


def _append_context_links(
    rendered: str,
    context: NotificationMessageContext | None,
    template: str,
) -> str:
    if context is None:
        return rendered
    lines: list[str] = []
    if context.telegram_message_url and "{telegram_message_url}" not in template:
        lines.append(f"Telegram: {context.telegram_message_url}")
    if context.app_message_url and "{app_message_url}" not in template:
        lines.append(f"Аналитика: {context.app_message_url}")
    if not lines:
        return rendered
    return f"{rendered}\n\nСсылки:\n" + "\n".join(lines)


def _safe_template(template: str, values: dict[str, str]) -> str:
    allowed = set(values)
    fields = [field_name for _, field_name, _, _ in Formatter().parse(template) if field_name]
    unknown = [field for field in fields if field not in allowed]
    if unknown:
        return template + "\n\nUnknown template fields: " + ", ".join(sorted(unknown))
    return template


def _category_labels(items: Sequence[object]) -> str:
    labels = [getattr(item, "label", "") for item in items]
    return ", ".join(label for label in labels if label) or "не указано"


def _reason_lines(reasons: Sequence[object], *, limit: int = 6) -> str:
    lines: list[str] = []
    for reason in reasons[:limit]:
        label = str(getattr(reason, "label", "") or getattr(reason, "key", ""))
        weight = int(getattr(reason, "weight", 0) or 0)
        matched = getattr(reason, "matched_texts", [])
        matched_values = [str(item) for item in matched[:3]] if isinstance(matched, list) else []
        detail = f": {', '.join(matched_values)}" if matched_values else ""
        lines.append(f"{_format_weight(weight)} {label}{detail}")
    if len(reasons) > limit:
        lines.append(f"...и еще {len(reasons) - limit}")
    return "\n".join(lines) if lines else "не указано"


def _format_weight(weight: int) -> str:
    return f"+{weight}" if weight > 0 else str(weight)


def _truncate_text(text: str, *, max_length: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 1].rstrip() + "..."


def _any_overlap(expected: list[str], actual: list[str]) -> bool:
    return bool(set(expected).intersection(actual))
