# PUR Leads v2

Fresh implementation branch for the next version of PUR Leads.

The previous codebase is historical reference only. Active development happens
in this repository layout:

- `backend/` - FastAPI service, SQLAlchemy/Alembic, PostgreSQL only.
- `frontend/` - React + Vite + TypeScript operator UI.
- `docker-compose.yml` - local container stack for PostgreSQL, Redis, backend,
  enrichment dispatcher, worker, Telegram userbot listener, notification
  dispatcher, and frontend.
- `docs/` - architecture and durable decisions.
- `state/` - current work and backlog.
- `artifacts/` - ignored local exports and evidence, including production lead examples.

## Local Development

```bash
docker compose up --build
```

Services:

- backend: `http://localhost:8000`
- frontend: `http://localhost:5173`
- postgres: `127.0.0.1:55433`
- redis: `127.0.0.1:6379`
- caddy dev access: `https://secclaw.qlbc.ru:19443`
- enrichment-dispatcher: PostgreSQL task outbox flusher, no public port
- worker: Celery enrichment worker
- userbot: Telegram source listener, no public port
- notification-dispatcher: Telegram notification outbox flusher, no public port

The dev operator UI is protected by a simple session cookie login. Defaults are:

- login: `admin`
- password: `pur-dev-password`

Override with `PUR_AUTH_USERNAME`, `PUR_AUTH_PASSWORD`, and
`PUR_AUTH_SESSION_SECRET` in the dev environment.

## Внешний Dev-Доступ

Caddy на хосте прокидывает dev-интерфейс наружу через:

`https://secclaw.qlbc.ru:19443/`

Маршрутизация:

- `/` -> Vite dev server на `127.0.0.1:5173`
- `/api/*` -> FastAPI на `127.0.0.1:8000`
- SSE endpoint `/api/v1/enrichments/{job_id}/events` проходит через тот же
  Caddy route; в reverse proxy включен streaming-friendly `flush_interval -1`.

Caddy-конфигурация находится вне репозитория:

- `/etc/caddy/sites/53-pur-leads-v2-dev.conf`
- импорт подключен из `/etc/caddy/Caddyfile`
- файл site-конфига должен быть читаем service user Caddy, например
  `root:caddy 640`
- хостовый firewall должен пропускать внешний порт:
  `sudo ufw allow 19443/tcp comment 'PUR Leads v2 dev UI'`

The first workflow uses the backend API to create text enrichment jobs, a
PostgreSQL enrichment task outbox, an enrichment dispatcher that publishes
Celery tasks, a Celery worker to run the NLP pipeline, Redis as the broker,
PostgreSQL for persisted job state, and SSE for progress updates.

The operator UI also includes a Settings Center. It shows editable NLP/domain
settings from PostgreSQL config revisions and read-only runtime settings from
the backend environment. Draft NLP settings can be previewed on text before
saving. Rule editing separates exact phrases from lemmatized phrases; new
lemmatized phrases are built from operator-entered text by the backend and show
both the original input and generated lemmas. Exact phrases use literal
lowercased matching for technical spellings such as `Wi-Fi`, `220v`, and
abbreviations; lemmatized phrases use normalized Yargy tokens. A Help tab in the
UI explains the matching modes. `backend/config/nlp` is only the bootstrap
default when the database has no active NLP config revision yet.

The enrichment result now includes `lead_assessment`: an explainable PUR lead
verdict with score, temperature, solution areas, customer segments, review lane,
positive reasons, and noise signals. The Overview tab shows dictionary entities,
facts, domain signals, the exact score arithmetic, and category/lane matches in
operator-facing labels. Evidence rows and calculation rows link to separate
settings detail pages through hash deeplinks like
`#/settings/aliases/devices/electric_curtain`, while keeping the current input
text in the SPA context. Scoring thresholds, weights, review lanes, and taxonomy
mappings are edited through the same PostgreSQL-backed Settings Center.

