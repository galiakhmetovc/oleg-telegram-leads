from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Literal

from app.application.settings.ports import NlpConfigRepository
from app.domain.settings import NlpConfigRevision

OPERATOR_NOISE_SIGNAL_TYPE = "operator_noise"
OPERATOR_NOISE_SIGNAL_LABEL = "Операторский шум"
OPERATOR_NOISE_SIGNAL_GROUP = "Шум / ручная разметка"
OPERATOR_NOISE_SIGNAL_WEIGHT = -50
NEW_SIGNAL_DEFAULT_WEIGHT = 0
SUPPORTED_ALIAS_CATALOGS = ("vendors", "protocols", "devices", "software")

DocumentValidator = Callable[[dict[str, dict[str, Any]]], None]
SemanticPatternBuilder = Callable[[str], dict[str, Any]]
AliasCatalog = Literal["vendors", "protocols", "devices", "software"]
RuleCollection = Literal["signals", "facts"]
PhraseKind = Literal["exact", "semantic"]


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
class SettingsReferenceResult:
    section: str
    key: str
    label: str
    catalog: str | None = None


@dataclass(frozen=True)
class AddAliasFromSelectionCommand:
    text: str
    catalog: AliasCatalog
    key: str
    source_message_id: str | None = None
    canonical: str | None = None
    alias_type: str | None = None
    fact_types: list[str] | None = None
    color: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class AddAliasFromSelectionResult:
    text: str
    catalog: str
    key: str
    canonical: str
    created_target: bool
    created_entry: bool
    settings_ref: SettingsReferenceResult
    revision: NlpConfigRevision


@dataclass(frozen=True)
class AddRulePhraseFromSelectionCommand:
    text: str
    collection: RuleCollection
    target_type: str
    phrase_kind: PhraseKind
    source_message_id: str | None = None
    target_label: str | None = None
    group: str | None = None
    color: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class AddRulePhraseFromSelectionResult:
    text: str
    collection: str
    rule_type: str
    rule_label: str
    phrase_kind: str
    created_target: bool
    created_entry: bool
    settings_ref: SettingsReferenceResult
    revision: NlpConfigRevision
    exact_phrase: list[str] | None = None
    semantic_pattern: dict[str, Any] | None = None


@dataclass(frozen=True)
class OperatorNoiseMutation:
    documents: dict[str, dict[str, Any]]
    created_rule: bool
    created_phrase: bool
    changed: bool


@dataclass(frozen=True)
class AliasMutation:
    documents: dict[str, dict[str, Any]]
    canonical: str
    created_target: bool
    created_entry: bool
    changed: bool


@dataclass(frozen=True)
class RulePhraseMutation:
    documents: dict[str, dict[str, Any]]
    rule_label: str
    created_target: bool
    created_entry: bool
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


class AddAliasFromSelection:
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
        command: AddAliasFromSelectionCommand,
    ) -> AddAliasFromSelectionResult:
        alias_text = selected_text_value(command.text)
        active_revision = await self._repository.get_active_or_seed(self._default_documents)
        mutation = add_alias_to_documents(
            active_revision.documents,
            alias_text=alias_text,
            catalog=command.catalog,
            key=command.key,
            canonical=command.canonical,
            alias_type=command.alias_type,
            fact_types=command.fact_types,
            color=command.color,
            confidence=command.confidence,
        )
        if mutation.changed:
            self._validate_documents(mutation.documents)
            revision = await self._repository.replace_active(
                mutation.documents,
                source="operator_constructor_alias",
            )
        else:
            revision = active_revision

        return AddAliasFromSelectionResult(
            text=command.text,
            catalog=command.catalog,
            key=clean_key(command.key),
            canonical=mutation.canonical,
            created_target=mutation.created_target,
            created_entry=mutation.created_entry,
            settings_ref=SettingsReferenceResult(
                section="aliases",
                catalog=command.catalog,
                key=clean_key(command.key),
                label=mutation.canonical,
            ),
            revision=revision,
        )


