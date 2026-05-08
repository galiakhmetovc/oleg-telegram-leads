from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.analytics import AnalyticsCandidate

DEFAULT_REVIEW_LANE_KEY = "other_candidate"
DEFAULT_REVIEW_LANE_LABEL = "Прочий кандидат"


@dataclass(frozen=True)
class ReviewLaneMatchGroup:
    signal_types: list[str] = field(default_factory=list)
    fact_types: list[str] = field(default_factory=list)
    reason_keys: list[str] = field(default_factory=list)
    solution_area_types: list[str] = field(default_factory=list)
    customer_segment_types: list[str] = field(default_factory=list)
    intent_signal_types: list[str] = field(default_factory=list)
    noise_signal_types: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReviewLaneConfig:
    key: str
    label: str
    priority: int = 0
    description: str | None = None
    min_score: int | None = None
    max_score: int | None = None
    temperatures: list[str] = field(default_factory=list)
    match_groups: list[ReviewLaneMatchGroup] = field(default_factory=list)
    excluded_signal_types: list[str] = field(default_factory=list)
    excluded_fact_types: list[str] = field(default_factory=list)
    excluded_reason_keys: list[str] = field(default_factory=list)
    excluded_solution_area_types: list[str] = field(default_factory=list)
    excluded_customer_segment_types: list[str] = field(default_factory=list)
    excluded_intent_signal_types: list[str] = field(default_factory=list)
    excluded_noise_signal_types: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReviewLaneAssignment:
    key: str
    label: str
    description: str | None = None


def assign_review_lane(
    candidate: AnalyticsCandidate,
    lanes: list[ReviewLaneConfig],
) -> ReviewLaneAssignment:
    fields = _candidate_fields(candidate)
    for lane in sorted(lanes, key=lambda item: (-item.priority, item.key)):
        if _lane_matches(candidate, fields, lane):
            return ReviewLaneAssignment(
                key=lane.key,
                label=lane.label,
                description=lane.description,
            )
    return ReviewLaneAssignment(
        key=DEFAULT_REVIEW_LANE_KEY,
        label=DEFAULT_REVIEW_LANE_LABEL,
    )


def review_lane_labels(lanes: list[ReviewLaneConfig]) -> dict[str, ReviewLaneAssignment]:
    labels = {
        lane.key: ReviewLaneAssignment(
            key=lane.key,
            label=lane.label,
            description=lane.description,
        )
        for lane in lanes
    }
    labels.setdefault(
        DEFAULT_REVIEW_LANE_KEY,
        ReviewLaneAssignment(key=DEFAULT_REVIEW_LANE_KEY, label=DEFAULT_REVIEW_LANE_LABEL),
    )
    return labels


def _lane_matches(
    candidate: AnalyticsCandidate,
    fields: dict[str, set[str]],
    lane: ReviewLaneConfig,
) -> bool:
    if lane.min_score is not None and candidate.score < lane.min_score:
        return False
    if lane.max_score is not None and candidate.score > lane.max_score:
        return False
    if lane.temperatures and candidate.temperature not in lane.temperatures:
        return False
    if _has_excluded_value(fields, lane):
        return False
    return all(_match_group(fields, group) for group in lane.match_groups)


def _match_group(fields: dict[str, set[str]], group: ReviewLaneMatchGroup) -> bool:
    group_fields = {
        "signal_types": group.signal_types,
        "fact_types": group.fact_types,
        "reason_keys": group.reason_keys,
        "solution_area_types": group.solution_area_types,
        "customer_segment_types": group.customer_segment_types,
        "intent_signal_types": group.intent_signal_types,
        "noise_signal_types": group.noise_signal_types,
    }
    requested = {
        field_name: set(values)
        for field_name, values in group_fields.items()
        if values
    }
    if not requested:
        return True
    return any(values & fields[field_name] for field_name, values in requested.items())


def _has_excluded_value(fields: dict[str, set[str]], lane: ReviewLaneConfig) -> bool:
    exclusions = {
        "signal_types": lane.excluded_signal_types,
        "fact_types": lane.excluded_fact_types,
        "reason_keys": lane.excluded_reason_keys,
        "solution_area_types": lane.excluded_solution_area_types,
        "customer_segment_types": lane.excluded_customer_segment_types,
        "intent_signal_types": lane.excluded_intent_signal_types,
        "noise_signal_types": lane.excluded_noise_signal_types,
    }
    return any(set(values) & fields[field_name] for field_name, values in exclusions.items() if values)


def _candidate_fields(candidate: AnalyticsCandidate) -> dict[str, set[str]]:
    return {
        "signal_types": _item_types(candidate.domain_signals, "type"),
        "fact_types": _item_types(candidate.facts, "type"),
        "reason_keys": _item_types(candidate.reasons, "key"),
        "solution_area_types": _item_types(candidate.solution_areas, "type"),
        "customer_segment_types": _item_types(candidate.customer_segments, "type"),
        "intent_signal_types": _item_types(candidate.intent_signals, "type"),
        "noise_signal_types": _item_types(candidate.noise_signals, "type"),
    }


def _item_types(items: list[dict[str, object]], key: str) -> set[str]:
    return {str(item[key]) for item in items if item.get(key)}
