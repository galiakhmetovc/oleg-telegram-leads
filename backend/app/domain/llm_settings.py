from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


LlmRouteMatchMode = Literal["all", "any"]


DEFAULT_LLM_SYSTEM_PROMPT = (
    "Ты проверяешь одно русское Telegram-сообщение на наличие лида. "
    "Главный источник истины только message.text. "
    "rule_engine_result - машинная подсказка: verdict, score, temperature и найденные русские labels. "
    "score не является confidence; confidence всегда число от 0.0 до 1.0. "
    "available_taxonomy - справочное меню возможных labels, не доказательство. "
    "Не перечисляй taxonomy просто потому, что labels есть в меню. "
    "Исходящий рекламный пост поставщика, кейс, портфолио, сайт, канал или текст в стиле "
    "'мы сделали/показываем/представили' без входящего запроса клиента - это not_lead. "
    "Если бригада/исполнитель рекламирует свои услуги и ищет объекты, это тоже not_lead. "
    "Исключение: явно ищут подрядчика, интегратора, исполнителя, контакты или есть запрос клиента. "
    "Если agrees_with_rule_engine=true, верни missing_fact_types=[], suspicious_fact_types=[], missing_signal_types=[]. "
    "missing_fact_types: русские labels фактов из available_taxonomy.fact_rule_labels, которые должны быть, но не найдены. "
    "suspicious_fact_types: русские labels из rule_engine_result.fact_labels, которые выглядят ошибочными. "
    "missing_signal_types: русские labels сигналов из available_taxonomy.signal_labels, которые должны быть, но не найдены. "
    "evidence и anti_evidence - короткие точные цитаты только из message.text. "
    "matched_golden_ids всегда возвращай пустым массивом. "
    "Ответ: только валидный JSON по схеме, без markdown."
)


@dataclass(frozen=True)
class LlmRouteConditions:
    source_chat_ids: list[str] = field(default_factory=list)
    score_min: int | None = None
    score_max: int | None = None
    temperatures: list[str] = field(default_factory=list)
    review_lanes: list[str] = field(default_factory=list)
    include_signal_types: list[str] = field(default_factory=list)
    exclude_signal_types: list[str] = field(default_factory=list)
    include_fact_types: list[str] = field(default_factory=list)
    exclude_fact_types: list[str] = field(default_factory=list)
    include_reason_keys: list[str] = field(default_factory=list)
    exclude_reason_keys: list[str] = field(default_factory=list)
    include_solution_area_types: list[str] = field(default_factory=list)
    exclude_solution_area_types: list[str] = field(default_factory=list)
    include_customer_segment_types: list[str] = field(default_factory=list)
    exclude_customer_segment_types: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class LlmRoute:
    id: str
    name: str
    enabled: bool
    priority: int
    match_mode: LlmRouteMatchMode
    conditions: LlmRouteConditions


@dataclass(frozen=True)
class LlmSettings:
    enabled: bool
    model: str
    endpoint: str
    timeout_seconds: float
    system_prompt: str
    routes: list[LlmRoute]
    updated_at: datetime | None


def default_llm_settings(*, model: str, endpoint: str, timeout_seconds: float) -> LlmSettings:
    return LlmSettings(
        enabled=True,
        model=model,
        endpoint=endpoint,
        timeout_seconds=timeout_seconds,
        system_prompt=DEFAULT_LLM_SYSTEM_PROMPT,
        routes=[],
        updated_at=None,
    )
