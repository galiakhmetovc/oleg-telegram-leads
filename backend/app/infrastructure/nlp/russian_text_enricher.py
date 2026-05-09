from __future__ import annotations

import re
import warnings
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from natasha import Doc, MorphVocab, NewsEmbedding, NewsMorphTagger, NewsNERTagger
from natasha import NewsSyntaxParser, Segmenter
from yargy import Parser, or_, rule
from yargy.predicates import normalized
from yargy.tokenizer import MorphTokenizer

from app.domain.enrichment import DomainSignal, EnrichedEntity, EnrichedSentence, EnrichedToken
from app.domain.enrichment import EnrichmentMetrics, ExtractedFact, PipelineTraceItem
from app.domain.enrichment import SettingsReference
from app.domain.enrichment import SyntaxDependency, TextEnrichmentResult, TextRange
from app.infrastructure.nlp.config_loader import AliasMatchingConfig, AliasRuleConfig, NlpPipelineConfig
from app.infrastructure.nlp.config_loader import PhraseRuleConfig
from app.infrastructure.nlp.config_loader import RuleTokenConfig
from app.infrastructure.nlp.lead_scorer import LeadScorer

ProgressCallback = Callable[[str, int, str], None]


@dataclass(frozen=True)
class CompiledPhraseRule:
    config: PhraseRuleConfig
    exact_phrases: tuple[CompiledExactPhrase, ...]
    parser: Any | None


@dataclass(frozen=True)
class CompiledAliasRule:
    config: AliasRuleConfig
    exact_phrases: tuple[CompiledExactPhrase, ...]
    normalized_aliases: tuple[CompiledAliasText, ...]


@dataclass(frozen=True)
class CompiledExactPhrase:
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class CompiledAliasText:
    compact: str
    fuzzy_distance: int
    max_word_span: int
    script: str | None


@dataclass(frozen=True)
class AliasCompactDocument:
    text: str
    indexes: tuple[int, ...]
    word_ranges: tuple[tuple[int, int], ...]
    word_scripts: tuple[str | None, ...]


@dataclass(frozen=True)
class AliasTextMatch:
    config: AliasRuleConfig
    start: int
    stop: int
    text: str


