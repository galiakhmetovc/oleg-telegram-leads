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

        reader = self.reader_factory(local_path)
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
