from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.llm_verification import LlmVerificationRun, SourceMessageForLlmVerification
from app.domain.settings import NlpConfigRevision


class LlmVerificationRepository(Protocol):
    async def get_source_message(self, source_message_id: UUID) -> SourceMessageForLlmVerification | None:
        raise NotImplementedError

    async def save_run(self, run: LlmVerificationRun) -> LlmVerificationRun:
        raise NotImplementedError

    async def get_run(self, run_id: UUID) -> LlmVerificationRun | None:
        raise NotImplementedError

    async def claim_run(self, run_id: UUID) -> LlmVerificationRun | None:
        raise NotImplementedError

    async def complete_run(
        self,
        run_id: UUID,
        *,
        response: dict[str, object],
        raw_response: str,
        completed_at: datetime,
    ) -> LlmVerificationRun | None:
        raise NotImplementedError

    async def fail_run(
        self,
        run_id: UUID,
        *,
        error: str,
        raw_response: str | None,
        failed_at: datetime,
    ) -> LlmVerificationRun | None:
        raise NotImplementedError

    async def list_runs(self, source_message_id: UUID) -> list[LlmVerificationRun]:
        raise NotImplementedError

    async def list_all_runs(self, *, limit: int, offset: int) -> tuple[int, list[LlmVerificationRun]]:
        raise NotImplementedError

    async def route_run_exists(self, *, source_message_id: UUID, route_id: str) -> bool:
        raise NotImplementedError


class LlmTaskPublisher(Protocol):
    async def publish(self, run_id: UUID) -> None: ...


class ActiveNlpConfigReader(Protocol):
    async def get_active(self) -> NlpConfigRevision | None:
        raise NotImplementedError


class LlmVerificationClient(Protocol):
    async def verify(
        self,
        *,
        model: str,
        context_pack: dict[str, object],
        system_prompt: str,
    ) -> tuple[dict[str, object], str]:
        raise NotImplementedError
