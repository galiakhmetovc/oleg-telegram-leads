from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable

from app.application.settings.ports import NlpConfigRepository
from app.domain.settings import NlpConfigRevision

OPERATOR_NOISE_SIGNAL_TYPE = "operator_noise"
OPERATOR_NOISE_SIGNAL_LABEL = "Операторский шум"
OPERATOR_NOISE_SIGNAL_GROUP = "Шум / ручная разметка"
OPERATOR_NOISE_SIGNAL_WEIGHT = -50

DocumentValidator = Callable[[dict[str, dict[str, Any]]], None]


@dataclass(frozen=True)
class AddOperatorNoisePhraseCommand:
    text: str
    source_message_id: str | None = None


@dataclass(frozen=True)
class AddOperatorNoisePhraseResult:
    text: str
    phrase: list[str]
    signal_type: str
    signal_label: str
    created_rule: bool
    created_phrase: bool
    revision: NlpConfigRevision


@dataclass(frozen=True)
class OperatorNoiseMutation:
    documents: dict[str, dict[str, Any]]
    created_rule: bool
    created_phrase: bool
    changed: bool


class AddOperatorNoisePhrase:
    def __init__(
        self,
        *,
        repository: NlpConfigRepository,
        default_documents: dict[str, dict[str, Any]],
        validate_documents: DocumentValidator,
    ) -> None:
        self._repository = repository
        self._default_documents = default_documents
        self._validate_documents = validate_documents

    async def execute(
        self,
        command: AddOperatorNoisePhraseCommand,
    ) -> AddOperatorNoisePhraseResult:
        phrase = operator_noise_phrase_tokens(command.text)
        active_revision = await self._repository.get_active_or_seed(self._default_documents)
        mutation = add_operator_noise_phrase_to_documents(active_revision.documents, phrase)
        if mutation.changed:
            self._validate_documents(mutation.documents)
            revision = await self._repository.replace_active(
                mutation.documents,
                source="operator_constructor_noise",
            )
        else:
            revision = active_revision

        return AddOperatorNoisePhraseResult(
            text=command.text,
            phrase=phrase,
            signal_type=OPERATOR_NOISE_SIGNAL_TYPE,
            signal_label=OPERATOR_NOISE_SIGNAL_LABEL,
            created_rule=mutation.created_rule,
            created_phrase=mutation.created_phrase,
            revision=revision,
        )


def operator_noise_phrase_tokens(text: str) -> list[str]:
    tokens = [
        token.strip("._-+").casefold()
        for token in re.findall(r"[\w.+-]+", text, flags=re.UNICODE)
    ]
    clean_tokens = [token for token in tokens if token]
    if not clean_tokens:
        raise ValueError("selected text must contain at least one word or number")
    return clean_tokens


def add_operator_noise_phrase_to_documents(
    documents: dict[str, dict[str, Any]],
    phrase: list[str],
) -> OperatorNoiseMutation:
    next_documents = deepcopy(documents)
    changed = False
    created_rule = False
    created_phrase = False

    signals = _document_list(next_documents, "signals", "signals")
    signal = _find_mapping_by_key(signals, "type", OPERATOR_NOISE_SIGNAL_TYPE)
    if signal is None:
        signal = {
            "type": OPERATOR_NOISE_SIGNAL_TYPE,
            "label": OPERATOR_NOISE_SIGNAL_LABEL,
            "group": OPERATOR_NOISE_SIGNAL_GROUP,
            "color": "#5f6368",
            "confidence": 0.95,
            "phrases": [],
        }
        signals.append(signal)
        created_rule = True
        changed = True

    phrases = signal.setdefault("phrases", [])
    if not isinstance(phrases, list):
        phrases = []
        signal["phrases"] = phrases
        changed = True
    if phrase not in phrases:
        phrases.append(phrase)
        created_phrase = True
        changed = True

    scoring = next_documents.setdefault("lead_scoring", {}).setdefault("lead_scoring", {})
    weights = scoring.setdefault("weights", {})
    signal_weights = weights.setdefault("signals", {})
    if signal_weights.get(OPERATOR_NOISE_SIGNAL_TYPE) is None:
        signal_weights[OPERATOR_NOISE_SIGNAL_TYPE] = OPERATOR_NOISE_SIGNAL_WEIGHT
        changed = True

    if _append_unique(scoring.setdefault("noise_signal_types", []), OPERATOR_NOISE_SIGNAL_TYPE):
        changed = True
    if _append_unique(scoring.setdefault("lead_veto_signal_types", []), OPERATOR_NOISE_SIGNAL_TYPE):
        changed = True

    for lane in scoring.get("review_lanes", []):
        if not isinstance(lane, dict):
            continue
        if lane.get("key") == "noise":
            for match_group in lane.setdefault("match_groups", []):
                if not isinstance(match_group, dict):
                    continue
                if _append_unique(match_group.setdefault("noise_signal_types", []), OPERATOR_NOISE_SIGNAL_TYPE):
                    changed = True
                if _append_unique(match_group.setdefault("signal_types", []), OPERATOR_NOISE_SIGNAL_TYPE):
                    changed = True
        elif _append_unique(lane.setdefault("excluded_noise_signal_types", []), OPERATOR_NOISE_SIGNAL_TYPE):
            changed = True

    return OperatorNoiseMutation(
        documents=next_documents,
        created_rule=created_rule,
        created_phrase=created_phrase,
        changed=changed,
    )


def _document_list(
    documents: dict[str, dict[str, Any]],
    document_name: str,
    list_name: str,
) -> list[Any]:
    document = documents.setdefault(document_name, {})
    values = document.setdefault(list_name, [])
    if not isinstance(values, list):
        replacement: list[Any] = []
        document[list_name] = replacement
        return replacement
    return values


def _find_mapping_by_key(
    values: list[Any],
    key: str,
    expected_value: str,
) -> dict[str, Any] | None:
    for value in values:
        if isinstance(value, dict) and value.get(key) == expected_value:
            return value
    return None


def _append_unique(values: list[Any], value: str) -> bool:
    if value in values:
        return False
    values.append(value)
    return True
