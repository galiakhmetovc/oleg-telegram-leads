from __future__ import annotations

import warnings
from collections.abc import Callable

from natasha import Doc, MorphVocab, NewsEmbedding, NewsMorphTagger, NewsNERTagger
from natasha import NewsSyntaxParser, Segmenter
from yargy import Parser, or_, rule
from yargy.predicates import caseless

from app.domain.enrichment import DomainSignal, EnrichedEntity, EnrichedSentence, EnrichedToken
from app.domain.enrichment import EnrichmentMetrics, ExtractedFact, PipelineTraceItem
from app.domain.enrichment import SyntaxDependency, TextEnrichmentResult, TextRange
from app.infrastructure.nlp.config_loader import NlpPipelineConfig, PhraseRuleConfig

ProgressCallback = Callable[[str, int, str], None]


class RussianTextEnricher:
    def __init__(self, config: NlpPipelineConfig) -> None:
        self._config = config
        self._segmenter = Segmenter()
        self._morph_vocab = MorphVocab()
        self._embedding: NewsEmbedding | None = None
        self._morph_tagger: NewsMorphTagger | None = None
        self._syntax_parser: NewsSyntaxParser | None = None
        self._ner_tagger: NewsNERTagger | None = None

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

        facts = self._extract_facts(text) if self._config.is_enabled("facts") else []
        if self._config.is_enabled("facts"):
            mark("facts", 80, "Извлечены факты по Yargy-правилам")

        signals = (
            self._extract_domain_signals(text) if self._config.is_enabled("domain_signals") else []
        )
        if self._config.is_enabled("domain_signals"):
            mark("domain_signals", 90, "Найдены доменные сигналы-кандидаты")

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
                features={key: str(value) for key, value in getattr(token, "feats", {}).items()},
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
            for index, span in enumerate(doc.spans, start=1)
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

    def _extract_domain_signals(self, text: str) -> list[DomainSignal]:
        signals: list[DomainSignal] = []
        for rule_config in self._config.signals:
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
                )
                for start, stop, match_text in self._find_phrase_matches(text, rule_config)
            )
        return signals

    def _extract_facts(self, text: str) -> list[ExtractedFact]:
        facts: list[ExtractedFact] = []
        for rule_config in self._config.facts:
            facts.extend(
                ExtractedFact(
                    id=f"fact-{len(facts) + 1}",
                    text=match_text,
                    type=rule_config.type,
                    label=rule_config.label,
                    range=TextRange(start=start, stop=stop),
                    source="yargy",
                    confidence=rule_config.confidence,
                )
                for start, stop, match_text in self._find_phrase_matches(text, rule_config)
            )
        return facts

    def _find_phrase_matches(
        self,
        text: str,
        rule_config: PhraseRuleConfig,
    ) -> list[tuple[int, int, str]]:
        phrase_rules = [
            rule(*[caseless(word) for word in phrase])
            for phrase in rule_config.phrases
        ]
        matches: list[tuple[int, int, str]] = []
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning, module="pymorphy2.analyzer")
            warnings.filterwarnings("ignore", message="pkg_resources is deprecated.*")
            parser = Parser(or_(*phrase_rules))
            for match in parser.findall(text):
                matches.append((match.span.start, match.span.stop, text[match.span.start:match.span.stop]))
        return matches