class AddRulePhraseFromSelection:
    def __init__(
        self,
        *,
        repository: NlpConfigRepository,
        default_documents: dict[str, dict[str, Any]],
        validate_documents: DocumentValidator,
        semantic_pattern_builder: SemanticPatternBuilder,
    ) -> None:
        self._repository = repository
        self._default_documents = default_documents
        self._validate_documents = validate_documents
        self._semantic_pattern_builder = semantic_pattern_builder

    async def execute(
        self,
        command: AddRulePhraseFromSelectionCommand,
    ) -> AddRulePhraseFromSelectionResult:
        exact_phrase: list[str] | None = None
        semantic_pattern: dict[str, Any] | None = None
        if command.phrase_kind == "exact":
            exact_phrase = exact_phrase_tokens(command.text)
        else:
            semantic_pattern = self._semantic_pattern_builder(command.text)

        active_revision = await self._repository.get_active_or_seed(self._default_documents)
        mutation = add_rule_phrase_to_documents(
            active_revision.documents,
            collection=command.collection,
            target_type=command.target_type,
            target_label=command.target_label,
            phrase_kind=command.phrase_kind,
            exact_phrase=exact_phrase,
            semantic_pattern=semantic_pattern,
            group=command.group,
            color=command.color,
            confidence=command.confidence,
        )
        if mutation.changed:
            self._validate_documents(mutation.documents)
            revision = await self._repository.replace_active(
                mutation.documents,
                source=f"operator_constructor_{command.collection.rstrip('s')}",
            )
        else:
            revision = active_revision

        return AddRulePhraseFromSelectionResult(
            text=command.text,
            collection=command.collection,
            rule_type=clean_key(command.target_type),
            rule_label=mutation.rule_label,
            phrase_kind=command.phrase_kind,
            exact_phrase=exact_phrase,
            semantic_pattern=semantic_pattern,
            created_target=mutation.created_target,
            created_entry=mutation.created_entry,
            settings_ref=SettingsReferenceResult(
                section=command.collection,
                key=clean_key(command.target_type),
                label=mutation.rule_label,
            ),
            revision=revision,
        )


def selected_text_value(text: str) -> str:
    value = text.strip()
    if not value:
        raise ValueError("selected text must not be empty")
    return value


def clean_key(value: str) -> str:
    key = value.strip()
    if not key:
        raise ValueError("target key must not be empty")
    return key


def operator_noise_phrase_tokens(text: str) -> list[str]:
    return exact_phrase_tokens(text)


def exact_phrase_tokens(text: str) -> list[str]:
    tokens = [
        token.strip("._-+").casefold()
        for token in re.findall(r"[\w.+-]+", text, flags=re.UNICODE)
    ]
    clean_tokens = [token for token in tokens if token]
    if not clean_tokens:
        raise ValueError("selected text must contain at least one word or number")
    return clean_tokens


def add_alias_to_documents(
    documents: dict[str, dict[str, Any]],
    *,
    alias_text: str,
    catalog: str,
    key: str,
    canonical: str | None = None,
    alias_type: str | None = None,
    fact_types: list[str] | None = None,
    color: str | None = None,
    confidence: float | None = None,
) -> AliasMutation:
    if catalog not in SUPPORTED_ALIAS_CATALOGS:
        raise ValueError(f"unsupported alias catalog: {catalog}")
    cleaned_key = clean_key(key)
    next_documents = deepcopy(documents)
    changed = False
    created_target = False
    created_entry = False

    aliases = _document_list(next_documents, catalog, catalog)
    target = _find_mapping_by_key(aliases, "key", cleaned_key)
    if target is None:
        target = {
            "key": cleaned_key,
            "canonical": selected_text_value(canonical or alias_text),
            "type": alias_type or _default_alias_type(catalog),
            "aliases": [],
            "fact_types": _clean_string_list(fact_types) or [alias_type or _default_alias_type(catalog)],
        }
        if color:
            target["color"] = color
        if confidence is not None:
            target["confidence"] = confidence
        aliases.append(target)
        created_target = True
        changed = True

    target_aliases = target.setdefault("aliases", [])
    if not isinstance(target_aliases, list):
        target_aliases = []
        target["aliases"] = target_aliases
        changed = True
    if alias_text.casefold() not in {str(item).casefold() for item in target_aliases}:
        target_aliases.append(alias_text)
        created_entry = True
        changed = True

    return AliasMutation(
        documents=next_documents,
        canonical=str(target.get("canonical", cleaned_key)),
        created_target=created_target,
        created_entry=created_entry,
        changed=changed,
    )


