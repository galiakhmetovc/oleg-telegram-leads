# Message Queue Grid Design

## Goal

Rework `Рабочее место -> Очередь` into an operator-grade message queue. The queue should show recent live Telegram messages by default, support rich message-level filtering, expose all useful message metadata as optional columns, and keep operator layout choices local to the browser.

## Data Scope

The queue is message-first. Each row should carry as much message-related data as the backend can provide without per-row extra requests:

- source type (`telegram` now, `max` later);
- source message id, Telegram chat/message ids, channel title, message text, received time, Telegram/app/testing URLs;
- enrichment id, deterministic score, temperature, review lane, lead status, solution areas, customer segments, intent/noise signals, reasons, domain signals, facts;
- operator review verdict, tags, comment, created/updated timestamps;
- latest LLM verification summary: processed flag, status, verdict, confidence, recommendation, agreement with rule engine, model, route, attempts, error, created/updated timestamps.

## Default View

The queue defaults to the last 24 hours, not all time. A quick period strip provides common ranges: 1h, 3h, 5h, 12h, 24h, 2d, 3d, 7d, 30d, and all time. The active period is represented as a removable chip.

The old `Запуск` selector is hidden from the operator queue. The live source remains `Telegram live` internally, but the operator sees rows and filters, not analytics run implementation details.

## Filters

The queue shows active filters as chips and a single `Добавить фильтр` button. The button opens a modal where the operator chooses field, operator, and value. Applying a filter stores it in `localStorage` and updates URL/API query parameters.

Supported filters include score, temperature, review lane, review status, review verdict, channel, text, received range, source type, signal, reason, solution area, customer segment, and LLM fields: processed, status, verdict, recommendation, confidence, model, route, agreement with rule engine, and error presence.

## Columns

The queue exposes a large column catalog. Operators can show/hide columns, reorder them, and resize widths. Column state is saved in `localStorage`. The first implementation uses the existing MUI table with local column metadata; it should not introduce a new grid dependency in this pass.

Default columns stay compact: source type, received time, channel, text, score, temperature, review lane, review status, LLM verdict/status, and actions. The column picker can enable all metadata columns listed in Data Scope.

## Actions

Rows expose one `Действия` button. It opens a compact modal with actions:

- open original Telegram message;
- open focused analytics view;
- open review;
- run/open LLM verification;
- re-run deterministic checking;
- add to golden examples;
- show/hide detailed analysis.

The separate expand arrow and multiple inline action buttons disappear from the row.

## Persistence

All operator preferences for active filters, quick period, column visibility/order/widths, and the last expanded message live in `localStorage`. Backend persistence is intentionally skipped until the web UI gains users/roles.