The default Analytics screen is now the live Telegram review surface. It reads
from `telegram_source_messages` joined to enrichment jobs/results, not from old
batch imports. Old batch analytics rows are cleared by migration
`0008_runtime_analytics_cleanup`; batch tooling remains available for offline
calibration, but does not feed the operator's default live analytics screen.
Each row keeps quick Telegram/app/test links and has a dedicated `Ревью` action
opening `#/analytics/review/{source_message_id}`. Review verdicts and comments
are stored in `message_reviews`, separate from deterministic enrichment output,
so operator ground truth can later drive calibration and rule edits. The
candidate list shows saved review chips, supports filters for reviewed/
unreviewed messages and verdicts, and review links preserve the current run,
filters, and page offset when returning from the dedicated Review page. The
default queue is unreviewed messages. Review saves support structured reason
tags, hotkeys `1/2/3/4`, `Ctrl+Enter`, and "Сохранить и следующий".
Expanded Analytics rows reuse the same explainability links as Testing:
facts, signals, score reasons, taxonomy categories, alias dependencies, weights,
and review lanes link to Settings detail targets. Left click opens the quick
settings preview modal; Ctrl/Cmd or middle click follows the full hash deeplink.

The Settings Center also exposes Telegram runtime settings:

- Notification routing: Telegram bots, Telegram chats, and routes are separate
  settings. Bots own tokens, chats own destination `chat_id` values, and routes
  decide where to notify based on the enrichment result (`is_lead`, score,
  temperature, review lane, solution areas, customer segments, signals, facts,
  reasons, and noise). API responses return only token presence and a masked
  token, never the full bot token. Default lead notifications are formatted as
  readable blocks with score, review lane, solution areas, customer segments,
  score reasons, source text preview, and Telegram/app links.
- Telegram input: userbot accounts own phone/app credentials/session state, and
  source chats own input refs such as `@channel` plus the high-water mark
  `last_message_id`. API responses mask `api_hash` and never return the
  Telethon session string. A saved source chat can temporarily show `draft`:
  that means the row is stored, but the userbot has not yet resolved the
  `input_ref` into a concrete Telegram chat id and cursor. Saving editable
  Telegram input settings preserves runtime cursor/error/cooldown state unless
  the source identity changes. Telegram `FloodWait` is stored on the userbot
  account as `cooldown_until`; while it is active, the service does not
  reconnect or issue read/resolve calls for that account. Immediately after
  cooldown expires, recovery is throttled: dev Compose reads at most 10 messages
  per source batch, drains larger backlogs in repeated delayed batches, and
  waits 15 seconds between source recovery reads before switching to live
  updates.

Production runtime flow:

1. `userbot` listens to configured Telegram source chats through Telethon live
   updates. On startup it does one bounded recovery read after the stored
   `last_message_id`.
2. For a new text message, the userbot creates a queued enrichment job with a
   blocked task outbox row, then persists the source row in
   `telegram_source_messages`. The source-message insert activates the matching
   `enrichment_task_outbox` row to `pending` in the same transaction. If another
   process already saved the source message, the losing unpublished job/outbox
   row is discarded.
3. `enrichment-dispatcher` atomically claims pending `enrichment_task_outbox`
   rows and publishes the Celery/Redis task. Testing/API jobs create pending
   outbox rows directly. If publish fails, the row is released back to
   `pending` with the error for retry.
4. `worker` atomically claims only queued enrichment jobs, enriches the text,
   and stores the result in PostgreSQL. Celery redelivery or duplicate task
   publication is a no-op once a job is running/completed/failed.
5. Notification routing writes matching messages to `notification_outbox`.
6. `notification-dispatcher` atomically claims pending outbox rows, groups by
   bot+chat, packs batches under Telegram `sendMessage` 4096-character limit,
   and sends a partial batch after the oldest item waits 5 minutes.

Telegram notifications are emitted only for enrichment jobs that belong to a
stored Telegram source message. Manual Testing enrichments can reuse the same
text for debugging, but they do not enqueue lead notifications. Telegram
notifications include a link to the source Telegram message when a stable
permalink can be derived, and a link back to the app analytics view for the
stored source message. The Analytics table also has a quick "Проверить" action
that opens `#/testing?message_id={source_message_id}`, loads the source text in
the Testing screen, and starts enrichment.
Outbox rows for Telegram-originated jobs carry `source_message_id` and
`enrichment_job_id`; `(source_message_id, route_id)` is unique, so worker
redelivery cannot enqueue the same route notification twice for the same source
message.

