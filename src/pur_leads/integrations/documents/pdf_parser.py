"""PDF artifact parsing adapter."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pypdf
from pypdf import PdfReader

from pur_leads.workers.runtime import ParsedArtifact


class PdfArtifactParser:
    def __init__(
        self,
        *,
        reader_factory: Callable[[str | Path], Any] = PdfReader,
        parser_version: str | None = None,
    ) -> None:
        self.reader_factory = reader_factory
        self.parser_version = parser_version or str(getattr(pypdf, "__version__", "unknown"))

    async def parse_artifact(
        self,
        *,
        source_id: str,
        artifact_id: str | None,
        payload: dict[str, Any],
    ) -> ParsedArtifact:
        local_path = payload.get("local_path")
        if not isinstance(local_path, str) or not local_path:
            raise ValueError("pdf parser requires payload.local_path")

        path = Path(local_path)
        file_name = payload.get("file_name")
        mime_type = payload.get("mime_type")
        if _is_text_document(path, file_name=file_name, mime_type=mime_type):
            chunks = _chunk_text(_read_text_document(path))
            return ParsedArtifact(
                source_id=source_id,
                artifact_id=artifact_id,
                chunks=chunks,
                parser_name="plain-text",
                parser_version="1",
            )

        reader = self.reader_factory(path)
        chunks = [
            normalized
            for page in getattr(reader, "pages", [])
            if (normalized := _normalize_page_text(page.extract_text()))
        ]
        return ParsedArtifact(
            source_id=source_id,
            artifact_id=artifact_id,
            chunks=chunks,
            parser_name="pypdf",
            parser_version=self.parser_version,
        )


def _normalize_page_text(value: str | None) -> str | None:
    if value is None:
        return None
    lines = [line.strip() for line in value.splitlines()]
    normalized = "\n".join(line for line in lines if line)
    return normalized or None


def _is_text_document(
    path: Path,
    *,
    file_name: Any,
    mime_type: Any,
) -> bool:
    if isinstance(mime_type, str):
        normalized_mime = mime_type.casefold().split(";", 1)[0].strip()
        if normalized_mime.startswith("text/"):
            return True
        if normalized_mime in {
            "application/json",
            "application/xml",
            "application/csv",
            "text/csv",
        }:
            return True
    candidate = str(file_name or path.name).casefold()
    return candidate.endswith((".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm"))


def _read_text_document(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _chunk_text(value: str, *, max_chars: int = 8000) -> list[str]:
    normalized = "\n".join(line.rstrip() for line in value.replace("\r\n", "\n").split("\n"))
    normalized = normalized.strip()
    if not normalized:
        return []
    paragraphs = [part.strip() for part in normalized.split("\n\n") if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs or [normalized]:
        separator = "\n\n" if current else ""
        if current and len(current) + len(separator) + len(paragraph) > max_chars:
            chunks.append(current)
            current = paragraph
            continue
        current = f"{current}{separator}{paragraph}" if current else paragraph
    if current:
        chunks.append(current)
    return chunks
