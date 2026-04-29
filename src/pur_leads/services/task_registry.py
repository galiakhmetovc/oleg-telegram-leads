"""Static registry of scheduler task definitions exposed to the admin UI."""

from __future__ import annotations

from typing import Any


TASK_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "task_type": "poll_monitored_source",
        "display_name": "Чтение Telegram-источника",
        "workload_class": "live/bulk",
        "required_capabilities": ["worker", "telegram.read_history"],
        "parallelism_rule": "Последовательно на один юзербот, если явно не увеличено.",
        "default_priority": 20,
        "config_keys": ["telegram_read_jobs_per_userbot", "telegram_get_history_wait_seconds"],
        "status": "active",
    },
    {
        "task_type": "download_artifact",
        "display_name": "Скачивание документа",
        "workload_class": "bulk",
        "required_capabilities": ["worker", "telegram.download_document"],
        "parallelism_rule": "Ограничивается Telegram-юзерботом и политикой архивации.",
        "default_priority": 40,
        "config_keys": ["telegram_read_jobs_per_userbot"],
        "status": "active",
    },
    {
        "task_type": "fetch_external_page",
        "display_name": "Загрузка внешней страницы",
        "workload_class": "bulk",
        "required_capabilities": ["worker", "external_fetch"],
        "parallelism_rule": "Ограничивается HTTP-пулом и списком разрешенных доменов.",
        "default_priority": 45,
        "config_keys": [
            "external_page_fetch_concurrency",
            "external_page_allowed_domains",
            "external_page_fetch_timeout_seconds",
        ],
        "status": "active",
    },
    {
        "task_type": "parse_artifact",
        "display_name": "Разбор документа локальным парсером",
        "workload_class": "bulk",
        "required_capabilities": ["worker", "local_parser"],
        "parallelism_rule": "Ограничивается локальным CPU/IO-пулом.",
        "default_priority": 50,
        "config_keys": ["local_parser_concurrency"],
        "status": "active",
    },
    {
        "task_type": "ocr_artifact",
        "display_name": "OCR документа",
        "workload_class": "bulk",
        "required_capabilities": ["worker", "ocr.document"],
        "parallelism_rule": "Ограничивается выбранным OCR-исполнителем и лимитом модели.",
        "default_priority": 55,
        "config_keys": ["ai_model_concurrency_utilization_ratio"],
        "status": "planned",
    },
    {
        "task_type": "extract_catalog_facts",
        "display_name": "Извлечение фактов каталога",
        "workload_class": "bulk/normal",
        "required_capabilities": ["worker", "llm.text.fast", "llm.text.strong"],
        "parallelism_rule": "Выбирает исполнителя catalog_extractor по роли, приоритету и свободным слотам.",
        "default_priority": 60,
        "config_keys": ["catalog_llm_extraction_enabled", "catalog_llm_max_tokens"],
        "status": "active",
    },
    {
        "task_type": "classify_message_batch",
        "display_name": "Классификация сообщений",
        "workload_class": "realtime",
        "required_capabilities": ["worker", "llm.text.fast"],
        "parallelism_rule": "Фаззи-путь локальный; LLM shadow использует резерв realtime-слотов.",
        "default_priority": 10,
        "config_keys": [
            "lead_llm_shadow_enabled",
            "lead_llm_shadow_max_messages_per_job",
            "worker_realtime_reserved_slots",
        ],
        "status": "active",
    },
    {
        "task_type": "catalog_candidate_validation",
        "display_name": "Фоновая проверка кандидатов каталога",
        "workload_class": "idle",
        "required_capabilities": ["worker", "llm.text.strong"],
        "parallelism_rule": (
            "Запускается только когда нет due/running realtime, normal или bulk задач; "
            "использует исполнителя catalog_candidate_validator."
        ),
        "default_priority": 90,
        "config_keys": [
            "catalog_quality_idle_validation_enabled",
            "catalog_quality_idle_batch_size",
            "catalog_quality_validator_model",
            "catalog_quality_validator_profile",
        ],
        "status": "active",
    },
    {
        "task_type": "send_notifications",
        "display_name": "Отправка уведомлений",
        "workload_class": "realtime",
        "required_capabilities": ["worker", "telegram.notify"],
        "parallelism_rule": "Ограничивается ботом, группой уведомлений и минимальным интервалом.",
        "default_priority": 5,
        "config_keys": [
            "telegram_bot_send_concurrency_per_bot",
            "telegram_notification_min_interval_seconds",
        ],
        "status": "active",
    },
    {
        "task_type": "generate_contact_reasons",
        "display_name": "Поводы связаться с клиентом",
        "workload_class": "normal",
        "required_capabilities": ["worker", "llm.text.fast"],
        "parallelism_rule": "Может работать локально или через будущий CRM-исполнитель.",
        "default_priority": 70,
        "config_keys": [],
        "status": "planned",
    },
)


def list_task_definitions() -> list[dict[str, Any]]:
    return [dict(item) for item in TASK_DEFINITIONS]