The Review page is the detailed operator workspace for one message. It shows the
source text, score/temperature/lane, reasons, facts, domain signals, and
highlighted fragments, then lets the operator save one of `Лид`, `Не лид`,
`Сомнительно`, or `Шум` with structured tags and a comment. The page also
contains the first constructor panel: select a fragment in the source text to
prepare a future dictionary/fact/signal/noise edit.

The UI includes Logs and System Status tabs. These are based on durable backend
state: enrichment events, enrichment task outbox rows, source messages, source
chat errors, notification outbox state, database/Redis checks, source-chat
statuses, job counters, task-dispatch counters, and notification outbox
counters. Logs are filtered and paginated on the backend by service, level,
text, and time range. Runtime log API limits are configurable with
`PUR_RUNTIME_LOG_DEFAULT_LIMIT` and `PUR_RUNTIME_LOG_MAX_LIMIT`. To avoid
unbounded growth, log-like retention keeps the newest
`PUR_RUNTIME_ENRICHMENT_EVENT_RETENTION_ROWS` enrichment events and newest
`PUR_RUNTIME_NOTIFICATION_OUTBOX_RETENTION_ROWS` non-pending notification
outbox rows; pending/sending notifications and Telegram source messages are not
trimmed by this log retention policy. `enrichment_task_outbox` is operational
state for reliable task publication and is not trimmed by runtime log
retention. `enrichment_events` are worker progress journal rows, not analytics
candidates; live Analytics shows only Telegram source messages that already
have an enrichment result. Docker Compose also rotates container stdout logs
with `max-size=10m` and `max-file=5` per service.

The UI also includes a Project Documentation tab. It reads repository markdown
documents through the backend from `README.md`, `AGENTS.md`, `docs/`, `notes/`,
and `state/`, and shows them grouped by file without exposing arbitrary host
paths. In Docker dev mode the backend gets the project root as a read-only
`/workspace` mount via `PUR_PROJECT_DOCS_ROOT`.

Batch enrichment remains offline/testing/calibration tooling. It does not send
notifications and is not connected to Telegram input.

## Batch Enrichment

Local exports can be enriched without creating one API/Celery job per message:

```bash
cd backend
uv run python -m app.cli.batch_enrich \
  --input ../artifacts/designer-channel/messages.jsonl \
  --output ../artifacts/designer-channel/full-enrichment.jsonl \
  --summary ../artifacts/designer-channel/full-enrichment.summary.json \
  --progress-interval 1000
```

The batch output is JSONL with `message_id`, `text`, and full
`TextEnrichmentResult` under `result`. `artifacts/` is ignored by git.

## Batch Analytics

Lead candidates from a completed batch run can be imported into PostgreSQL for
the web analytics tab. The import reads the compact `lead-candidates.jsonl`
file and the batch summary, not the full enrichment dump:

```bash
cd backend
PUR_DATABASE_URL='postgresql+psycopg://pur_leads:pur_leads_dev_password@127.0.0.1:55433/pur_leads_v2' \
uv run python -m app.cli.import_analytics \
  --summary ../artifacts/designer-channel/runs/2026-05-07-full-8workers/full-enrichment.summary.json \
  --lead-candidates ../artifacts/designer-channel/runs/2026-05-07-full-8workers/lead-candidates.jsonl \
  --name designer-channel-2026-05-07-full-8workers
```

The UI tab `Аналитика` shows imported runs, high-level KPIs, score buckets, top
signals/reasons/segments, review lanes, and a candidate table filtered by score,
temperature, signal, reason, solution area, customer segment, review lane,
source channel, received date, review state, verdict, and text. Review lanes are
configured in `lead_scoring.review_lanes` and stored in PostgreSQL NLP config
revisions; YAML is only the bootstrap default.

Checks:

```bash
cd backend && uv run pytest -q
cd backend && uv run pytest --runslow tests/test_enrichment_pipeline.py::test_enriches_text_with_configured_domain_signal -q
cd frontend && npm test && npm run build
docker compose config
```
