from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class NlpConfigRevision:
    id: UUID
    revision: int
    documents: dict[str, dict[str, Any]]
    source: str
    created_at: datetime | None
