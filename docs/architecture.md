# Architecture

PUR Leads v2 starts as a clean containerized web application.

## Dev Mode

Everything currently runs in development mode.

- Docker images provide runtime tools and dependency layers only.
- Application source is mounted from the host through bind volumes.
- Backend Python dependencies are installed into the image from `backend/pyproject.toml`
  and `backend/uv.lock`; backend source is not copied into the image.
- Frontend dependencies are installed into the image from `frontend/package-lock.json`;
  frontend source is not copied into the image.
- Frontend `node_modules` is exposed through the `frontend-node-modules` Docker volume.
- There is no production image, nginx packaging, or baked application source yet.

## Components

- PostgreSQL is the only operational database.
- FastAPI owns the backend HTTP API and database access.
- Celery workers execute background NLP enrichment jobs.
- Redis is the local Celery broker.
- Telegram userbot listener receives configured source chat messages.
- Notification dispatcher sends Telegram bot notifications from a durable
  outbox.
- React + Vite + TypeScript owns the operator UI.
- Docker Compose owns the local dev stack and service wiring.
- Host Caddy exposes the dev UI over HTTPS for operator review.
- Analytics defaults to live Telegram source messages and enrichment results.
  Batch analytics imports remain offline calibration tooling.

## Caddy Dev Access

External dev access is provided by the host-level Caddy service, not by the
Docker Compose stack.

- Public URL: `https://secclaw.qlbc.ru:19443/`
- Site file: `/etc/caddy/sites/53-pur-leads-v2-dev.conf`
- Main Caddy import: `/etc/caddy/Caddyfile`
- Frontend route: `/` -> `127.0.0.1:5173`
- Backend route: `/api/*` -> `127.0.0.1:8000`
- SSE route: `/api/v1/enrichments/{job_id}/events` is covered by `/api/*`
  and requires proxy streaming to stay enabled.
- Site file permissions: the Caddy service user must be able to read the site
  file, for example `root:caddy 640`.
- Firewall: `19443/tcp` must be allowed on the host, for example
  `sudo ufw allow 19443/tcp comment 'PUR Leads v2 dev UI'`.

The Docker services stay bound to localhost in dev mode. Caddy is the only
external ingress for this slice.

## Backend

The backend package lives in `backend/app`.

- `app/main.py` creates the FastAPI application.
- `app/api/health.py` exposes the first health endpoint.
- `app/core/config.py` reads environment-backed settings.
- `app/db/session.py` centralizes SQLAlchemy async engine/session construction.
- `backend/alembic/` is reserved for schema migrations.
- `app/api/auth.py` exposes simple dev login/logout/session endpoints.
- `app/api/runtime.py` exposes durable logs and system status for the UI.
- `app/api/project_docs.py` exposes read-only project markdown documentation
  for the operator UI.

All `/api/v1/*` routes are protected by a signed HttpOnly session cookie in dev
runtime, except `/api/v1/auth/*`. `/health` stays open for service checks.
Default dev credentials are `admin / pur-dev-password`; production-grade auth is
a separate future slice.

Project documentation API is intentionally allowlisted. It can read only
`README.md`, `AGENTS.md`, and markdown files below `docs/`, `notes/`, and
`state/` inside the current worktree. It rejects hidden/service paths and does
not expose arbitrary filesystem reads. In Docker dev mode the backend receives
the repository root as a read-only `/workspace` mount through
`PUR_PROJECT_DOCS_ROOT=/workspace`; outside Docker it falls back to the worktree
root inferred from the backend package path.

The first product slice uses a persisted enrichment job model:

- FastAPI creates enrichment jobs, serves job snapshots, and streams progress
  through Server-Sent Events.
- Celery workers execute the configured NLP pipeline outside the API process.
- PostgreSQL stores jobs, progress events, and final enrichment results.
- Redis is only the Celery broker; durable business state stays in PostgreSQL.
- NLP stages, domain signals, and rule sources are loaded from configuration
  instead of being hardcoded into application code.

## Telegram Runtime Flow

The production Telegram path is split into two durable queues around the
existing enrichment worker:

1. `userbot` listens to configured source chats with Telethon `StringSession`
   and `NewMessage` updates.
2. It persists each accepted source message in `telegram_source_messages`.
3. It creates a normal enrichment job and publishes the existing Celery task
   only after the source message row is saved, so the worker can always resolve
   Telegram context for notification routing.