class RussianTextEnricher:
    def __init__(self, config: NlpPipelineConfig) -> None:
        self._config = config
        self._segmenter = Segmenter()
        self._morph_vocab = MorphVocab()
        self._embedding: NewsEmbedding | None = None
        self._morph_tagger: NewsMorphTagger | None = None
        self._syntax_parser: NewsSyntaxParser | None = None
        self._ner_tagger: NewsNERTagger | None = None
        self._yargy_tokenizer = MorphTokenizer()
        self._compiled_signal_rules = self._compile_phrase_rules(config.signals)
        self._compiled_fact_rules = self._compile_phrase_rules(config.facts)
        self._compiled_alias_rules = self._compile_alias_rules(config.aliases)
        self._lead_scorer = LeadScorer(
            config.lead_scoring,
            signal_labels={rule.type: rule.label for rule in config.signals},
            fact_labels=_fact_type_labels(config),
        )

    def enrich(
        self,
        text: str,
        progress_callback: ProgressCallback | None = None,
    ) -> TextEnrichmentResult:
        trace: list[PipelineTraceItem] = []

        def mark(stage: str, progress: int, message: str) -> None:
            trace.append(
                PipelineTraceItem(
                    stage=stage,
                    status="completed",
                    message=message,
                    progress_percent=progress,
                )
            )
            if progress_callback is not None:
                progress_callback(stage, progress, message)

        doc = Doc(text)
        doc.segment(self._segmenter)
        mark("segmentation", 15, "Текст разбит на предложения и токены")

        if self._config.is_enabled("morph"):
            doc.tag_morph(self._morph_tagger_instance())
            for token in doc.tokens:
                token.lemmatize(self._morph_vocab)
            mark("morph", 35, "Выполнены морфология, POS и лемматизация")

        if self._config.is_enabled("syntax"):
            doc.parse_syntax(self._syntax_parser_instance())
            mark("syntax", 55, "Построены синтаксические зависимости")

        if self._config.is_enabled("ner"):
            doc.tag_ner(self._ner_tagger_instance())
            for span in doc.spans:
                span.normalize(self._morph_vocab)
            mark("ner", 70, "Найдены именованные сущности")

        alias_matches = self._find_alias_matches(text)

        facts = self._extract_facts(text, alias_matches) if self._config.is_enabled("facts") else []
        if self._config.is_enabled("facts"):
            mark("facts", 80, "Извлечены факты по Yargy-правилам")

        signals = (
            self._extract_domain_signals(text, alias_matches, facts)
            if self._config.is_enabled("domain_signals")
            else []
        )
        if self._config.is_enabled("domain_signals"):
            mark("domain_signals", 90, "Найдены доменные сигналы-кандидаты")

        lead_assessment = (
            self._lead_scorer.assess(signals=signals, facts=facts)
            if self._config.is_enabled("lead_scoring")
            else None
        )
        if self._config.is_enabled("lead_scoring"):
            mark("lead_scoring", 95, "Рассчитана оценка потенциального лида")

        sentences = [
            EnrichedSentence(
                id=f"sentence-{index}",
                text=sentence.text,
                range=TextRange(start=sentence.start, stop=sentence.stop),
            )
            for index, sentence in enumerate(doc.sents, start=1)
        ]
        tokens = [
            EnrichedToken(
                id=token.id,
                text=token.text,
                range=TextRange(start=token.start, stop=token.stop),
                lemma=getattr(token, "lemma", None),
                pos=getattr(token, "pos", None),
                features={
                    key: str(value)
                    for key, value in (getattr(token, "feats", None) or {}).items()
                },
            )
            for token in doc.tokens
        ]
        entities = [
            EnrichedEntity(
                id=f"entity-{index}",
                text=span.text,
                type=span.type,
                range=TextRange(start=span.start, stop=span.stop),
                source="natasha",
            )
            for index, span in enumerate(doc.spans or [], start=1)
        ]
        syntax = [
            SyntaxDependency(
                token_id=token.id,
                head_id=getattr(token, "head_id", None),
                relation=getattr(token, "rel", None),
            )
            for token in doc.tokens
        ]
        metrics = EnrichmentMetrics(
            character_count=len(text),
            sentence_count=len(sentences),
            token_count=len(tokens),
            entity_count=len(entities),
            fact_count=len(facts),
            domain_signal_count=len(signals),
        )
        mark("metrics", 100, "Метрики рассчитаны")

        return TextEnrichmentResult(
            original_text=text,
            normalized_text=" ".join(text.split()),
            sentences=sentences,
            tokens=tokens,
            entities=entities,
            facts=facts,
            domain_signals=signals,
            syntax=syntax,
            metrics=metrics,
            pipeline_trace=trace,
            lead_assessment=lead_assessment,
        )

    def _embedding_instance(self) -> NewsEmbedding:
        if self._embedding is None:
            self._embedding = NewsEmbedding()
        return self._embedding

    def _morph_tagger_instance(self) -> NewsMorphTagger:
        if self._morph_tagger is None:
            self._morph_tagger = NewsMorphTagger(self._embedding_instance())
        return self._morph_tagger

    def _syntax_parser_instance(self) -> NewsSyntaxParser:
        if self._syntax_parser is None:
            self._syntax_parser = NewsSyntaxParser(self._embedding_instance())
        return self._syntax_parser

    def _ner_tagger_instance(self) -> NewsNERTagger:
        if self._ner_tagger is None:
            self._ner_tagger = NewsNERTagger(self._embedding_instance())
        return self._ner_tagger

    def _extract_domain_signals(
        self,
        text: str,
        alias_matches: list[AliasTextMatch],
        facts: list[ExtractedFact],
    ) -> list[DomainSignal]:
        signals: list[DomainSignal] = []
        for compiled_rule in self._compiled_signal_rules:
            rule_config = compiled_rule.config
            signals.extend(
                DomainSignal(
                    id=f"signal-{len(signals) + 1}",
                    text=match_text,
                    type=rule_config.type,
                    label=rule_config.label,
                    range=TextRange(start=start, stop=stop),
                    source="yargy",
                    confidence=rule_config.confidence,
                    color=rule_config.color,
                    explanation=(
                        f"Сработало правило доменного сигнала «{rule_config.label}» "
                        f"({rule_config.type}) через точную или лемматическую фразу."
                    ),
                    settings_refs=[_rule_settings_ref("signals", rule_config.type, rule_config.label)],
                )
                for start, stop, match_text in self._find_phrase_matches(
                    text,
                    compiled_rule.exact_phrases,
                    compiled_rule.parser,
                )
            )
            for alias_match in alias_matches:
                if not _rule_matches_alias(rule_config, alias_match.config):
                    continue
                signals.append(
                    DomainSignal(
                        id=f"signal-{len(signals) + 1}",
                        text=alias_match.text,
                        type=rule_config.type,
                        label=rule_config.label,
                        range=TextRange(start=alias_match.start, stop=alias_match.stop),
                        source="alias_catalog",
                        confidence=rule_config.confidence,
                        color=rule_config.color,
                        explanation=(
                            f"Сигнал «{rule_config.label}» зависит от alias "
                            f"«{alias_match.config.canonical}» из каталога "
                            f"{alias_match.config.catalog} ({alias_match.config.key})."
                        ),
                        settings_refs=[
                            _rule_settings_ref("signals", rule_config.type, rule_config.label),
                            _alias_settings_ref(alias_match.config),
                        ],
                    )
                )
            for fact in facts:
                if not _rule_matches_fact(rule_config, fact):
                    continue
                signals.append(
                    DomainSignal(
                        id=f"signal-{len(signals) + 1}",
                        text=fact.text,
                        type=rule_config.type,
                        label=rule_config.label,
                        range=fact.range,
                        source="fact_dependency",
                        confidence=rule_config.confidence,
                        color=rule_config.color,
                        explanation=(
                            f"Сигнал «{rule_config.label}» зависит от найденного факта "
                            f"«{fact.label}»: «{fact.text}»."
                        ),
                        settings_refs=[
                            _rule_settings_ref("signals", rule_config.type, rule_config.label),
                            *(
                                fact.settings_refs
                                or [_rule_settings_ref("facts", fact.type, fact.label)]
                            ),
                        ],
                    )
                )
        return _dedupe_signals(signals)

    def _extract_facts(
        self,
        text: str,
        alias_matches: list[AliasTextMatch],
    ) -> list[ExtractedFact]:
        facts: list[ExtractedFact] = []
        for compiled_rule in self._compiled_fact_rules:
            rule_config = compiled_rule.config
            facts.extend(
                ExtractedFact(
                    id=f"fact-{len(facts) + 1}",
                    text=match_text,
                    type=rule_config.type,
                    label=rule_config.label,
                    range=TextRange(start=start, stop=stop),
                    source="yargy",
                    confidence=rule_config.confidence,
                    explanation=(
                        f"Сработало правило факта «{rule_config.label}» "
                        f"({rule_config.type}) через точную или лемматическую фразу."
                    ),
                    settings_refs=[_rule_settings_ref("facts", rule_config.type, rule_config.label)],
                )
                for start, stop, match_text in self._find_phrase_matches(
                    text,
                    compiled_rule.exact_phrases,
                    compiled_rule.parser,
                )
            )
        for alias_match in alias_matches:
            alias_config = alias_match.config
            facts.extend(
                ExtractedFact(
                    id=f"fact-{len(facts) + offset + 1}",
                    text=alias_match.text,
                    type=fact_type,
                    label=_alias_fact_label(alias_config, fact_type),
                    range=TextRange(start=alias_match.start, stop=alias_match.stop),
                    source="alias_catalog",
                    confidence=alias_config.confidence,
                    explanation=(
                        f"Найден alias «{alias_config.canonical}» в каталоге "
                        f"{alias_config.catalog} ({alias_config.key}); он выпускает "
                        f"fact_type «{fact_type}»."
                    ),
                    settings_refs=[_alias_settings_ref(alias_config)],
                )
                for offset, fact_type in enumerate(alias_config.fact_types)
            )
        return _dedupe_facts(facts)

    def _compile_phrase_rules(
        self,
        rule_configs: tuple[PhraseRuleConfig, ...],
    ) -> tuple[CompiledPhraseRule, ...]:
        return tuple(
            CompiledPhraseRule(
                config=rule_config,
                exact_phrases=_compile_exact_phrases(rule_config.phrases),
                parser=self._build_parser(rule_config),
            )
            for rule_config in rule_configs
        )

    def _compile_alias_rules(
        self,
        alias_configs: tuple[AliasRuleConfig, ...],
    ) -> tuple[CompiledAliasRule, ...]:
        return tuple(
            CompiledAliasRule(
                config=alias_config,
                exact_phrases=_compile_exact_phrases(
                    tuple(
                        tuple(alias.strip().split())
                        for alias in alias_config.aliases
                        if alias.strip()
                    )
                ),
                normalized_aliases=_compile_normalized_aliases(
                    alias_config.aliases,
                    self._config.alias_matching,
                ),
            )
            for alias_config in alias_configs
        )

    def _build_parser(self, rule_config: PhraseRuleConfig) -> Any | None:
        yargy_rules = [
            rule(*[self._token_predicate(token) for token in pattern.tokens])
            for pattern in rule_config.patterns
        ]
        if not yargy_rules:
            return None
        return _parser_from_rules(yargy_rules, tokenizer=self._yargy_tokenizer)

    def _find_alias_matches(self, text: str) -> list[AliasTextMatch]:
        matches: list[AliasTextMatch] = []
        seen: set[tuple[str, int, int]] = set()
        compact_text = _alias_compact_document(text, self._config.alias_matching)
        for compiled_alias in self._compiled_alias_rules:
            for start, stop, match_text in self._find_phrase_matches(
                text,
                compiled_alias.exact_phrases,
                None,
            ):
                key = (compiled_alias.config.key, start, stop)
                if key in seen:
                    continue
                seen.add(key)
                matches.append(
                    AliasTextMatch(
                        config=compiled_alias.config,
                        start=start,
                        stop=stop,
                        text=match_text,
                    )
                )
            for start, stop in _find_normalized_alias_matches(
                text,
                compact_text,
                compiled_alias.normalized_aliases,
                self._config.alias_matching,
            ):
                key = (compiled_alias.config.key, start, stop)
                if key in seen:
                    continue
                seen.add(key)
                matches.append(
                    AliasTextMatch(
                        config=compiled_alias.config,
                        start=start,
                        stop=stop,
                        text=text[start:stop],
                    )
                )
        return _prefer_longest_non_overlapping_alias_matches(matches)

    def _find_phrase_matches(
        self,
        text: str,
        exact_phrases: tuple[CompiledExactPhrase, ...],
        parser: Any | None,
    ) -> list[tuple[int, int, str]]:
        matches = _find_exact_matches(text, exact_phrases)
        if parser is not None:
            search_text = text.lower()
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=UserWarning, module="pymorphy2.analyzer")
                warnings.filterwarnings("ignore", message="pkg_resources is deprecated.*")
                for match in parser.findall(search_text):
                    matches.append(
                        (match.span.start, match.span.stop, text[match.span.start:match.span.stop])
                    )
        return sorted(matches, key=lambda item: (item[0], item[1], item[2].lower()))

    def _token_predicate(self, token: RuleTokenConfig) -> Any:
        if token.predicate == "normalized":
            return normalized(token.value)
        raise ValueError(f"unsupported Yargy token predicate: {token.predicate}")


