# Operator Workspace Navigation Design

## Goal

Move daily operator work out of the top-level Analytics/Testing/Constructor split into one top-level `Рабочее место` area, while keeping reporting under `Аналитика`.

## Design

Top-level navigation:

- `Рабочее место`: default operator entry point.
- `Аналитика`: report/eval pages only.
- Existing secondary sections stay top-level: `LLM`, `Golden`, `Настройки`, `Как работать`, `Справка`, docs/logs/status.

`Рабочее место` contains compact internal tabs:

- `Очередь`: current live candidate queue.
- `Ревью`: current message review page, selected only when a message is open.
- `Проверка`: current manual text testing workspace.
- `Конструктор`: current draft rule constructor.

`Аналитика` contains:

- `Обзор`
- `Качество ревью`
- `LLM-проверка`

## Compatibility

Existing routes keep working:

- `/analytics` opens `Рабочее место -> Очередь`.
- `/analytics/review/:id` opens `Рабочее место -> Ревью`.
- `/testing` opens `Рабочее место -> Проверка`.
- `/constructor` opens `Рабочее место -> Конструктор`.
- `/analytics/overview` and `/analytics/quality` open top-level `Аналитика`.

This is intentionally a navigation/layout change only. It does not change review persistence, candidate filters, testing jobs, constructor draft behavior, or backend APIs.
