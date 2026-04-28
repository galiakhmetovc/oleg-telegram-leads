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


ChatMessageInput = AiChatMessage | Mapping[str, str]


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