def _compile_exact_phrases(phrases: tuple[tuple[str, ...], ...]) -> tuple[CompiledExactPhrase, ...]:
    return tuple(
        CompiledExactPhrase(pattern=_exact_phrase_pattern(phrase))
        for phrase in phrases
        if _clean_phrase_tokens(phrase)
    )


def _compile_normalized_aliases(
    aliases: tuple[str, ...],
    settings: AliasMatchingConfig,
) -> tuple[CompiledAliasText, ...]:
    compiled: list[CompiledAliasText] = []
    seen: set[str] = set()
    for alias in aliases:
        compact_document = _alias_compact_document(alias, settings)
        compact = compact_document.text
        if not compact or compact in seen:
            continue
        seen.add(compact)
        word_count = len(compact_document.word_ranges)
        compiled.append(
            CompiledAliasText(
                compact=compact,
                fuzzy_distance=_alias_fuzzy_distance(alias, compact, settings),
                max_word_span=word_count,
                script=_single_script(compact_document.word_scripts),
            )
        )
    return tuple(compiled)


def _exact_phrase_pattern(phrase: tuple[str, ...]) -> re.Pattern[str]:
    body = r"[^\w]+".join(re.escape(token) for token in _clean_phrase_tokens(phrase))
    return re.compile(rf"(?<![\w]){body}(?![\w])", flags=re.UNICODE)


