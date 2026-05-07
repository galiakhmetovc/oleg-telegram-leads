from __future__ import annotations

import re
import warnings
from dataclasses import dataclass

from natasha import Doc, MorphVocab, NewsEmbedding, NewsMorphTagger, Segmenter

_RULE_TOKEN_RE = re.compile(r"\w", flags=re.UNICODE)


@dataclass(frozen=True)
class SemanticRulePhrase:
    source_text: str
    lemmas: tuple[str, ...]

    @property
    def lemma_text(self) -> str:
        return " ".join(self.lemmas)


class RussianRulePhraseNormalizer:
    def __init__(self) -> None:
        self._segmenter = Segmenter()
        self._morph_vocab = MorphVocab()
        self._embedding = NewsEmbedding()
        self._morph_tagger = NewsMorphTagger(self._embedding)

    def to_semantic_phrase(self, text: str) -> SemanticRulePhrase:
        source_text = " ".join(text.split())
        if not source_text:
            raise ValueError("semantic pattern text must not be empty")

        doc = Doc(source_text)
        doc.segment(self._segmenter)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning, module="pymorphy2.analyzer")
            warnings.filterwarnings("ignore", message="pkg_resources is deprecated.*")
            doc.tag_morph(self._morph_tagger)
            lemmas = tuple(
                lemma
                for token in doc.tokens
                if _is_rule_token(token.text)
                for lemma in (_lemma_for_token(token, self._morph_vocab),)
                if lemma
            )

        if not lemmas:
            raise ValueError("semantic pattern text must contain at least one token")
        return SemanticRulePhrase(source_text=source_text, lemmas=lemmas)


def _is_rule_token(value: str) -> bool:
    return bool(_RULE_TOKEN_RE.search(value))


def _lemma_for_token(token: object, morph_vocab: MorphVocab) -> str:
    token.lemmatize(morph_vocab)  # type: ignore[attr-defined]
    lemma = str(getattr(token, "lemma", None) or getattr(token, "text", ""))
    return lemma.casefold()
