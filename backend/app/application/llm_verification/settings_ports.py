from __future__ import annotations

from typing import Protocol

from app.domain.llm_settings import LlmSettings


class LlmSettingsRepository(Protocol):
    async def get_settings(self) -> LlmSettings: ...

    async def save_settings(self, settings: LlmSettings) -> LlmSettings: ...
