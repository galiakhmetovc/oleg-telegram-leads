"""Telegram Stage 2 text normalization over immutable raw exports."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.models.telegram_sources import telegram_raw_export_runs_table

STAGE_NAME = "telegram_text_normalization"
STAGE_VERSION = "1"

URL_RE = re.compile(r"(?:https?://|t\.me/|telegram\.me/)[^\s<>()\"']+", re.IGNORECASE)
WHITESPACE_RE = re.compile(r"\s+")
TOKEN_RE = re.compile(
    r"\[URL\]|[A-Za-zА-Яа-яЁё]+(?:[-'][A-Za-zА-Яа-яЁё]+)*|\d+(?:[.,]\d+)?",
    re.UNICODE,
)
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
LATIN_RE = re.compile(r"[A-Za-z]")

PYMORPHY_POS_TO_UNIVERSAL = {
    "NOUN": "NOUN",
    "ADJF": "ADJ",
    "ADJS": "ADJ",
    "COMP": "ADJ",
    "VERB": "VERB",
    "INFN": "VERB",
    "PRTF": "VERB",
    "PRTS": "VERB",
    "GRND": "VERB",
    "NUMR": "NUM",
    "ADVB": "ADV",
    "PRED": "ADV",
    "NPRO": "PRON",
    "PREP": "ADP",
    "CONJ": "CCONJ",
    "PRCL": "PART",
    "INTJ": "INTJ",
}


@dataclass(frozen=True)
class TelegramTextNormalizationResult:
    raw_export_run_id: str
    output_dir: Path
    texts_parquet_path: Path
    summary_path: Path
    metrics: dict[str, Any]


@dataclass(frozen=True)
class NormalizedText:
    raw_text: str
    clean_text: str
    lang: str
    tokens: list[str]
    lemmas: list[str]
    pos_tags: list[str]
    token_map: list[dict[str, str]]
    status: str
    error: str | None = None


class TelegramTextNormalizationService:
    """Normalize raw Telegram text into a reusable parquet layer for NLP/search stages."""

    def __init__(
        self, session: Session, *, processed_root: Path | str = "./data/processed"
    ) -> None:
        self.session = session
        self.processed_root = Path(processed_root)
        self._ru_analyzer: Any | None = None
        self._en_nlp: Any | None = None
        self._en_nlp_loaded = False

    def write_texts(self, raw_export_run_id: str) -> TelegramTextNormalizationResult:
        run = self._require_run(raw_export_run_id)
        messages_path = _resolve_path(run["messages_parquet_path"])

        output_dir = (
            self.processed_root
            / "telegram_texts"
            / f"source_id={run['monitored_source_id']}"
            / f"run_id={raw_export_run_id}"
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        texts_parquet_path = output_dir / "texts.parquet"
        summary_path = output_dir / "text_normalization_summary.json"

        metrics_accumulator = _TextMetricsAccumulator()
        validation_sample: list[dict[str, Any]] = []
        token_arrays_same_length = True
        writer: pq.ParquetWriter | None = None
        wrote_rows = False
        schema = _texts_schema()
        try:
            parquet_file = pq.ParquetFile(messages_path)
            for batch in parquet_file.iter_batches(batch_size=2000):
                normalized_rows = [self._normalize_row(row, run) for row in batch.to_pylist()]
                for normalized_row in normalized_rows:
                    metrics_accumulator.add(normalized_row)
                    token_arrays_same_length = (
                        token_arrays_same_length and _token_arrays_same_length_row(normalized_row)
                    )
                    _add_validation_sample(validation_sample, normalized_row)
                if normalized_rows:
                    table = pa.Table.from_pylist(normalized_rows, schema=schema)
                    writer = writer or pq.ParquetWriter(
                        texts_parquet_path,
                        schema=schema,
                        compression="zstd",
                    )
                    writer.write_table(table)
                    wrote_rows = True
            if not wrote_rows:
                pq.write_table(
                    pa.Table.from_pylist([], schema=schema),
                    texts_parquet_path,
                    compression="zstd",
                )
        finally:
            if writer is not None:
                writer.close()
        metrics = metrics_accumulator.finish()
        summary = _summary_payload(
            run=run,
            raw_export_run_id=raw_export_run_id,
            messages_path=messages_path,
            texts_parquet_path=texts_parquet_path,
            summary_path=summary_path,
            metrics=metrics,
            token_arrays_same_length=token_arrays_same_length,
            validation_sample=validation_sample,
        )
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        metadata = dict(run["metadata_json"] or {})
        metadata["text_normalization"] = {
            "stage": STAGE_NAME,
            "stage_version": STAGE_VERSION,
            "texts_parquet_path": str(texts_parquet_path),
            "summary_path": str(summary_path),
            "generated_at": summary["generated_at"],
            "total_messages": metrics["total_messages"],
            "rows_with_text": metrics["rows_with_text"],
            "tokenizer_error_rows": metrics["tokenizer_error_rows"],
        }
        self.session.execute(
            update(telegram_raw_export_runs_table)
            .where(telegram_raw_export_runs_table.c.id == raw_export_run_id)
            .values(metadata_json=metadata)
        )
        self.session.commit()
        return TelegramTextNormalizationResult(
            raw_export_run_id=raw_export_run_id,
            output_dir=output_dir,
            texts_parquet_path=texts_parquet_path,
            summary_path=summary_path,
            metrics=metrics,
        )

    def _require_run(self, raw_export_run_id: str) -> dict[str, Any]:
        row = (
            self.session.execute(
                select(telegram_raw_export_runs_table).where(
                    telegram_raw_export_runs_table.c.id == raw_export_run_id
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise KeyError(raw_export_run_id)
        if row["status"] != "succeeded":
            raise ValueError("text normalization requires a succeeded raw export run")
        return dict(row)

    def _normalize_row(self, row: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_text(_combined_text(row))
        return {
            "export_run_id": run["id"],
            "monitored_source_id": run["monitored_source_id"],
            "telegram_message_id": row.get("telegram_message_id"),
            "row_index": row.get("row_index"),
            "date": row.get("date"),
            "message_url": row.get("message_url"),
            "raw_text": normalized.raw_text,
            "clean_text": normalized.clean_text,
            "normalization_lang": normalized.lang,
            "tokens_json": _json_string(normalized.tokens),
            "lemmas_json": _json_string(normalized.lemmas),
            "pos_tags_json": _json_string(normalized.pos_tags),
            "token_map_json": _json_string(normalized.token_map),
            "token_count": len(normalized.tokens),
            "has_text": bool(normalized.raw_text.strip()),
            "normalization_status": normalized.status,
            "normalization_error": normalized.error,
            "raw_message_json": row.get("raw_message_json"),
        }

    def _normalize_text(self, raw_text: str) -> NormalizedText:
        raw_text = raw_text or ""
        clean_text = _clean_text(raw_text)
        if not clean_text:
            return NormalizedText(
                raw_text=raw_text,
                clean_text="",
                lang="unknown",
                tokens=[],
                lemmas=[],
                pos_tags=[],
                token_map=[],
                status="empty_text",
            )

        lang = _detect_lang(clean_text)
        try:
            tokens, lemmas, pos_tags = self._tokens_lemmas_pos(clean_text, lang)
        except Exception as exc:  # pragma: no cover - defensive per-row quarantine
            return NormalizedText(
                raw_text=raw_text,
                clean_text=clean_text,
                lang=lang,
                tokens=[],
                lemmas=[],
                pos_tags=[],
                token_map=[],
                status="tokenizer_error",
                error=str(exc) or exc.__class__.__name__,
            )

        token_map = [
            {"token": token, "lemma": lemma, "pos": pos}
            for token, lemma, pos in zip(tokens, lemmas, pos_tags, strict=True)
        ]
        return NormalizedText(
            raw_text=raw_text,
            clean_text=clean_text,
            lang=lang,
            tokens=tokens,
            lemmas=lemmas,
            pos_tags=pos_tags,
            token_map=token_map,
            status="normalized",
        )

    def _tokens_lemmas_pos(
        self,
        clean_text: str,
        lang: str,
    ) -> tuple[list[str], list[str], list[str]]:
        if lang == "en":
            return self._english_tokens(clean_text)
        tokens = _regex_tokens(clean_text)
        normalized = [self._normalize_token(token) for token in tokens]
        return (
            [item["token"] for item in normalized],
            [item["lemma"] for item in normalized],
            [item["pos"] for item in normalized],
        )

    def _english_tokens(self, clean_text: str) -> tuple[list[str], list[str], list[str]]:
        nlp = self._load_spacy()
        if nlp is None:
            tokens = _regex_tokens(clean_text)
            return (
                tokens,
                [_fallback_lemma(token) for token in tokens],
                [_fallback_pos(token) for token in tokens],
            )
        doc = nlp(clean_text)
        tokens: list[str] = []
        lemmas: list[str] = []
        pos_tags: list[str] = []
        for token in doc:
            if token.is_space or token.is_punct:
                continue
            tokens.append(token.text)
            lemmas.append(token.lemma_.lower() if token.lemma_ else token.text.lower())
            pos_tags.append(token.pos_ or "X")
        return tokens, lemmas, pos_tags

    def _normalize_token(self, token: str) -> dict[str, str]:
        if token == "[URL]":
            return {"token": token, "lemma": "url", "pos": "X"}
        if CYRILLIC_RE.search(token):
            return self._russian_token(token)
        return {
            "token": token,
            "lemma": _fallback_lemma(token),
            "pos": _fallback_pos(token),
        }

    def _russian_token(self, token: str) -> dict[str, str]:
        analyzer = self._load_pymorphy()
        if analyzer is None:
            return {"token": token, "lemma": token.lower(), "pos": "X"}
        parsed = analyzer.parse(token)[0]
        lemma = parsed.normal_form or token.lower()
        source_pos = parsed.tag.POS
        pos = PYMORPHY_POS_TO_UNIVERSAL.get(source_pos or "", "X")
        if pos == "NOUN" and token[:1].isupper():
            pos = "PROPN"
        return {"token": token, "lemma": lemma, "pos": pos}

    def _load_pymorphy(self) -> Any | None:
        if self._ru_analyzer is not None:
            return self._ru_analyzer
        try:
            import pymorphy3  # type: ignore[import-not-found]
        except Exception:
            return None
        self._ru_analyzer = pymorphy3.MorphAnalyzer()
        return self._ru_analyzer

    def _load_spacy(self) -> Any | None:
        if self._en_nlp_loaded:
            return self._en_nlp
        self._en_nlp_loaded = True
        try:
            import spacy  # type: ignore[import-not-found]
        except Exception:
            self._en_nlp = None
            return None
        for model_name in ("en_core_web_md", "en_core_web_sm"):
            try:
                self._en_nlp = spacy.load(model_name)
                return self._en_nlp
            except Exception:
                continue
        self._en_nlp = None
        return None


def _combined_text(row: dict[str, Any]) -> str:
    return "\n".join(
        str(value)
        for value in (row.get("text_plain"), row.get("caption"))
        if value is not None and str(value).strip()
    )


def _clean_text(raw_text: str) -> str:
    lowered = raw_text.lower()
    without_urls = URL_RE.sub("[URL]", lowered)
    return WHITESPACE_RE.sub(" ", without_urls).strip()


def _detect_lang(clean_text: str) -> str:
    value = clean_text.replace("[URL]", "")
    cyrillic_count = len(CYRILLIC_RE.findall(value))
    latin_count = len(LATIN_RE.findall(value))
    if cyrillic_count == 0 and latin_count == 0:
        return "unknown"
    if cyrillic_count > 0 and latin_count > 0:
        return "mixed"
    if cyrillic_count > 0:
        return "ru"
    return "en"


def _regex_tokens(clean_text: str) -> list[str]:
    return TOKEN_RE.findall(clean_text)


def _fallback_lemma(token: str) -> str:
    if token == "[URL]":
        return "url"
    return token.lower()


def _fallback_pos(token: str) -> str:
    if token == "[URL]":
        return "X"
    if token.replace(",", "").replace(".", "").isdigit():
        return "NUM"
    return "X"


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    accumulator = _TextMetricsAccumulator()
    for row in rows:
        accumulator.add(row)
    return accumulator.finish()


class _TextMetricsAccumulator:
    def __init__(self) -> None:
        self.total = 0
        self.rows_with_text = 0
        self.total_tokens = 0
        self.statuses: Counter[str] = Counter()
        self.languages: Counter[str] = Counter()
        self.lemmas: Counter[str] = Counter()

    def add(self, row: dict[str, Any]) -> None:
        self.total += 1
        if row["has_text"]:
            self.rows_with_text += 1
        self.total_tokens += int(row["token_count"] or 0)
        self.statuses[str(row["normalization_status"])] += 1
        self.languages[str(row["normalization_lang"])] += 1
        self.lemmas.update(
            lemma
            for lemma in json.loads(str(row["lemmas_json"]))
            if isinstance(lemma, str) and lemma and lemma != "url"
        )

    def finish(self) -> dict[str, Any]:
        return {
            "total_messages": self.total,
            "rows_with_text": self.rows_with_text,
            "empty_text_rows": self.statuses.get("empty_text", 0),
            "normalized_rows": self.statuses.get("normalized", 0),
            "tokenizer_error_rows": self.statuses.get("tokenizer_error", 0),
            "total_tokens": self.total_tokens,
            "status_distribution": dict(sorted(self.statuses.items())),
            "language_distribution": dict(sorted(self.languages.items())),
            "top_lemmas": [
                {"lemma": lemma, "count": count} for lemma, count in self.lemmas.most_common(50)
            ],
        }


def _summary_payload(
    *,
    run: dict[str, Any],
    raw_export_run_id: str,
    messages_path: Path,
    texts_parquet_path: Path,
    summary_path: Path,
    metrics: dict[str, Any],
    token_arrays_same_length: bool,
    validation_sample: list[dict[str, Any]],
) -> dict[str, Any]:
    generated_at = utc_now()
    return {
        "stage": STAGE_NAME,
        "stage_version": STAGE_VERSION,
        "generated_at": generated_at.isoformat(),
        "input": {
            "raw_export_run_id": raw_export_run_id,
            "monitored_source_id": run["monitored_source_id"],
            "source_ref": run["source_ref"],
            "source_kind": run["source_kind"],
            "username": run["username"],
            "messages_parquet_path": str(messages_path),
        },
        "outputs": {
            "texts_parquet_path": str(texts_parquet_path),
            "summary_path": str(summary_path),
        },
        "metrics": metrics,
        "invariants": {
            "raw_text_preserved": True,
            "token_arrays_same_length": token_arrays_same_length,
            "empty_messages_preserved": True,
        },
        "validation_sample": validation_sample,
    }


def _validation_sample(rows: list[dict[str, Any]], limit: int = 50) -> list[dict[str, Any]]:
    sample: list[dict[str, Any]] = []
    for row in rows:
        _add_validation_sample(sample, row, limit=limit)
        if len(sample) >= limit:
            break
    return sample


def _token_arrays_same_length(rows: list[dict[str, Any]]) -> bool:
    for row in rows:
        if not _token_arrays_same_length_row(row):
            return False
    return True


def _add_validation_sample(
    sample: list[dict[str, Any]],
    row: dict[str, Any],
    *,
    limit: int = 50,
) -> None:
    if len(sample) >= limit or not row["has_text"]:
        return
    sample.append(
        {
            "telegram_message_id": row["telegram_message_id"],
            "message_url": row["message_url"],
            "raw_text": _truncate(str(row["raw_text"] or ""), 500),
            "clean_text": _truncate(str(row["clean_text"] or ""), 500),
            "normalization_lang": row["normalization_lang"],
            "tokens": json.loads(str(row["tokens_json"])),
            "lemmas": json.loads(str(row["lemmas_json"])),
            "pos_tags": json.loads(str(row["pos_tags_json"])),
        }
    )


def _token_arrays_same_length_row(row: dict[str, Any]) -> bool:
    tokens = json.loads(str(row["tokens_json"]))
    lemmas = json.loads(str(row["lemmas_json"]))
    pos_tags = json.loads(str(row["pos_tags_json"]))
    token_map = json.loads(str(row["token_map_json"]))
    return len(tokens) == len(lemmas) == len(pos_tags) == len(token_map)


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 3] + "..."


def _write_texts_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    schema = _texts_schema()
    table = (
        pa.Table.from_pylist(rows, schema=schema)
        if rows
        else pa.Table.from_pylist([], schema=schema)
    )
    pq.write_table(table, path, compression="zstd")


def _texts_schema() -> pa.Schema:
    return pa.schema(
        [
            ("export_run_id", pa.string()),
            ("monitored_source_id", pa.string()),
            ("telegram_message_id", pa.int64()),
            ("row_index", pa.int64()),
            ("date", pa.string()),
            ("message_url", pa.string()),
            ("raw_text", pa.string()),
            ("clean_text", pa.string()),
            ("normalization_lang", pa.string()),
            ("tokens_json", pa.string()),
            ("lemmas_json", pa.string()),
            ("pos_tags_json", pa.string()),
            ("token_map_json", pa.string()),
            ("token_count", pa.int64()),
            ("has_text", pa.bool_()),
            ("normalization_status", pa.string()),
            ("normalization_error", pa.string()),
            ("raw_message_json", pa.string()),
        ]
    )


def _json_string(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _resolve_path(value: Any) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else Path(".") / path
