from __future__ import annotations

from typing import Any

from app.application.review_lanes import assign_review_lane_from_fields
from app.domain.enrichment import DomainSignal, ExtractedFact, LeadAssessment, LeadCategory, LeadReason
from app.domain.enrichment import LeadReviewLane
from app.infrastructure.nlp.config_loader import LeadScoreCapConfig, LeadScoringConfig


class LeadScorer:
    def __init__(
        self,
        config: LeadScoringConfig,
        *,
        signal_labels: dict[str, str] | None = None,
        fact_labels: dict[str, str] | None = None,
    ) -> None:
        self._config = config
        self._signal_labels = signal_labels or {}
        self._fact_labels = fact_labels or {}

    def assess(
        self,
        *,
        signals: list[DomainSignal],
        facts: list[ExtractedFact],
    ) -> LeadAssessment:
        signal_matches = _group_matches(signals)
        fact_matches = _group_matches(facts)
        reasons = self._reasons(signal_matches, fact_matches)
        score = self._score(reasons, signal_matches, fact_matches)
        temperature = self._temperature(score)
        solution_areas = self._categories(
            self._config.solution_areas,
            signal_matches,
            fact_matches,
        )
        customer_segments = self._categories(
            self._config.customer_segments,
            signal_matches,
            fact_matches,
        )
        intent_signals = self._signal_type_categories(
            self._config.intent_signal_types,
            signal_matches,
        )
        noise_signals = self._signal_type_categories(
            self._config.noise_signal_types,
            signal_matches,
        )
        veto_signal_types = (
            self._config.lead_veto_signal_types
            if self._config.lead_veto_signal_types is not None
            else self._config.noise_signal_types
        )
        has_lead_veto = any(signal_type in signal_matches for signal_type in veto_signal_types)
        effective_temperature = "none" if has_lead_veto else temperature

        return LeadAssessment(
            is_lead=not has_lead_veto and score >= self._config.lead_threshold,
            score=score,
            temperature=effective_temperature,
            solution_areas=solution_areas,
            customer_segments=customer_segments,
            intent_signals=intent_signals,
            noise_signals=noise_signals,
            reasons=reasons,
            review_lane=self._review_lane(
                score=score,
                temperature=effective_temperature,
                signal_matches=signal_matches,
                fact_matches=fact_matches,
                reasons=reasons,
                solution_areas=solution_areas,
                customer_segments=customer_segments,
                intent_signals=intent_signals,
                noise_signals=noise_signals,
            ),
        )

    def _score(
        self,
        reasons: list[LeadReason],
        signal_matches: dict[str, list[str]],
        fact_matches: dict[str, list[str]],
    ) -> int:
        score = max(0, sum(reason.weight for reason in reasons))
        for cap in self._config.score_caps:
            if score <= cap.max_score or not _cap_matches(cap, reasons, signal_matches, fact_matches):
                continue
            adjustment = cap.max_score - score
            reasons.append(
                LeadReason(
                    source="score_cap",
                    key=cap.key,
                    label=cap.label,
                    weight=adjustment,
                    matched_texts=_cap_matched_texts(cap, reasons, signal_matches, fact_matches),
                )
            )
            score = cap.max_score
        return max(0, score)

    def _reasons(
        self,
        signal_matches: dict[str, list[str]],
        fact_matches: dict[str, list[str]],
    ) -> list[LeadReason]:
        reasons: list[LeadReason] = []
        for signal_type, weight in self._config.signal_weights.items():
            if signal_type in signal_matches:
                reasons.append(
                    LeadReason(
                        source="domain_signal",
                        key=signal_type,
                        label=self._signal_labels.get(signal_type, signal_type),
                        weight=weight,
                        matched_texts=signal_matches[signal_type],
                    )
                )
        for fact_type, weight in self._config.fact_weights.items():
            if fact_type in fact_matches:
                reasons.append(
                    LeadReason(
                        source="fact",
                        key=fact_type,
                        label=self._fact_labels.get(fact_type, fact_type),
                        weight=weight,
                        matched_texts=fact_matches[fact_type],
                    )
                )
        return reasons

    def _temperature(self, score: int) -> str:
        if score >= self._config.hot_threshold:
            return "hot"
        if score >= self._config.warm_threshold:
            return "warm"
        if score >= self._config.lead_threshold:
            return "cold"
        return "none"

    def _categories(
        self,
        categories: dict[str, dict[str, Any]],
        signal_matches: dict[str, list[str]],
        fact_matches: dict[str, list[str]],
    ) -> list[LeadCategory]:
        matched: list[LeadCategory] = []
        for category_type, category in categories.items():
            signal_types = [str(item) for item in category.get("signal_types", [])]
            fact_types = [str(item) for item in category.get("fact_types", [])]
            matched_types = [
                *[signal_type for signal_type in signal_types if signal_type in signal_matches],
                *[fact_type for fact_type in fact_types if fact_type in fact_matches],
            ]
            if matched_types:
                matched.append(
                    LeadCategory(
                        type=category_type,
                        label=str(category.get("label", category_type)),
                        matched_types=matched_types,
                    )
                )
        return matched

    def _signal_type_categories(
        self,
        signal_types: list[str],
        signal_matches: dict[str, list[str]],
    ) -> list[LeadCategory]:
        return [
            LeadCategory(
                type=signal_type,
                label=self._signal_labels.get(signal_type, signal_type),
                matched_types=[signal_type],
            )
            for signal_type in signal_types
            if signal_type in signal_matches
        ]

    def _review_lane(
        self,
        *,
        score: int,
        temperature: str,
        signal_matches: dict[str, list[str]],
        fact_matches: dict[str, list[str]],
        reasons: list[LeadReason],
        solution_areas: list[LeadCategory],
        customer_segments: list[LeadCategory],
        intent_signals: list[LeadCategory],
        noise_signals: list[LeadCategory],
    ) -> LeadReviewLane | None:
        if not self._config.review_lanes:
            return None

        fields = {
            "signal_types": set(signal_matches),
            "fact_types": set(fact_matches),
            "reason_keys": {reason.key for reason in reasons},
            "solution_area_types": {item.type for item in solution_areas},
            "customer_segment_types": {item.type for item in customer_segments},
            "intent_signal_types": {item.type for item in intent_signals},
            "noise_signal_types": {item.type for item in noise_signals},
        }
        lane = assign_review_lane_from_fields(
            score=score,
            temperature=temperature,
            fields=fields,
            lanes=self._config.review_lanes,
        )
        return LeadReviewLane(
            key=lane.key,
            label=lane.label,
            description=lane.description,
            matched_group_indexes=lane.matched_group_indexes,
        )


