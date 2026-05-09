from __future__ import annotations

from typing import Any, Protocol

from app.domain.settings import NlpConfigRevision


class NlpConfigRepository(Protocol):
    async def get_active(self) -> NlpConfigRevision | None:
        ...

    async def get_active_or_seed(
        self,
        default_documents: dict[str, dict[str, Any]],
    ) -> NlpConfigRevision:
        ...

    async def replace_active(
        self,
        documents: dict[str, dict[str, Any]],
        *,
        source: str,
    ) -> NlpConfigRevision:
        ...