4. The Celery `worker` enriches the text and writes the result.
5. For Telegram-originated jobs, notification routing writes pending messages
   to `notification_outbox`. Each Telegram source message can enqueue at most
   one outbox row per route through `(source_message_id, route_id)` uniqueness.
6. `notification-dispatcher` atomically claims pending outbox rows with
   `FOR UPDATE SKIP LOCKED`, then sends Telegram bot messages from the outbox.

Redis/Celery is the execution queue for NLP work. PostgreSQL is the source of
truth for Telegram source messages, enrichment state, and outgoing notification
outbox items. This makes deduplication, replay, audit, and operator analytics
possible even if a process restarts.

The userbot service is deliberately not connected to batch-runner output.
Batch-runner remains a local/offline test and calibration tool.

Telegram output batching follows Bot API constraints:

- `sendMessage` text is capped at 4096 characters.
- Messages are grouped by `bot_id + chat_id`.
- A full batch is sent as soon as adding the next item would exceed the limit.
- A non-full batch is sent when the oldest pending item is at least 5 minutes
  old.
- Dispatcher sends at most one message per configured chat at a time and keeps a
  per-chat spacing guard for Telegram rate limits.

Lead notification text is rendered from route templates. The default template
uses operator-readable blocks: score and temperature, review lane label,
solution areas, customer segments, top score reasons with matched snippets, a
short source text preview, and a separate links block. Custom route templates
can still use placeholders such as `{score}`, `{temperature}`,
`{review_lane_label}`, `{solution_areas}`, `{customer_segments}`,
`{reasons_detailed}`, `{text_preview}`, `{telegram_message_url}`, and
`{app_message_url}`.

Manual Testing enrichments do not enqueue Telegram lead notifications, even if
the text and score match a route. Notification delivery is limited to enrichment
jobs linked to `telegram_source_messages`, so repeated operator checks cannot
send duplicate lead alerts.

Outbox claiming uses status `sending` plus `claimed_at`. A second dispatcher
does not see rows already claimed by the first one; stale `sending` rows become
claimable again after the repository timeout.

Initial source-chat bootstrap is conservative: if a source has no
`last_message_id`, the userbot resolves the chat and stores the latest message
id as the cursor instead of importing the whole history. On listener startup,
already resolved sources get one bounded recovery read after `last_message_id`
to cover downtime, then live `NewMessage` updates drive ingestion. Historical
channel exports should still be processed through batch tooling.

Source-chat status is runtime state, not form state. `draft` means the source
row is saved but its `input_ref` has not yet been resolved by the userbot.
`resolved` means the backend has a concrete Telegram chat id and a cursor.
`error` stores the last resolution or runtime failure for operator review.
Saving editable Telegram input settings preserves existing runtime values such
as `last_message_id`, `last_error`, resolved Telegram chat id, account
authorization metadata, and cooldown state when the source identity is
unchanged. Changing the source identity intentionally resets the cursor.
Telegram `FloodWait` is treated as a temporary rate limit on the userbot
account. When Telethon returns it, the application stores `cooldown_until` and
`last_error` on `telegram_userbot_accounts`; while that timestamp is in the
future, the service skips the account and makes no Telegram read/resolve calls
for it, including after container restarts. Source chats stay in their previous
non-error state while retaining the wait reason in `last_error`. The legacy
history polling mode remains available for diagnostics, but the compose service
uses the live listener to avoid repeatedly resolving and reading every source
when there are no new messages.

When an account resumes immediately after `cooldown_until`, recovery is
throttled. The listener clears the account cooldown, then reads source recovery
one chat at a time with a smaller per-source limit. If a source has more
backlog than that limit, it drains the backlog in repeated small batches with a
delay between batches; then it waits between sources before entering live
subscription mode. Current dev Compose settings are:
`--batch-limit 100`, `--cooldown-recovery-limit 10`, and
`--cooldown-recovery-delay 15`. This prevents the first post-FloodWait restart
from bursting through all configured chats at once.

## Live Analytics And Runtime UI

The Analytics tab opens by default after login and uses a virtual run
`Telegram live` backed by PostgreSQL runtime tables:

- `telegram_source_messages` provides source text and Telegram ids.
- `enrichment_jobs` and `enrichment_results` provide processing state and
  deterministic lead assessment.
- `message_reviews` stores mutable operator ground truth for each source
  message: verdict, comment, and timestamps.