def _clean_phrase_tokens(phrase: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(token.strip().lower() for token in phrase if token.strip())


def _find_exact_matches(
    text: str,
    exact_phrases: tuple[CompiledExactPhrase, ...],
) -> list[tuple[int, int, str]]:
    search_text = text.lower()
    return [
        (match.start(), match.end(), text[match.start():match.end()])
        for exact_phrase in exact_phrases
        for match in exact_phrase.pattern.finditer(search_text)
    ]


def _find_normalized_alias_matches(
    original_text: str,
    compact_text: AliasCompactDocument,
    aliases: tuple[CompiledAliasText, ...],
    settings: AliasMatchingConfig,
) -> list[tuple[int, int]]:
    if not compact_text.text:
        return []
    matches: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for alias in aliases:
        for start, stop in _find_compact_exact_matches(original_text, compact_text, alias.compact):
            if (start, stop) not in seen:
                seen.add((start, stop))
                matches.append((start, stop))
        if settings.fuzzy_enabled and alias.fuzzy_distance > 0:
            for start, stop in _find_compact_fuzzy_matches(
                original_text,
                compact_text,
                alias.compact,
                alias.fuzzy_distance,
                alias.max_word_span,
                alias.script,
            ):
                if (start, stop) not in seen:
                    seen.add((start, stop))
                    matches.append((start, stop))
    return matches


def _prefer_longest_non_overlapping_alias_matches(
    matches: list[AliasTextMatch],
) -> list[AliasTextMatch]:
    kept: list[AliasTextMatch] = []
    for match in sorted(
        matches,
        key=lambda item: (
            item.start,
            -(item.stop - item.start),
            item.config.catalog,
            item.config.key,
            item.text.casefold(),
        ),
    ):
        if any(_ranges_overlap(match.start, match.stop, item.start, item.stop) for item in kept):
            continue
        kept.append(match)
    return sorted(kept, key=lambda item: (item.start, item.stop, item.text.lower()))


def _ranges_overlap(left_start: int, left_stop: int, right_start: int, right_stop: int) -> bool:
    return left_start < right_stop and right_start < left_stop


def _find_compact_exact_matches(
    original_text: str,
    compact_text: AliasCompactDocument,
    alias: str,
) -> list[tuple[int, int]]:
    matches: list[tuple[int, int]] = []
    start = compact_text.text.find(alias)
    while start >= 0:
        stop = start + len(alias)
        original_start = compact_text.indexes[start]
        original_stop = compact_text.indexes[stop - 1] + 1
        if _has_original_boundaries(original_text, original_start, original_stop):
            matches.append((original_start, original_stop))
        start = compact_text.text.find(alias, start + 1)
    return matches


def _find_compact_fuzzy_matches(
    original_text: str,
    compact_text: AliasCompactDocument,
    alias: str,
    max_distance: int,
    max_word_span: int,
    alias_script: str | None,
) -> list[tuple[int, int]]:
    matches: list[tuple[int, int]] = []
    alias_length = len(alias)
    min_length = max(1, alias_length - max_distance)
    max_length = alias_length + max_distance
    for range_index, (start, _word_stop) in enumerate(compact_text.word_ranges):
        for _next_index, (_next_start, stop) in enumerate(
            compact_text.word_ranges[range_index:],
            start=range_index,
        ):
            if _next_index - range_index + 1 > max_word_span:
                break
            window_length = stop - start
            if window_length < min_length:
                continue
            if window_length > max_length:
                break
            window = compact_text.text[start:stop]
            if _bounded_levenshtein(window, alias, max_distance) > max_distance:
                continue
            if not _candidate_scripts_match(
                compact_text.word_scripts[range_index : _next_index + 1],
                alias_script,
            ):
                continue
            original_start = compact_text.indexes[start]
            original_stop = compact_text.indexes[stop - 1] + 1
            if _has_original_boundaries(original_text, original_start, original_stop):
                matches.append((original_start, original_stop))
    return matches


def _alias_compact_document(text: str, settings: AliasMatchingConfig) -> AliasCompactDocument:
    chars: list[str] = []
    indexes: list[int] = []
    word_ranges: list[tuple[int, int]] = []
    word_scripts: list[str | None] = []
    for match in re.finditer(r"\w+|\W+", text, flags=re.UNICODE):
        token = match.group(0)
        if not any(char.isalnum() for char in token):
            if not settings.normalize_separators:
                for offset, char in enumerate(token):
                    normalized_char = char.casefold()
                    if settings.normalize_yo:
                        normalized_char = normalized_char.replace("ё", "е")
                    for item in normalized_char:
                        chars.append(item)
                        indexes.append(match.start() + offset)
            continue
        word_start = len(chars)
        target_script = _dominant_script(token) if settings.normalize_latin_confusables else None
        for offset, char in enumerate(token):
            for normalized_char in _normalize_alias_char(char, settings, target_script):
                if normalized_char.isalnum():
                    chars.append(normalized_char)
                    indexes.append(match.start() + offset)
        if len(chars) > word_start:
            word_ranges.append((word_start, len(chars)))
            word_scripts.append(target_script)
    return AliasCompactDocument(
        text="".join(chars),
        indexes=tuple(indexes),
        word_ranges=tuple(word_ranges),
        word_scripts=tuple(word_scripts),
    )


def _normalize_alias_char(
    char: str,
    settings: AliasMatchingConfig,
    target_script: str | None,
) -> str:
    value = char.casefold()
    if settings.normalize_yo:
        value = value.replace("ё", "е")
    if target_script == "cyrillic":
        value = "".join(_LATIN_TO_CYRILLIC_CONFUSABLES.get(item, item) for item in value)
    elif target_script == "latin":
        value = "".join(_CYRILLIC_TO_LATIN_CONFUSABLES.get(item, item) for item in value)
    return value


def _dominant_script(token: str) -> str | None:
    latin_count = sum(1 for char in token.casefold() if "a" <= char <= "z")
    cyrillic_count = sum(1 for char in token.casefold() if "а" <= char <= "я" or char == "ё")
    if cyrillic_count > 0 and cyrillic_count >= latin_count:
        return "cyrillic"
    if latin_count > 0:
        return "latin"
    return None


def _alias_fuzzy_distance(alias: str, compact: str, settings: AliasMatchingConfig) -> int:
    if not settings.fuzzy_enabled:
        return 0
    if compact.casefold() in settings.fuzzy_excluded_aliases or alias.casefold() in settings.fuzzy_excluded_aliases:
        return 0
    if len(compact) < settings.fuzzy_min_length:
        return 0
    if len(compact) >= settings.fuzzy_long_min_length:
        return settings.fuzzy_long_max_distance
    return settings.fuzzy_max_distance


def _single_script(scripts: tuple[str | None, ...]) -> str | None:
    concrete_scripts = {script for script in scripts if script is not None}
    if len(concrete_scripts) == 1:
        return next(iter(concrete_scripts))
    return None


def _candidate_scripts_match(candidate_scripts: tuple[str | None, ...], alias_script: str | None) -> bool:
    if alias_script is None:
        return True
    return all(script is None or script == alias_script for script in candidate_scripts)


def _bounded_levenshtein(left: str, right: str, max_distance: int) -> int:
    if abs(len(left) - len(right)) > max_distance:
        return max_distance + 1
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        row_min = current[0]
        for right_index, right_char in enumerate(right, start=1):
            cost = 0 if left_char == right_char else 1
            current_value = min(
                previous[right_index] + 1,
                current[right_index - 1] + 1,
                previous[right_index - 1] + cost,
            )
            current.append(current_value)
            row_min = min(row_min, current_value)
        if row_min > max_distance:
            return max_distance + 1
        previous = current
    return previous[-1]


def _has_original_boundaries(text: str, start: int, stop: int) -> bool:
    return (start <= 0 or not text[start - 1].isalnum()) and (
        stop >= len(text) or not text[stop].isalnum()
    )


def _parser_from_rules(yargy_rules: list[Any], tokenizer: Any | None = None) -> Any:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=UserWarning, module="pymorphy2.analyzer")
        warnings.filterwarnings("ignore", message="pkg_resources is deprecated.*")
        return Parser(or_(*yargy_rules), tokenizer=tokenizer)


