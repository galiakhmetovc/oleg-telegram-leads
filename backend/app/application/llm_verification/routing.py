from __future__ import annotations

from app.domain.enrichment import LeadAssessment, TextEnrichmentResult
from app.domain.llm_settings import LlmRoute, LlmRouteConditions, LlmSettings
from app.domain.llm_verification import SourceMessageForLlmVerification


def matched_llm_routes(settings: LlmSettings, source: SourceMessageForLlmVerification) -> list[LlmRoute]:
    if not settings.enabled:
        return []
    return [
        route
        for route in sorted(settings.routes, key=lambda item: item.priority, reverse=True)
        if route.enabled and _route_matches(route, source)
    ]


def _route_matches(route: LlmRoute, source: SourceMessageForLlmVerification) -> bool:
    checks = _condition_checks(route.conditions, source)
    if not checks:
        return True
    if route.match_mode == "any":
        return any(checks)
    return all(checks)


def _condition_checks(conditions: LlmRouteConditions, source: SourceMessageForLlmVerification) -> list[bool]:
    result = source.enrichment_result
    assessment = result.lead_assessment
    checks: list[bool] = []
    if conditions.source_chat_ids:
        checks.append(str(source.source_chat_id) in _normalized_set(conditions.source_chat_ids))
    if conditions.score_min is not None:
        checks.append(_score(assessment) >= conditions.score_min)
    if conditions.score_max is not None:
        checks.append(_score(assessment) <= conditions.score_max)
    if conditions.temperatures:
        checks.append(_temperature(assessment) in _normalized_set(conditions.temperatures))
    if conditions.review_lanes:
        checks.append(_review_lane(assessment) in _normalized_set(conditions.review_lanes))
    checks.extend(_include_exclude_checks(conditions, result))
    return checks


def _include_exclude_checks(conditions: LlmRouteConditions, result: TextEnrichmentResult) -> list[bool]:
    fact_types = {fact.type for fact in result.facts}
    signal_types = {signal.type for signal in result.domain_signals}
    assessment = result.lead_assessment
    if assessment is not None:
        signal_types.update(signal.type for signal in assessment.intent_signals)
        signal_types.update(signal.type for signal in assessment.noise_signals)
    reason_keys = {reason.key for reason in assessment.reasons} if assessment is not None else set()
    solution_area_types = {item.type for item in assessment.solution_areas} if assessment is not None else set()
    customer_segment_types = {item.type for item in assessment.customer_segments} if assessment is not None else set()

    return [
        _includes(fact_types, conditions.include_fact_types),
        _excludes(fact_types, conditions.exclude_fact_types),
        _includes(signal_types, conditions.include_signal_types),
        _excludes(signal_types, conditions.exclude_signal_types),
        _includes(reason_keys, conditions.include_reason_keys),
        _excludes(reason_keys, conditions.exclude_reason_keys),
        _includes(solution_area_types, conditions.include_solution_area_types),
        _excludes(solution_area_types, conditions.exclude_solution_area_types),
        _includes(customer_segment_types, conditions.include_customer_segment_types),
        _excludes(customer_segment_types, conditions.exclude_customer_segment_types),
    ]


def _includes(actual: set[str], required: list[str]) -> bool:
    return not required or bool(actual.intersection(_normalized_set(required)))


def _excludes(actual: set[str], forbidden: list[str]) -> bool:
    return not forbidden or not actual.intersection(_normalized_set(forbidden))


def _score(assessment: LeadAssessment | None) -> int:
    return assessment.score if assessment is not None else 0


def _temperature(assessment: LeadAssessment | None) -> str | None:
    return assessment.temperature if assessment is not None else None


def _review_lane(assessment: LeadAssessment | None) -> str | None:
    return assessment.review_lane.key if assessment is not None and assessment.review_lane is not None else None


def _normalized_set(values: list[str]) -> set[str]:
    return {value.strip() for value in values if value.strip()}