- Aggregates are computed from live completed enrichments.
- App links use `#/analytics/message/{source_message_id}`.
- Review links use `#/analytics/review/{source_message_id}` and open the full
  operator review workspace. Links from the candidate table include a `return`
  hash with current run, filters, and pagination offset so the review page can
  navigate back to the same working queue.
- Testing links use `#/testing?message_id={source_message_id}` and load the
  message text before starting a fresh enrichment job.
- Candidate list rows include saved `message_reviews` state and can be filtered
  by unreviewed/reviewed status and by operator verdict.

Migration `0008_runtime_analytics_cleanup` deletes old batch analytics rows so
the operator screen starts from connected Telegram channels. Batch imports can
still be used later for calibration/evaluation, but they are not the default
operator analytics source.

The Logs tab reads durable events from enrichment events, Telegram source
messages, userbot account/source errors, and notification outbox rows. The
System Status tab checks backend, PostgreSQL, Redis, userbot account cooldowns,
source-chat status counts, enrichment job counters, Telegram messages with
completed enrichment results, Telegram messages still waiting for enrichment,
and notification outbox counters.

Runtime logs are not a separate append-only log file. The API builds a unified
log view from operational PostgreSQL tables and applies service, level, text,
and time filters in SQL with limit/offset pagination. API page size defaults to
`PUR_RUNTIME_LOG_DEFAULT_LIMIT=50` and is capped by
`PUR_RUNTIME_LOG_MAX_LIMIT=200`.

Disk growth is controlled at the log-like table boundary:

- `enrichment_events` keeps the newest
  `PUR_RUNTIME_ENRICHMENT_EVENT_RETENTION_ROWS` rows, default `20000`.
- `notification_outbox` keeps the newest
  `PUR_RUNTIME_NOTIFICATION_OUTBOX_RETENTION_ROWS` non-pending rows, default
  `10000`; pending rows are never removed by retention.
- `telegram_source_messages` is source business data for analytics/review and
  is not deleted by runtime log retention.

`enrichment_events` are progress journal rows for worker jobs. One enrichment
job normally writes multiple events, so their count is intentionally different
from the count of rows visible in live Analytics. Live Analytics shows Telegram
source messages only after the corresponding enrichment result exists.

Manual review is deliberately separate from deterministic NLP output. A saved
review does not rewrite enrichment results, score, lane, or notification state;
it records operator feedback that can later be used for calibration and config
changes. The Review page combines the expanded Analytics evidence view with
four verdicts (`Лид`, `Не лид`, `Сомнительно`, `Шум`), a free comment, and a
constructor draft panel based on text selection.

Container stdout/stderr logs are also bounded in Docker Compose through the
`json-file` driver with `max-size=10m` and `max-file=5` on every service.

The Project Documentation tab reads the same repository documentation through
`GET /api/v1/project-docs` and `GET /api/v1/project-docs/{path}`. The frontend
groups files by root area (`Корень`, `docs`, `notes`, `state`) and renders a
lightweight markdown preview for operator navigation.

## NLP Configuration

Editable NLP behavior is stored in PostgreSQL table `nlp_config_revisions`.
`backend/config/nlp` contains only bootstrap defaults used to seed revision 1
when the database is empty.

- `pipeline` controls enabled stages.
- `signals` defines domain signals shown to the operator.
- `facts` defines structured fact extraction.
- `vendors`, `protocols`, `devices`, and `software` define alias catalogs for
  exact written variants of market terms.
- `pipeline.alias_matching` controls alias normalization and limited fuzzy
  matching for dictionary spellings.
- `lead_scoring` defines PUR lead thresholds, signal/fact weights, solution area
  mappings, customer segment mappings, intent signals, and noise signals.

Signal and fact rules may include a `group` display folder. The group is stored
in the PostgreSQL config revision together with the rule and is used by the
Settings Center to keep large rule lists navigable. It does not affect matching,
lead scoring, analytics filters, or API identifiers.

Yargy rules are externalized as configuration data, but the operator-facing
model is intentionally simpler than Yargy internals:

- Exact phrases: stable token sequences for abbreviations, technical notation,
  and wording where the exact written form matters. Concrete market names belong
  in alias catalogs instead of signal/fact phrase rules.
- Lemmatized phrases: Russian domain phrases entered as normal text and stored
  with both the operator's source text and backend-built lemmas.