_LATIN_TO_CYRILLIC_CONFUSABLES = {
    "a": "а",
    "b": "в",
    "c": "с",
    "e": "е",
    "h": "н",
    "k": "к",
    "m": "м",
    "o": "о",
    "p": "р",
    "t": "т",
    "x": "х",
    "y": "у",
}

_CYRILLIC_TO_LATIN_CONFUSABLES = {
    "а": "a",
    "в": "b",
    "с": "c",
    "е": "e",
    "н": "h",
    "к": "k",
    "м": "m",
    "о": "o",
    "р": "p",
    "т": "t",
    "х": "x",
    "у": "y",
}


def _alias_fact_label(alias_config: AliasRuleConfig, fact_type: str) -> str:
    prefix = {
        "vendor": "Вендор",
        "protocol": "Протокол",
        "device": "Устройство",
        "software": "ПО",
        "model": "Модель",
    }.get(fact_type, alias_config.kind)
    return f"{prefix}: {alias_config.canonical}"


def _rule_settings_ref(section: str, key: str, label: str) -> SettingsReference:
    return SettingsReference(
        section=section,
        key=key,
        label=label,
        kind="rule",
    )


def _alias_settings_ref(alias_config: AliasRuleConfig) -> SettingsReference:
    return SettingsReference(
        section="aliases",
        catalog=alias_config.catalog,
        key=alias_config.key,
        label=_alias_ref_label(alias_config),
        kind="alias",
    )


