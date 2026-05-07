from __future__ import annotations

from typing import Any

from app.domain.enrichment import DomainSignal, ExtractedFact, LeadAssessment, LeadCategory, LeadReason
from app.infrastructure.nlp.config_loader import LeadScoringConfig


class LeadScorer:
    def __init__(self, config: LeadScoringConfig) -> None:
        self._config = config

    def assess(
        self,
        *,
        signals: list[DomainSignal],
        facts: list[ExtractedFact],
    ) -> LeadAssessment:
        signal_matches = _group_matches(signals)
        fact_matches = _group_matches(facts)
        reasons = self._reasons(signal_matches, fact_matches)
        score = max(0, sum(reason.weight for reason in reasons))

        return LeadAssessment(
            is_lead=score >= self._config.lead_threshold,
            score=score,
            temperature=self._temperature(score),
            solution_areas=self._categories(
                self._config.solution_areas,
                signal_matches,
                fact_matches,
            ),
            customer_segments=self._categories(
                self._config.customer_segments,
                signal_matches,
                fact_matches,
            ),
            intent_signals=self._signal_type_categories(
                self._config.intent_signal_types,
                signal_matches,
            ),
            noise_signals=self._signal_type_categories(
                self._config.noise_signal_types,
                signal_matches,
            ),
            reasons=reasons,
        )

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
                        label=signal_type,
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
                        label=fact_type,
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
            LeadCategory(type=signal_type, label=signal_type, matched_types=[signal_type])
            for signal_type in signal_types
            if signal_type in signal_matches
        ]


def _group_matches(items: list[DomainSignal] | list[ExtractedFact]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for item in items:
        grouped.setdefault(item.type, [])
        if item.text not in grouped[item.type]:
            grouped[item.type].append(item.text)
    return grouped