Use lemmatized phrases for Russian domain language that appears in different
cases or forms. For example, operator input `умный дом` is stored as lemmas
`умный дом` and can match `умного дома` and `умному дому`. Operator input
`нужна консультация` is stored as lemmas `нужный консультация`.

The persisted config still uses `phrases` and `patterns` as the storage shape
because that is what the rule engine consumes. The web UI does not expose Yargy
predicate names as the product vocabulary.

Exact phrases are matched as lowercased literal text with word-like boundaries,
not through Yargy morphology. This keeps technical variants such as `220v` and
abbreviations in the exact matching mode. Product names, brands, protocols, and
software names are handled by alias catalogs. Lemmatized phrases use Yargy
`normalized` tokens. Documents that still contain `caseless` are invalid for v2
and must be replaced by a new PostgreSQL config revision or reseeded from
current bootstrap YAML.

Alias catalogs are separate from domain signals. Alias catalogs store written
variants: canonical name, alias type (`vendor`, `protocol`, `device`,
`software`, or `model`), Latin/Cyrillic/transliterated/mistyped spellings, and
`fact_types` emitted when the alias matches. Alias matching uses casefold, so
registry/case is ignored. The configurable `alias_matching` layer can also
normalize `ё/е`, separator variants such as `Wi-Fi`/`WiFi`, mixed
Latin/Cyrillic confusable letters such as `Нептyн`, and a bounded fuzzy edit
distance. Fuzzy is deliberately limited by `fuzzy_min_length`,
`fuzzy_max_distance`, `fuzzy_long_min_length`, `fuzzy_long_max_distance`, and
`fuzzy_excluded_aliases` so short aliases such as `sst`, `knx`, or `dvr` do not
start matching random words. Enrichment output still returns the original span
text from the input message.

If several alias matches overlap, the pipeline keeps the longest span and drops
shorter nested matches. For example, `Нептуп ProW` should emit the model/vendor
facts for the full phrase, not an extra `Нептуп` fact; `Profi Wi-Fi` should not
also emit a nested `Wi-Fi` protocol fact. Alias spellings are curated so the same
literal spelling is not duplicated across catalogs; choose the most specific
catalog (`vendors`, `software`, `devices`, or `protocols`) and make domain
signals depend on that catalog explicitly.

Domain signals are the inference layer over semantic phrases, alias catalogs,
and facts. They remain semantic categories such as `smart_home_platform`,
`protocol_gateway`, `leak_protection`, `lighting_automation`,
`climate_automation`, `access_control`, `intercom`, `video_surveillance`, and
`power_backup`. A signal may define `match.aliases` dependencies by selecting an
alias catalog (`vendors`, `software`, `devices`, etc.) and concrete alias keys
such as `yandex`, `aqara`, `alice`, or `leak_sensor`. If a matching alias is
found, the signal is emitted with `source=alias_catalog`.
Signals may also define `match.facts` dependencies to build a higher-level
signal from already extracted fact types.

Brand/model spellings must not be duplicated in domain signal or fact phrase
rules. For example, `Нептун`, `Нептуп`, `Neptun ProW`, and `Profi Wi-Fi` live in
the `neptun` vendor alias. The `water_leak_protection` and `leak_protection`
signals explicitly reference that alias through `match.aliases`; the alias
itself emits `vendor`/`model` facts. Domain signal rules keep only semantic
language such as `датчик протечки` or `защита от протечек`. Lead scoring uses
the resulting signal/fact types, not the storage location of the rule.

## Lead Assessment

The `lead_scoring` stage runs after Yargy fact and signal extraction. It does not
contain hardcoded PUR business rules: the code sums configured signal/fact
weights, applies configured thresholds, maps matched signal/fact types to
solution areas and customer segments, and returns explanatory reasons.

Generic demand signals such as `need`, `provider_search`, `consultation_request`,
and generic `work_type` facts are intentionally low-weight. They explain intent,
but should not by themselves turn an off-domain message into a PUR lead. A strong
lead should normally combine intent with PUR domain signals or facts such as
smart home, video surveillance, access control, leak protection, lighting,
climate, power backup, or engineering network context.

`lead_assessment` is part of every new enrichment result when the stage is
enabled:

- `is_lead`: whether the score reaches the configured lead threshold.
- `score`: non-negative deterministic score.
- `temperature`: `none`, `cold`, `warm`, or `hot`.
- `solution_areas` and `customer_segments`: configured taxonomy matches.
- `intent_signals` and `noise_signals`: configured positive/noise categories.
- `reasons`: score contributions with source, key, weight, and matched texts.
- `review_lane`: the first configured review lane that matches the same
  extracted arrays, score, and temperature; it includes the lane label,
  description, and matched match-group indexes.

