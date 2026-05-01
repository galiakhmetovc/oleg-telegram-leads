"""Chroma vector index for normalized Telegram text."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import blake2b, sha256
import json
import math
from pathlib import Path
import re
from typing import Any, Protocol

import pyarrow.parquet as pq
from sqlalchemy import select
from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.models.telegram_sources import telegram_raw_export_runs_table
from pur_leads.services.telegram_run_metadata import merge_raw_export_run_metadata

STAGE_NAME = "telegram_chroma_index"
STAGE_VERSION = "1"
DEFAULT_COLLECTION_NAME = "telegram_texts"
DEFAULT_EMBEDDING_PROFILE = "rubert_tiny2_v1"
RUBERT_TINY2_MODEL_NAME = "cointegrated/rubert-tiny2"
RUBERT_TINY2_DEFAULT_DIMENSIONS = 312
LOCAL_HASHING_PROFILE = "local_hashing_v1"
DEFAULT_EMBEDDING_DIMENSIONS = 384

TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+", re.UNICODE)


@dataclass(frozen=True)
class TelegramChromaIndexResult:
    raw_export_run_id: str
    chroma_path: Path
    collection_name: str
    summary_path: Path
    metrics: dict[str, Any]


class TextEmbedder(Protocol):
    profile: str
    model_name: str | None

    @property
    def dimensions(self) -> int: ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...


class TelegramChromaIndexService:
    """Build a local persistent Chroma index from Stage 2 normalized Telegram text."""

    def __init__(self, session: Session, *, chroma_root: Path | str = "./data/chroma") -> None:
        self.session = session
        self.chroma_root = Path(chroma_root)

    def write_index(
        self,
        raw_export_run_id: str,
        *,
        texts_parquet_path: Path | str | None = None,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        embedding_profile: str = DEFAULT_EMBEDDING_PROFILE,
        embedding_dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS,
        batch_size: int = 500,
        rebuild: bool = True,
    ) -> TelegramChromaIndexResult:
        run = self._require_run(raw_export_run_id)
        texts_path = (
            _resolve_path(texts_parquet_path)
            if texts_parquet_path is not None
            else _texts_path_from_metadata(run)
        )
        artifact_texts_path = _artifact_texts_path_from_metadata(run)
        chroma_path = (
            self.chroma_root
            / "telegram_texts"
            / f"source_id={run['monitored_source_id']}"
            / f"run_id={raw_export_run_id}"
        )
        chroma_path.mkdir(parents=True, exist_ok=True)
        summary_path = chroma_path / "chroma_index_summary.json"

        embedder = _build_embedder(
            embedding_profile,
            local_hashing_dimensions=embedding_dimensions,
        )
        client = _persistent_client(chroma_path)
        if rebuild:
            _delete_collection_if_exists(client, collection_name)
        collection = client.get_or_create_collection(
            name=collection_name,
            metadata={
                "stage": STAGE_NAME,
                "stage_version": STAGE_VERSION,
                "embedding_profile": embedder.profile,
                "embedding_model": embedder.model_name or "",
                "embedding_dimensions": embedder.dimensions,
                "hnsw:space": "cosine",
            },
        )
        total_text_rows = 0
        total_artifact_text_rows = 0
        indexed_message_documents = 0
        indexed_artifact_documents = 0
        skipped_empty_text_rows = 0
        skipped_empty_artifact_text_rows = 0
        sample_documents: list[dict[str, Any]] = []
        for arrow_batch in pq.ParquetFile(texts_path).iter_batches(batch_size=max(1, batch_size)):
            rows = arrow_batch.to_pylist()
            total_text_rows += len(rows)
            documents = _documents_from_rows(
                rows,
                raw_export_run_id=raw_export_run_id,
                monitored_source_id=str(run["monitored_source_id"]),
            )
            skipped_empty_text_rows += len(rows) - len(documents)
            indexed_message_documents += len(documents)
            _extend_sample_documents(sample_documents, documents)
            _upsert_documents(collection, documents, embedder=embedder)

        if artifact_texts_path is not None and artifact_texts_path.exists():
            for arrow_batch in pq.ParquetFile(artifact_texts_path).iter_batches(
                batch_size=max(1, batch_size)
            ):
                artifact_rows = arrow_batch.to_pylist()
                total_artifact_text_rows += len(artifact_rows)
                documents = _artifact_documents_from_rows(
                    artifact_rows,
                    raw_export_run_id=raw_export_run_id,
                    monitored_source_id=str(run["monitored_source_id"]),
                )
                skipped_empty_artifact_text_rows += len(artifact_rows) - len(documents)
                indexed_artifact_documents += len(documents)
                _extend_sample_documents(sample_documents, documents)
                _upsert_documents(collection, documents, embedder=embedder)

        metrics = {
            "total_text_rows": total_text_rows,
            "total_artifact_text_rows": total_artifact_text_rows,
            "indexed_documents": indexed_message_documents + indexed_artifact_documents,
            "indexed_message_documents": indexed_message_documents,
            "indexed_artifact_documents": indexed_artifact_documents,
            "skipped_empty_text_rows": skipped_empty_text_rows,
            "skipped_empty_artifact_text_rows": skipped_empty_artifact_text_rows,
            "embedding_profile": embedder.profile,
            "embedding_model": embedder.model_name,
            "embedding_dimensions": embedder.dimensions,
            "collection_count": collection.count(),
            "batch_size": max(1, batch_size),
        }
        summary = {
            "stage": STAGE_NAME,
            "stage_version": STAGE_VERSION,
            "generated_at": utc_now().isoformat(),
            "input": {
                "raw_export_run_id": raw_export_run_id,
                "monitored_source_id": run["monitored_source_id"],
                "source_ref": run["source_ref"],
                "source_kind": run["source_kind"],
                "username": run["username"],
                "texts_parquet_path": str(texts_path),
                "artifact_texts_parquet_path": (
                    str(artifact_texts_path) if artifact_texts_path is not None else None
                ),
            },
            "outputs": {
                "chroma_path": str(chroma_path),
                "collection_name": collection_name,
                "summary_path": str(summary_path),
            },
            "metrics": metrics,
            "sample_documents": [
                {
                    "id": item["id"],
                    "document": _truncate(item["document"], 500),
                    "metadata": item["metadata"],
                }
                for item in sample_documents
            ],
        }
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        merge_raw_export_run_metadata(
            self.session,
            raw_export_run_id,
            key="chroma_index",
            value={
                "stage": STAGE_NAME,
                "stage_version": STAGE_VERSION,
                "generated_at": summary["generated_at"],
                "texts_parquet_path": str(texts_path),
                "artifact_texts_parquet_path": (
                    str(artifact_texts_path) if artifact_texts_path is not None else None
                ),
                "chroma_path": str(chroma_path),
                "collection_name": collection_name,
                "embedding_profile": embedder.profile,
                "embedding_model": embedder.model_name,
                "embedding_dimensions": embedder.dimensions,
                "indexed_documents": indexed_message_documents + indexed_artifact_documents,
                "indexed_message_documents": indexed_message_documents,
                "indexed_artifact_documents": indexed_artifact_documents,
                "summary_path": str(summary_path),
            },
        )
        self.session.commit()
        return TelegramChromaIndexResult(
            raw_export_run_id=raw_export_run_id,
            chroma_path=chroma_path,
            collection_name=collection_name,
            summary_path=summary_path,
            metrics=metrics,
        )

    def query(
        self,
        *,
        chroma_path: Path | str,
        collection_name: str,
        query_text: str,
        n_results: int = 5,
        embedding_profile: str = DEFAULT_EMBEDDING_PROFILE,
        embedding_dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS,
    ) -> list[dict[str, Any]]:
        client = _persistent_client(Path(chroma_path))
        collection = client.get_collection(name=collection_name)
        embedder = _build_embedder(
            embedding_profile,
            local_hashing_dimensions=embedding_dimensions,
        )
        result = collection.query(
            query_embeddings=embedder.embed_texts([query_text]),
            n_results=max(1, n_results),
            include=["documents", "metadatas", "distances"],
        )
        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        return [
            {
                "id": item_id,
                "document": document,
                "metadata": metadata,
                "distance": distance,
            }
            for item_id, document, metadata, distance in zip(
                ids,
                documents,
                metadatas,
                distances,
                strict=False,
            )
        ]

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
            raise ValueError("Chroma indexing requires a succeeded raw export run")
        return dict(row)


def _documents_from_rows(
    rows: list[dict[str, Any]],
    *,
    raw_export_run_id: str,
    monitored_source_id: str,
) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for row in rows:
        if not row.get("has_text"):
            continue
        clean_text = str(row.get("clean_text") or "").strip()
        if not clean_text:
            continue
        lemmas = _json_list(row.get("lemmas_json"))
        embedding_text = " ".join([clean_text, " ".join(lemmas)]).strip()
        message_id = int(row["telegram_message_id"])
        row_index = int(row["row_index"])
        thread_fields = _thread_fields(row)
        documents.append(
            {
                "id": f"telegram-message-{message_id}-{row_index}",
                "document": clean_text,
                "embedding_text": embedding_text,
                "metadata": _metadata(
                    row,
                    raw_export_run_id=raw_export_run_id,
                    monitored_source_id=monitored_source_id,
                    text_hash=_text_hash(clean_text),
                    thread_fields=thread_fields,
                ),
            }
        )
    return documents


def _metadata(
    row: dict[str, Any],
    *,
    raw_export_run_id: str,
    monitored_source_id: str,
    text_hash: str,
    thread_fields: dict[str, Any],
) -> dict[str, str | int | float | bool]:
    return {
        "entity_type": "telegram_message",
        "raw_export_run_id": raw_export_run_id,
        "monitored_source_id": monitored_source_id,
        "telegram_message_id": int(row["telegram_message_id"]),
        "row_index": int(row["row_index"]),
        "artifact_id": "",
        "artifact_kind": "",
        "chunk_index": 0,
        "source_url": "",
        "final_url": "",
        "title": "",
        "file_name": "",
        "reply_to_message_id": thread_fields["reply_to_message_id"] or 0,
        "thread_id": str(thread_fields["thread_id"]),
        "thread_key": str(thread_fields["thread_key"]),
        "date": str(row.get("date") or ""),
        "message_url": str(row.get("message_url") or ""),
        "normalization_lang": str(row.get("normalization_lang") or "unknown"),
        "token_count": int(row.get("token_count") or 0),
        "text_hash": text_hash,
    }


def _artifact_documents_from_rows(
    rows: list[dict[str, Any]],
    *,
    raw_export_run_id: str,
    monitored_source_id: str,
) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for row in rows:
        if not row.get("has_text"):
            continue
        clean_text = str(row.get("clean_text") or "").strip()
        if not clean_text:
            continue
        lemmas = _json_list(row.get("lemmas_json"))
        embedding_text = " ".join([clean_text, " ".join(lemmas)]).strip()
        message_id = int(row["telegram_message_id"])
        artifact_id = str(row.get("artifact_id") or f"artifact:{message_id}")
        chunk_index = int(row.get("chunk_index") or 0)
        documents.append(
            {
                "id": f"telegram-artifact-{artifact_id}-{chunk_index}",
                "document": clean_text,
                "embedding_text": embedding_text,
                "metadata": _artifact_metadata(
                    row,
                    raw_export_run_id=raw_export_run_id,
                    monitored_source_id=monitored_source_id,
                    text_hash=_text_hash(clean_text),
                ),
            }
        )
    return documents


def _artifact_metadata(
    row: dict[str, Any],
    *,
    raw_export_run_id: str,
    monitored_source_id: str,
    text_hash: str,
) -> dict[str, str | int | float | bool]:
    message_id = int(row["telegram_message_id"])
    return {
        "entity_type": "telegram_artifact",
        "raw_export_run_id": raw_export_run_id,
        "monitored_source_id": monitored_source_id,
        "telegram_message_id": message_id,
        "row_index": 0,
        "artifact_id": str(row.get("artifact_id") or ""),
        "artifact_kind": str(row.get("artifact_kind") or ""),
        "chunk_index": int(row.get("chunk_index") or 0),
        "source_url": str(row.get("source_url") or ""),
        "final_url": str(row.get("final_url") or ""),
        "title": str(row.get("title") or ""),
        "file_name": str(row.get("file_name") or ""),
        "reply_to_message_id": 0,
        "thread_id": "",
        "thread_key": str(message_id),
        "date": str(row.get("date") or ""),
        "message_url": str(row.get("message_url") or ""),
        "normalization_lang": str(row.get("normalization_lang") or "unknown"),
        "token_count": int(row.get("token_count") or 0),
        "text_hash": text_hash,
    }


class LocalHashingEmbedder:
    profile = LOCAL_HASHING_PROFILE
    model_name = None

    def __init__(self, *, dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS) -> None:
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [_hashing_embed_text(text, dimensions=self.dimensions) for text in texts]


class RubertTiny2Embedder:
    profile = "rubert_tiny2_v1"
    model_name = RUBERT_TINY2_MODEL_NAME

    def __init__(self, *, max_length: int = 512) -> None:
        self.max_length = max_length
        self._tokenizer: Any | None = None
        self._model: Any | None = None
        self._torch: Any | None = None
        self._dimensions = RUBERT_TINY2_DEFAULT_DIMENSIONS

    @property
    def dimensions(self) -> int:
        self._load()
        return self._dimensions

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        self._load()
        assert self._tokenizer is not None
        assert self._model is not None
        assert self._torch is not None
        encoded = self._tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        )
        with self._torch.no_grad():
            output = self._model(**encoded)
            hidden = output.last_hidden_state
            mask = encoded["attention_mask"].unsqueeze(-1).expand(hidden.size()).float()
            pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
            pooled = self._torch.nn.functional.normalize(pooled, p=2, dim=1)
        return pooled.cpu().tolist()

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except Exception as exc:
            raise RuntimeError(
                "rubert_tiny2_v1 requires optional embedding dependencies. "
                "Install them with: uv sync --extra embeddings"
            ) from exc
        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self._model = AutoModel.from_pretrained(self.model_name)
        self._model.eval()
        self._dimensions = int(getattr(self._model.config, "hidden_size", self._dimensions))


def _build_embedder(
    embedding_profile: str,
    *,
    local_hashing_dimensions: int,
) -> TextEmbedder:
    normalized = embedding_profile.strip().lower().replace("-", "_")
    if normalized in {"local_hashing", "local_hashing_v1", "hashing"}:
        return LocalHashingEmbedder(dimensions=local_hashing_dimensions)
    if normalized in {"rubert_tiny2", "rubert_tiny2_v1", "cointegrated_rubert_tiny2"}:
        return RubertTiny2Embedder()
    raise ValueError(f"Unsupported embedding profile: {embedding_profile}")


def _hashing_embed_text(text: str, *, dimensions: int) -> list[float]:
    vector = [0.0] * dimensions
    for feature, weight in _features(text):
        digest = blake2b(feature.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big", signed=False)
        index = value % dimensions
        sign = 1.0 if value & 1 else -1.0
        vector[index] += sign * weight
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def _features(text: str) -> list[tuple[str, float]]:
    words = TOKEN_RE.findall(text.lower())
    features: list[tuple[str, float]] = []
    for word in words:
        features.append((f"w:{word}", 1.0))
        padded = f" {word} "
        for size, weight in ((3, 0.45), (4, 0.3)):
            if len(padded) < size:
                continue
            for index in range(0, len(padded) - size + 1):
                features.append((f"c{size}:{padded[index : index + size]}", weight))
    for first, second in zip(words, words[1:], strict=False):
        features.append((f"b:{first}:{second}", 0.75))
    return features


def _persistent_client(path: Path) -> Any:
    import chromadb
    from chromadb.config import Settings

    path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(path),
        settings=Settings(anonymized_telemetry=False),
    )


def _delete_collection_if_exists(client: Any, collection_name: str) -> None:
    try:
        client.delete_collection(collection_name)
    except Exception:
        return


def _texts_path_from_metadata(run: dict[str, Any]) -> Path:
    metadata = dict(run["metadata_json"] or {})
    text_normalization = metadata.get("text_normalization")
    if not isinstance(text_normalization, dict):
        raise ValueError("Chroma indexing requires Stage 2 text_normalization metadata")
    path_value = text_normalization.get("texts_parquet_path")
    if not path_value:
        raise ValueError("Chroma indexing requires text_normalization.texts_parquet_path")
    return _resolve_path(path_value)


def _artifact_texts_path_from_metadata(run: dict[str, Any]) -> Path | None:
    metadata = dict(run["metadata_json"] or {})
    artifact_texts = metadata.get("artifact_texts")
    if not isinstance(artifact_texts, dict):
        return None
    path_value = artifact_texts.get("texts_parquet_path")
    return _resolve_path(path_value) if path_value else None


def _thread_fields(row: dict[str, Any]) -> dict[str, Any]:
    raw = _json_dict(row.get("raw_message_json"))
    message_id = int(row["telegram_message_id"])
    reply_to = raw.get("reply_to_message_id")
    thread_id = str(raw.get("thread_id") or "")
    thread_key = thread_id or (str(reply_to) if reply_to is not None else str(message_id))
    return {
        "reply_to_message_id": int(reply_to) if reply_to is not None else 0,
        "thread_id": thread_id,
        "thread_key": thread_key,
    }


def _json_dict(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: Any) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _upsert_documents(collection: Any, documents: list[dict[str, Any]], *, embedder: TextEmbedder) -> None:
    if not documents:
        return
    embeddings = embedder.embed_texts([item["embedding_text"] for item in documents])
    collection.upsert(
        ids=[item["id"] for item in documents],
        documents=[item["document"] for item in documents],
        metadatas=[item["metadata"] for item in documents],
        embeddings=embeddings,
    )


def _extend_sample_documents(
    sample_documents: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    *,
    limit: int = 20,
) -> None:
    if len(sample_documents) >= limit:
        return
    sample_documents.extend(documents[: max(0, limit - len(sample_documents))])


def _text_hash(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 3] + "..."


def _resolve_path(value: Path | str | Any) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else Path(".") / path