def _alias_ref_label(alias_config: AliasRuleConfig) -> str:
    prefix = {
        "vendor": "Вендор",
        "protocol": "Протокол",
        "device": "Устройство",
        "software": "ПО",
        "model": "Модель",
    }.get(alias_config.kind, alias_config.kind)
    return f"{prefix}: {alias_config.canonical}"


def _fact_type_labels(config: NlpPipelineConfig) -> dict[str, str]:
    labels = {
        "vendor": "Вендор",
        "protocol": "Протокол",
        "device": "Устройство",
        "software": "ПО",
        "model": "Модель",
    }
    labels.update({rule.type: rule.label for rule in config.facts})
    return labels


def _rule_matches_alias(rule_config: PhraseRuleConfig, alias_config: AliasRuleConfig) -> bool:
    for dependency in rule_config.match.aliases:
        if dependency.catalogs and alias_config.catalog not in dependency.catalogs:
            continue
        if dependency.keys and alias_config.key not in dependency.keys:
            continue
        if dependency.kinds and alias_config.kind not in dependency.kinds:
            continue
        return True
    return False


def _rule_matches_fact(rule_config: PhraseRuleConfig, fact: ExtractedFact) -> bool:
    return any(fact.type in dependency.types for dependency in rule_config.match.facts)


def _dedupe_signals(signals: list[DomainSignal]) -> list[DomainSignal]:
    deduped: list[DomainSignal] = []
    seen: set[tuple[str, int, int, str]] = set()
    for signal in signals:
        key = (signal.type, signal.range.start, signal.range.stop, signal.text.lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(replace(signal, id=f"signal-{len(deduped) + 1}"))
    return deduped


def _dedupe_facts(facts: list[ExtractedFact]) -> list[ExtractedFact]:
    deduped: list[ExtractedFact] = []
    seen: set[tuple[str, int, int, str]] = set()
    for fact in facts:
        key = (fact.type, fact.range.start, fact.range.stop, fact.text.lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(replace(fact, id=f"fact-{len(deduped) + 1}"))
    return deduped
