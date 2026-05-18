from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enrichment import TextEnrichmentResult

LLM_VERIFICATION_SCHEMA_VERSION = "llm_verification.v1"

LlmVerdict = Literal["lead", "not_lead", "uncertain"]
LlmRecommendation = Literal["keep", "promote", "demote", "manual_review"]
LlmVerificationStatus = Literal["queued", "running", "completed", "failed"]


class LlmVerificationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: LlmVerdict
    confidence: float = Field(ge=0, le=1)
    recommendation: LlmRecommendation
    agrees_with_rule_engine: bool
    matched_golden_ids: list[str]
    missing_fact_types: list[str]
    suspicious_fact_types: list[str]
    missing_signal_types: list[str]
    evidence: list[str]
    anti_evidence: list[str]


LLM_VERIFICATION_RESPONSE_SCHEMA = LlmVerificationResponse.model_json_schema()


@dataclass(frozen=True)
class SourceMessageForLlmVerification:
    source_message_id: UUID
    source_chat_id: UUID
    source_chat_title: str | None
    telegram_message_id: int | None
    text: str
    enrichment_job_id: UUID
    enrichment_result: TextEnrichmentResult


@dataclass(frozen=True)
class LlmVerificationRun:
    id: UUID
    source_message_id: UUID
    enrichment_job_id: UUID
    model: str
    schema_version: str
    status: LlmVerificationStatus
    context_pack: dict[str, object]
    response: dict[str, object] | None
    raw_response: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime
    route_id: str | None = None
    prompt: str | None = None
    attempts: int = 0
    claimed_at: datetime | None = None
