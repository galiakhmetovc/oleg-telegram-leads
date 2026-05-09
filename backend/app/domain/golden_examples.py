from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

GoldenVerdict = Literal["lead", "not_lead", "uncertain", "noise"]


@dataclass(frozen=True)
class GoldenExample:
    id: UUID
    title: str
    text: str
    expected_verdict: GoldenVerdict | None
    comment: str
    source_message_id: UUID | None
    source_chat_title: str | None
    telegram_message_id: int | None
    telegram_message_url: str | None
    last_enrichment_job_id: UUID | None
    created_at: datetime
    updated_at: datetime
