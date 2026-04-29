"""Small chat-completion port used by AI-backed integrations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class AiChatMessage:
    role: str
    content: str


@dataclass(frozen=True)
class AiChatCompletion:
    content: str
    model: str
    request_id: str | None
    usage: dict[str, Any]
    raw_response: dict[str, Any]


@dataclass(frozen=True)
class AiModelLease:
    id: str
    provider: str
    model: str
    provider_account_id: str | None = None


class AiModelConcurrencyLimitExceeded(RuntimeError):
    def __init__(self, *, provider: str, model: str, retry_after_seconds: int = 5) -> None:
        super().__init__(f"AI model concurrency limit reached for {provider}:{model}; retry later")
        self.provider = provider
        self.model = model
        self.retry_after_seconds = retry_after_seconds
        self.resource_unavailable = True
        self.resource_kind = "ai_model_concurrency"


ChatMessageInput = AiChatMessage | Mapping[str, str]


class AiModelConcurrencyLimiter(Protocol):
    def acquire_model_slot(
        self,
        *,
        provider: str,
        model: str,
        worker_name: str,
        provider_account_id: str | None = None,
    ) -> AiModelLease | None:
        """Acquire one model execution slot or return None when the model is saturated."""

    def release_model_slot(self, lease: AiModelLease) -> None:
        """Release a previously acquired model execution slot."""


class AiChatClient(Protocol):
    async def complete(
        self,
        *,
        messages: Sequence[ChatMessageInput],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> AiChatCompletion:
        """Return one non-streaming chat completion."""


def message_payload(message: ChatMessageInput) -> dict[str, str]:
    if isinstance(message, AiChatMessage):
        return {"role": message.role, "content": message.content}
    return {"role": str(message["role"]), "content": str(message["content"])}