Older persisted results without `lead_assessment` remain readable and return the
field as `null`.

Extracted `facts` and `domain_signals` may include an `explanation` string.
The explanation is generated by the enrichment mechanism and tells the operator
whether the item came from a semantic rule, alias catalog dependency, or fact
dependency. The UI should present these explanations together with human labels
from the active config. Stable keys remain available for API filters and
debugging, but operator-facing summaries should prefer labels.

Extracted `facts` and `domain_signals` also include `settings_refs` when the
pipeline can identify the responsible editable setting. A reference points to a
rule (`signals` or `facts`) or an alias catalog row (`aliases` with `catalog`
and `key`). The frontend turns these references into stable hash deeplinks such
as `#/settings/signals/smart_home_automation` and
`#/settings/aliases/devices/electric_curtain`.

## Batch Analytics

Batch enrichment produces local JSONL artifacts under `artifacts/`. The
analytics import CLI turns a completed batch run into PostgreSQL records:

- `analytics_runs` stores run metadata, source paths, totals, timing, and raw
  summary JSON.
- `analytics_candidates` stores only candidate lead messages with message id,
  source text, score, temperature, review lane, assessment arrays, matched signals,
  and facts.
- `analytics_aggregates` stores precomputed counts for score buckets,
  review lanes, temperatures, domain signals, facts, reasons, solution areas,
  customer segments, intent signals, and noise signals.

FastAPI exposes this slice through:

- `GET /api/v1/analytics/runs`
- `GET /api/v1/analytics/runs/{run_id}/summary`
- `GET /api/v1/analytics/runs/{run_id}/candidates`, with filters for score,
  temperature, domain signal, reason key, solution area, customer segment, review
  lane, and text search.

Review lanes are not hardcoded analytics heuristics. They are configured under
`lead_scoring.review_lanes` in the PostgreSQL-backed NLP config revision. Each
lane defines priority, match groups over already extracted signal/fact/reason/
segment arrays, optional score/temperature bounds, and exclusion lists. The
analytics import assigns a lane to each candidate and precomputes lane aggregates
so the UI can filter review queues without scanning raw JSONL artifacts.

The repository currently uses PostgreSQL because the UI needs imported run
review, filters, and aggregates over tens of thousands of candidates, not raw
warehouse analytics over every enriched span. ClickHouse remains a future option
for full historical OLAP over all messages, traces, token-level data, and many
batch runs.

## Settings Center

The settings UI exposes the active NLP configuration through FastAPI:

- `GET /api/v1/settings` returns editable NLP/domain settings and read-only
  runtime settings. It also returns notification channel settings with secret
  values masked.
- `PUT /api/v1/settings/nlp` validates NLP settings and creates a new active
  PostgreSQL config revision.
- `POST /api/v1/settings/nlp/preview` runs a draft configuration against a text
  without saving it.
- `POST /api/v1/settings/nlp/semantic-pattern` converts operator-entered rule
  text into a lemmatized phrase and returns both `source_text` and lemma tokens.
- `PUT /api/v1/settings/notifications` stores Telegram bots, chats, and routing
  rules.
- `POST /api/v1/settings/notifications/telegram/bots/{bot_id}/test` validates a
  saved bot token through Telegram `getMe`.
- `POST /api/v1/settings/notifications/telegram/chats/{chat_id}/test` sends a
  test message to a saved chat using a selected saved bot.
- `PUT /api/v1/settings/telegram-ingestion` stores Telegram userbot accounts
  and source chats.
- `POST /api/v1/settings/telegram-ingestion/accounts/{account_id}/send-code`
  sends an interactive Telegram login code for a saved userbot account.
- `POST /api/v1/settings/telegram-ingestion/accounts/{account_id}/sign-in`
  completes userbot login and stores a Telethon `StringSession`.
- `GET /api/v1/analytics/messages/{message_id}` returns a live Telegram
  candidate plus saved operator review state.
- `PUT /api/v1/analytics/messages/{message_id}/review` upserts operator
  verdict/comment into `message_reviews`.
- `GET /api/v1/runtime/logs` returns recent durable runtime events.
- `GET /api/v1/runtime/status` returns backend/database/Redis/userbot/worker/
  notification-dispatcher status summaries.