def _group_matches(items: list[DomainSignal] | list[ExtractedFact]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for item in items:
        grouped.setdefault(item.type, [])
        if item.text not in grouped[item.type]:
            grouped[item.type].append(item.text)
    return grouped


def _cap_matches(
    cap: LeadScoreCapConfig,
    reasons: list[LeadReason],
    signal_matches: dict[str, list[str]],
    fact_matches: dict[str, list[str]],
) -> bool:
    reason_keys = {reason.key for reason in reasons}
    included = any(
        (
            any(signal_type in signal_matches for signal_type in cap.signal_types),
            any(signal_type in signal_matches for signal_type in cap.noise_signal_types),
            any(fact_type in fact_matches for fact_type in cap.fact_types),
            any(reason_key in reason_keys for reason_key in cap.reason_keys),
        )
    )
    if not included:
        return False
    return not any(
        (
            any(signal_type in signal_matches for signal_type in cap.excluded_signal_types),
            any(signal_type in signal_matches for signal_type in cap.excluded_noise_signal_types),
            any(fact_type in fact_matches for fact_type in cap.excluded_fact_types),
            any(reason_key in reason_keys for reason_key in cap.excluded_reason_keys),
        )
    )


def _cap_matched_texts(
    cap: LeadScoreCapConfig,
    reasons: list[LeadReason],
    signal_matches: dict[str, list[str]],
    fact_matches: dict[str, list[str]],
) -> list[str]:
    matched: list[str] = []
    reason_lookup = {reason.key: reason for reason in reasons}
    for signal_type in [*cap.signal_types, *cap.noise_signal_types]:
        matched.extend(signal_matches.get(signal_type, []))
    for fact_type in cap.fact_types:
        matched.extend(fact_matches.get(fact_type, []))
    for reason_key in cap.reason_keys:
        reason = reason_lookup.get(reason_key)
        if reason is not None:
            matched.extend(reason.matched_texts)
    return _unique_non_empty(matched)


def _unique_non_empty(values: list[str]) -> list[str]:
    unique: list[str] = []
    for value in values:
        if value and value not in unique:
            unique.append(value)
    return unique