def add_rule_phrase_to_documents(
    documents: dict[str, dict[str, Any]],
    *,
    collection: str,
    target_type: str,
    target_label: str | None,
    phrase_kind: str,
    exact_phrase: list[str] | None,
    semantic_pattern: dict[str, Any] | None,
    group: str | None,
    color: str | None,
    confidence: float | None,
) -> RulePhraseMutation:
    if collection not in {"signals", "facts"}:
        raise ValueError(f"unsupported rule collection: {collection}")
    if phrase_kind not in {"exact", "semantic"}:
        raise ValueError(f"unsupported phrase kind: {phrase_kind}")
    cleaned_type = clean_key(target_type)
    next_documents = deepcopy(documents)
    changed = False
    created_target = False
    created_entry = False

    rules = _document_list(next_documents, collection, collection)
    rule = _find_mapping_by_key(rules, "type", cleaned_type)
    if rule is None:
        rule = {
            "type": cleaned_type,
            "label": selected_text_value(target_label or cleaned_type),
            "group": group or ("Операторские сигналы" if collection == "signals" else "Операторские факты"),
            "confidence": 0.5 if confidence is None else confidence,
            "phrases": [],
            "patterns": [],
        }
        if collection == "signals":
            rule["color"] = color or "#0b57d0"
            rule["match"] = {"aliases": [], "facts": []}
        elif color:
            rule["color"] = color
        rules.append(rule)
        created_target = True
        changed = True
        if collection == "signals":
            scoring = next_documents.setdefault("lead_scoring", {}).setdefault("lead_scoring", {})
            signal_weights = scoring.setdefault("weights", {}).setdefault("signals", {})
            if signal_weights.get(cleaned_type) is None:
                signal_weights[cleaned_type] = NEW_SIGNAL_DEFAULT_WEIGHT
                changed = True

    if phrase_kind == "exact":
        if exact_phrase is None:
            raise ValueError("exact phrase is required")
        phrases = rule.setdefault("phrases", [])
        if not isinstance(phrases, list):
            phrases = []
            rule["phrases"] = phrases
            changed = True
        if exact_phrase not in phrases:
            phrases.append(exact_phrase)
            created_entry = True
            changed = True
    else:
        if semantic_pattern is None:
            raise ValueError("semantic pattern is required")
        patterns = rule.setdefault("patterns", [])
        if not isinstance(patterns, list):
            patterns = []
            rule["patterns"] = patterns
            changed = True
        if semantic_pattern not in patterns:
            patterns.append(semantic_pattern)
            created_entry = True
            changed = True

    return RulePhraseMutation(
        documents=next_documents,
        rule_label=str(rule.get("label", cleaned_type)),
        created_target=created_target,
        created_entry=created_entry,
        changed=changed,
    )


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


def _default_alias_type(catalog: str) -> str:
    return {
        "vendors": "vendor",
        "protocols": "protocol",
        "devices": "device",
        "software": "software",
    }[catalog]


def _clean_string_list(values: list[str] | None) -> list[str]:
    return [value.strip() for value in (values or []) if value.strip()]