PostgreSQL table `nlp_config_revisions` is the active source of truth for
editable NLP settings. `backend/config/nlp/*.yaml` is only a bootstrap default:
if the database has no active revision, the backend seeds revision 1 from YAML.
Celery loads the active database revision per job, so saved UI changes apply to
the next enrichment job. Runtime settings such as database URL, Redis URL, CORS,
and config paths are visible but read-only because they come from environment
configuration and may require process/container restart.

Each save creates a new active revision and deactivates the previous one. This
keeps future history/diff/rollback work aligned with the current API shape.
When a new bootstrap document or pipeline stage is introduced, the repository
can create a new active revision by merging missing bootstrap documents/stages
into the current active configuration without overwriting existing edited
signals or facts.

The frontend Settings Center edits exact phrases and lemmatized phrases as
separate lists with add/edit/delete actions. New lemmatized phrases are created
from natural operator input through the backend semantic-pattern endpoint so the
UI can show both the original text and the generated lemmas. Domain signals also
expose editable `match.aliases` and `match.facts` dependencies as add/remove
rows with catalog, alias, and fact selectors rather than text mini-language. The
UI has a Help page that explains these matching modes. The Settings Center also
exposes the alias catalogs as editable lists for vended platforms, protocols,
devices, and software. Lead scoring settings include review lanes, so review
queue logic is visible and editable together with thresholds, weights, taxonomy
mappings, intent signals, and noise signals.

Notification routing is a separate settings area, not part of NLP config
revisions. The first delivery adapter is Telegram. The settings live in
PostgreSQL table `notification_settings` as a routing aggregate with three
separate entity lists:

- bots: named Telegram bots with enabled flag and secret token;
- chats: named Telegram destination chats/groups with enabled flag and
  `telegram_chat_id`;
- routes: priority-ordered rules that connect one bot to one chat when
  enrichment output matches configured conditions.

The Telegram bot token is stored for sending but is never returned by read APIs;
the UI receives only `has_token` and `token_masked`. Runtime enrichment jobs
dispatch notifications after a job is completed. Dispatch errors are logged and
must not change the enrichment job result. Batch enrichment remains a testing
and calibration tool and does not call notification routing. The future Telegram
userbot should create normal runtime enrichment jobs after receiving messages,
then this dispatcher will use the completed result.

## Frontend

The frontend package lives in `frontend/src`.

- `App.tsx` is the first operator workspace shell.
- `main.tsx` mounts React.
- `styles.css` holds application-level layout styles.

The first operator screen provides:

- text input for arbitrary text;
- live backend progress with stage names and percentages;
- annotated source text after completion;
- PUR lead verdict with score, temperature, exact score formula, reasons,
  solution areas, customer segments, review lane calculation, and noise signals;
- overview evidence tables for dictionary entities, facts, and domain signals
  with matched text, human type label, source, and explanation;
- linked calculation/evidence tables. Whenever the result can be traced to a
  setting, the UI renders a link to a separate settings detail page for that
  signal, fact, alias, weight, solution area, customer segment, or review lane;
- structured result tabs for overview, entities, facts, domain signals, tokens,
  syntax, and pipeline trace.

Settings deeplinks are hash routes inside the SPA. Navigating to a settings
detail page does not reload the application, so the current enrichment input,
job result, and browser back/forward context remain available.

Backend span ranges are Unicode code point offsets, because Python strings use
code point indexing. Browser rendering uses UTF-16 code units. The frontend must
convert backend `range.start`/`range.stop` values before slicing source text for
highlighting; otherwise any emoji or other non-BMP character before a match
shifts the highlighted fragment.

The analytics screen provides live Telegram review and imported batch-run
calibration views:

- run selector and refresh;
- KPIs for processed messages, lead candidates, candidate rate, and failures;
- score buckets and top aggregate lists;
- filterable candidate table by score, temperature, domain signal, reason,
  solution area, customer segment, review lane, source channel, received date,
  review status, verdict, and text. Domain filters are selected from aggregate
  values instead of free-form operator input;
- review links preserve queue context, while Testing links use stable
  `#/testing?message_id=...` hashes and reload the Telegram source text.

## Legacy Reference

The v1 codebase remains available through git history and the old worktree at:

`/home/admin/AI-AGENT/data/projects/oleg-telegram-leads`

Production-confirmed lead examples are kept as ignored local artifacts under:

`artifacts/prod-lead-messages/2026-05-07`
