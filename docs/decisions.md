# Decisions

## 2026-05-07: Fresh v2 Codebase

PUR Leads v1 is historical reference only. V2 starts from a clean scaffold rather
than extending the old source tree.

## 2026-05-07: Core Stack

Use PostgreSQL, FastAPI, React, and Docker Compose as the base stack.

Rationale:

- PostgreSQL is the production database from day one.
- FastAPI gives a small, typed Python API surface.
- React + Vite + TypeScript gives a focused frontend toolchain.
- Docker Compose keeps local service wiring explicit and reproducible.

## 2026-05-07: Project Working Rules

Use root `AGENTS.md` as the mandatory working rules file for PUR Leads v2.

Rationale:

- Chat history is not a durable source of truth.
- Future agent sessions need one predictable place for project rules.
- Process rules, architecture rules, verification rules, and Definition of Done
  should be versioned with the project.

## 2026-05-07: Dev Containers Do Not Bake Source

In development mode, Docker images provide runtime tools and dependency layers only.
Backend and frontend source code is mounted from the host through bind volumes.

Rationale:

- The project is currently in active local development.
- Source changes should be visible without rebuilding images.
- Production image design is a separate future decision.

## 2026-05-07: Architecture Principles

Build v2 around Hexagonal Architecture / Ports and Adapters with explicit use
cases, domain boundaries, dependency inversion, repositories as ports, and clear
separation between API schemas, domain objects, DB models, and frontend types.

Apply GRASP, SOLID, DDD tactical patterns where useful, Dependency Injection,
Repository + Unit of Work, and testability by design.

Rationale:

- PUR Leads will contain substantial business behavior around Telegram data,
  lead review, NLP classification, evals, and operator workflows.
- Keeping framework and infrastructure dependencies outside the domain makes the
  system easier to test and change.
- Adult boundaries are cheaper to establish now than retrofit later.

## 2026-05-07: Frontend Product Direction

Build a working operator interface, not a landing page. Use Google Material
Design through MUI for the React UI.

Rationale:

- The product is an operational tool.
- Operators need dense, predictable screens: tables, filters, lists, forms,
  statuses, and review flows.
- Marketing-style hero sections and decorative UI do not serve the workflow.

## 2026-05-07: Verification Policy

All behavior-affecting changes are business logic and must be verified with a
method appropriate to risk. Tests are valuable when they protect real behavior;
do not write tests only for coverage theater.

Rationale:

- Backend, frontend, migrations, imports, classification, UI flow, and Docker
  wiring can all affect user-visible behavior.
- Verification may be unit, integration, API, UI smoke, manual, or another
  reproducible check depending on the change.

## 2026-05-07: Production-Derived Data

Production lead exports may be committed when they are useful for development,
evals, or regressions. Before committing production-derived data, explicitly
inspect what is being added and avoid accidental large dumps, secrets, tokens, or
irrelevant sensitive data.

Use `artifacts/` for local temporary exports and `datasets/` for small
versioned datasets when data should live in git.

Rationale:

- Real lead examples are important for NLP/eval quality.
- Data should be intentionally curated when it becomes part of the repository.

## 2026-05-07: Externalized Domain Configuration

Domain rules, signal definitions, dictionaries, thresholds, weights, enabled NLP
pipeline stages, UI labels for domain types, and provider-specific settings
should not be hardcoded in application code.

Rationale:

- PUR Leads will evolve through NLP experiments and domain feedback.
- Changing signal definitions should not require editing application mechanics.
- Configuration and rule files make behavior reviewable and reproducible.

## 2026-05-07: Enrichment Jobs Use Worker Queue From The Start

Use a separate Celery worker with Redis as the broker for text enrichment jobs.
FastAPI creates jobs, exposes snapshots, and streams progress through SSE.
PostgreSQL stores jobs, progress events, and final results.

Rationale:

- NLP enrichment is CPU-heavy enough to keep out of the API request path.
- The frontend needs detailed backend progress, including current stage and
  percentage.
- Persisted job state makes snapshots and page recovery possible.
- Starting with the worker boundary avoids replacing the execution model after
  the UI contract is built.

## 2026-05-07: Host Caddy Exposes Dev UI

Expose the v2 dev web interface through the existing host Caddy service at
`https://secclaw.qlbc.ru:19443/`.

Routing:

- `/` proxies to the Vite dev server on `127.0.0.1:5173`.
- `/api/*` proxies to FastAPI on `127.0.0.1:8000`.
- SSE uses the same `/api/*` route and requires streaming-friendly proxying.

Rationale:

- The user can review the interface without opening a browser from the agent
  environment.
- Backend and frontend remain in Docker Compose dev mode with localhost-bound
  ports.
- Caddy is an external ingress concern and stays outside the repository.
- The host firewall must explicitly allow `19443/tcp`; otherwise local checks
  from the host can pass while external browsers time out.

## 2026-05-07: Settings Center Stores NLP Settings In PostgreSQL

Expose all current NLP/domain settings in the operator UI and allow editing them
through FastAPI. Persist editable NLP/domain settings as PostgreSQL revisions in
`nlp_config_revisions`. Keep `backend/config/nlp` YAML files as bootstrap
defaults only, used when the database has no active revision yet. Keep runtime/env
settings read-only.

Rationale:

- Settings are product data and must survive through the operational database,
  not through mutable files.
- Revision rows make future diff, audit, rollback, and publication workflows
  natural.
- YAML remains useful as versioned bootstrap defaults and reviewable seed data,
  but it is not the active editable store.
- Runtime settings affect process wiring and secrets; showing them read-only is
  safer until auth, audit, and restart procedures exist.

## 2026-05-07: PUR Lead Assessment Is Deterministic And Explainable

Detect potential PUR clients with a deterministic lead assessment layer instead
of an LLM. The layer consumes extracted domain signals and facts, applies
PostgreSQL-backed scoring settings, and returns `lead_assessment` with a score,
temperature, solution areas, customer segments, reasons, and noise signals.

Rationale:

- The current task needs explainable classification that can be edited from the
  Settings Center and verified against known lead examples.
- Business meaning belongs in PostgreSQL config revisions: thresholds, weights,
  taxonomy mappings, and noise definitions are product settings, not code.
- A deterministic layer gives a stable baseline for future evals; ML/LLM
  classifiers can be added later once we have enough labeled examples and known
  failure modes.
- Noise signals must be first-class so equipment-only/DIY/sale posts can be
  explained as non-leads rather than silently missed.

## 2026-05-07: Smart-Home Market Terms Live In Alias Catalogs

Keep domain signals as semantic categories and move market spellings into
separate PostgreSQL-backed alias catalogs: `vendors`, `protocols`, `devices`,
and `software`. Each alias row stores canonical name, alias type, written
variants, and fact types emitted by alias matches. Domain signals reference
alias entries through identity facts such as `alias:vendors:neptun` in
`match.facts`. Bootstrap YAML files seed a curated first pass for common РФ/СНГ
smart-home platforms, protocols, devices, software, and security/leak/power/
climate brands.

Rationale:

- Vendor and device spellings change faster than the semantic taxonomy; mixing
  them directly into signal rules makes settings hard to audit and edit.
- Operators need to see and edit human spellings such as `Aqara/Акара`,
  `Zigbee/Зигби`, `Home Assistant/Хоум Ассистант`, and `Neptun/Нептун/Нептуп`
  without changing code.
- Exact alias matching is deterministic and cheap, while explicit signal
  dependencies keep lead scoring explainable.
- The curated bootstrap pass is intentionally broad but not final; production
  review and eval data should continue extending these catalogs.

## 2026-05-08: Rule Groups Are Editable Configuration Metadata

Domain signal and fact rules may carry a `group` display folder. The group is
stored in PostgreSQL-backed NLP config revisions and in bootstrap YAML defaults,
then rendered by the Settings Center as grouped accordions.

Rationale:

- The PUR domain signal list is already too large for one flat editor.
- Grouping must be part of editable configuration, not hardcoded frontend logic.
- `group` is navigation metadata only: it does not change extraction, confidence,
  scoring, review lanes, or analytics semantics.
- Russian group labels are acceptable because they are operator-facing folder
  names, while stable scoring/filter keys remain English `type` values.

## 2026-05-08: Brand Spellings Stay In Alias Catalogs

Do not duplicate concrete brands, model names, product names, or typo variants
inside domain signal/fact phrase rules. Domain signals and facts describe
semantic categories. Alias catalogs own market spellings and emit only
structured `fact_types`. Domain signals own the dependency graph through
`match.facts`.

Rationale:

- `Нептун`, `Нептуп`, `Neptun ProW`, and `Profi Wi-Fi` are vendor/model aliases,
  not semantic signal phrases.
- The durable relationship for signal detection is now stored on the signal:
  `water_leak_protection.match.facts` selects facts such as
  `alias:vendors:neptun`. This makes the inference layer explicit and avoids
  hidden reverse links inside dictionaries.
- Alias rows still emit facts such as `vendor`, `model`, `protocol`, `software`,
  or `automation_component`; signals can depend on those facts through
  `match.facts` when useful.
- This keeps scoring explainable while avoiding direct `dictionary -> signal`
  extraction paths for the same brand span.

## 2026-05-08: Domain Signals Own Dictionary Dependencies

Domain signals are the inference layer over dictionaries and facts. A signal
may be triggered by exact/lemmatized semantic phrases or `match.facts`
dependencies on already extracted facts. Alias catalogs no longer contain
`signal_types`.

Rationale:

- The operator needs to understand why `smart_home_platform` depends on alias
  keys such as `yandex`, `alice`, and `knx` from the signal configuration
  itself.
- Keeping dependencies on the signal side removes the second source of truth
  that existed when alias rows also declared signal outputs.
- `Алиса` is modeled as `smart_home_platform`, not as both platform and broad
  automation, to avoid overheating weak child-room/audio wiring mentions.

## 2026-05-08: Telegram Runtime Uses Durable Postgres Outboxes

Use Telethon userbot accounts for Telegram input and Telegram bot accounts for
Telegram output, but keep both production handoff points durable in PostgreSQL.

Runtime flow:

- `userbot` receives/polls source chats and persists source messages.
- It creates normal enrichment jobs and records task publication in
  `enrichment_task_outbox`.
- `enrichment-dispatcher` publishes pending task outbox rows to the existing
  Celery/Redis worker queue and retries broker publication failures from
  PostgreSQL.
- The enrichment worker stores results and enqueues matched notifications in
  `notification_outbox` instead of sending immediately.
- `notification-dispatcher` batches outbox items by bot+chat and sends Telegram
  bot messages.

Rationale:

- Redis/Celery is good for execution, but Telegram source messages and pending
  notifications are business records that must survive restarts and support
  deduplication/retry/audit.
- RabbitMQ would add routing mechanics before the product needs them. If
  broker-level exchanges, dead-letter policies, or high-volume fanout become a
  real requirement, it can be introduced behind the same ports later.
- Batch-runner must remain offline/testing tooling and must not dispatch
  production notifications.
- Celery remains an execution queue, not the source of truth. If the API or
  userbot process dies after committing an enrichment job but before broker
  publication succeeds, PostgreSQL must still contain a retryable task handoff.
- Telegram has message size and frequency limits, so output must batch leads:
  pack up to the Bot API text limit and flush non-full batches when the oldest
  item waits 5 minutes.

## 2026-05-07: Yargy Parsers Share Morphology Resources

Compile Yargy parsers once per `RussianTextEnricher` instance and share one
Yargy `MorphTokenizer` across signal, fact, and alias parsers.

Rationale:

- Creating a parser per configured rule with its own default `MorphTokenizer`
  also creates many `pymorphy2` analyzers.
- With broad PUR settings this made ordinary tests and batch runs allocate
  multiple GB of RSS and could kill unrelated terminal/tmux sessions under
  memory pressure.
- Shared tokenizer state keeps `normalized` semantic matching available while
  making default backend tests safe to run by default.

## 2026-05-07: Rule Matching Has Two Operator Modes

Expose only two rule matching modes to operators and API clients: exact phrases
and lemmatized phrases. Exact phrases are lowercased token-sequence matches with
word-like boundaries and non-word separators between tokens; lemmatized phrases
are stored as Yargy `normalized` tokens. Do not use `caseless` as a new
persisted/operator-facing rule predicate.

Rationale:

- The user-facing distinction must stay understandable: exact spelling versus
  semantic Russian word forms.
- Technical tokens such as `Wi-Fi`, `220v`, `Z-Wave`, abbreviations, and product
  names are exact spellings and should not depend on Yargy tokenization.
- Old `caseless` documents are not supported by v2. They should be replaced by
  a fresh PostgreSQL config revision or reseeded from current bootstrap YAML
  instead of hidden compatibility code.

## 2026-05-08: Alias Matching Has Configurable Normalization And Limited Fuzzy

Alias catalogs remain curated dictionaries, but matching is no longer only a
plain lowercased phrase search. The alias layer now applies configurable
normalization from `pipeline.alias_matching`: casefold, optional `ё/е`
normalization, separator folding for variants such as `Profi Wi-Fi` versus
`Profi-WiFi`, mixed Latin/Cyrillic confusable characters, and bounded fuzzy edit
distance.

Rationale:

- Market spellings are noisy: users write `Нептyн` with a Latin `y`,
  `neptun pro w`, `Profi-WiFi`, and similar variants.
- Exact aliases remain the source of truth; fuzzy only expands matching around
  configured aliases and returns the original text span.
- Fuzzy must be conservative. It is disabled for aliases shorter than
  `fuzzy_min_length`, capped by distance settings, and can be explicitly blocked
  with `fuzzy_excluded_aliases` for abbreviations or risky short model names.

## 2026-05-07: Analytics Starts In PostgreSQL

Store imported batch analytics in PostgreSQL first: runs, candidate lead
messages, and precomputed aggregates. Do not introduce ClickHouse until the
product needs a raw analytical warehouse over all messages, all spans, many
historical runs, or ad-hoc OLAP workloads that PostgreSQL cannot serve well.

Rationale:

- The immediate UI workflow reviews roughly tens of thousands of candidates per
  run, filters them, and compares aggregate counts.
- PostgreSQL is already the operational source of truth and keeps migrations,
  backup, deployment, and local dev simpler while the product workflow is still
  changing.
- Precomputed aggregates avoid scanning the 3+ GB full enrichment dump on every
  page load.
- A later ClickHouse slice should receive stable export/import contracts from
  this boundary instead of becoming another active source of truth too early.

## 2026-05-08: Analytics Review Lanes Are Configured

Add review lanes as a configurable product layer over imported analytics
candidates. A lane is not a hardcoded Python heuristic: it lives in
`lead_scoring.review_lanes` inside the PostgreSQL-backed NLP config revision and
matches already extracted signal, fact, reason, solution-area, customer-segment,
intent, and noise arrays.

Rationale:

- The current candidate set is intentionally broad, so operators need review
  queues such as direct PUR leads, project context, domain interest, generic
  demand, and noise.
- Threshold-only filtering loses confirmed positives and does not explain why a
  candidate should be reviewed first.
- Keeping lane definitions in config preserves the project rule that domain
  logic remains externalized and editable.
- Persisting the assigned lane during analytics import makes the UI filters and
  aggregates cheap in PostgreSQL.

## 2026-05-08: Alias Catalogs Prefer Specific Longest Matches

Alias catalogs should produce concise facts instead of every possible nested
match. When alias spans overlap, the enrichment pipeline keeps the longest span
and drops shorter nested aliases. Curated settings also avoid duplicating the
same literal spelling across `vendors`, `software`, `devices`, and `protocols`.

Rationale:

- Market aliases contain nested names: `Нептуп` inside `Нептуп ProW`, `Wi-Fi`
  inside `Profi Wi-Fi`, and vendor names inside longer platform names.
- Emitting every nested alias makes the UI noisy and can inflate explanations.
- The strongest explanation is usually the most specific full phrase. If one
  spelling must produce multiple facts, attach multiple `fact_types` to that
  one alias entry instead of duplicating the spelling across catalogs.

## 2026-05-08: Off-Domain Demand Is Not A PUR Lead By Itself

Generic demand and intent markers remain useful context, but their configured
weights are low enough that a message such as "где заказать обычный стол" does
not become a PUR lead without a relevant PUR domain signal or fact.

Rationale:

- The product goal is to find potential PUR clients, not every procurement or
  advice request in a chat.
- `provider_search`, `consultation_request`, `need`, and `work_type` should
  explain why a domain-relevant message is actionable.
- Analytics can still keep off-domain demand in its own review lane when needed,
  but the default deterministic `is_lead` verdict should require more than
  generic demand language.

## 2026-05-08: Enrichment Overview Must Explain The Calculation

The enrichment overview is the operator's primary debugging surface. It should
show dictionary entities, facts, domain signals, exact lead-score arithmetic,
solution-area matches, customer-segment matches, and review-lane selection with
human labels and generated explanations.

Rationale:

- Operators should not have to reverse-engineer why a text became a lead by
  jumping between JSON tabs and Settings Center.
- Scoring is deterministic and configured, so the UI can show the same formula
  the backend used instead of a prose approximation.
- Review lanes are also configured rules over extracted arrays; showing the
  selected lane and matched groups makes queue assignment auditable.
- Backend ranges are Python Unicode code point offsets. Frontend highlighting
  must convert them to JavaScript UTF-16 offsets so emoji and similar characters
  do not shift highlighted source fragments.

## 2026-05-08: Enrichment Evidence Links To Settings Deeplinks

Whenever an enrichment result can identify which editable setting produced a
fact or signal, the backend includes a structured `settings_refs` entry. The
frontend renders those references as hash deeplinks to separate settings detail
pages, for example `#/settings/signals/smart_home_automation`,
`#/settings/aliases/devices/electric_curtain`, and
`#/settings/lead-scoring/review-lane/direct_pur_lead`.

Rationale:

- Operators need to verify a score reason or evidence row from the result
  itself, without manually searching through long settings lists.
- Links should be ordinary browser-addressable links, not only local buttons, so
  they support copy/paste, browser back/forward, and direct page opening.
- The route stays inside the React SPA so the current input text and enrichment
  result remain in memory when the operator returns to `Обогащение`.

## 2026-05-08: Telegram Notifications Use Bots, Chats, And Routes

Add notification delivery as application/infrastructure adapters. Telegram is
the first delivery adapter, but its configuration is not a single channel:

- bots are named Telegram bots and own secret tokens;
- chats are named Telegram destinations and own `telegram_chat_id` values;
- routes are priority-ordered rules that select one bot and one chat based on
  completed enrichment output.

Route conditions can use the data already produced by enrichment:
`lead_assessment.is_lead`, score bounds, temperature, review lane, solution
areas, customer segments, domain signals, facts, score reasons, and noise
signals. Routes have `all` or `any` condition mode and a message template.

Store notification settings in PostgreSQL table `notification_settings` as a
routing aggregate. This is separate from NLP config revisions because delivery
channels are operational integration settings, not text-analysis rules. API
responses must not return full secret values: Telegram bot responses expose only
`has_token` and a masked token.

Runtime enrichment jobs dispatch notifications after a job is completed.
Batch-runner does not dispatch notifications; it remains an offline testing and
calibration tool. The future Telegram userbot should receive source messages
and create normal runtime enrichment jobs, which then pass through notification
routing after completion.

Rationale:

- The upcoming lead workflow needs outbound notifications, but Telegram should
  not leak into domain objects or NLP pipeline code.
- Keeping delivery behind ports/adapters lets us add more channels later without
  rewriting use cases.
- Settings belong in PostgreSQL per the project rule that product/runtime
  integration settings are not hardcoded.
- Test-send gives the operator a direct way to validate token/chat configuration
  before real lead notifications are wired.
- Separating bots, chats, and routes avoids coupling one bot to one group and
  lets operators route hot leads, noise, segments, or solution areas differently.
- Batch runs over historical archives can contain thousands of matches, so they
  must not accidentally send Telegram messages.

## 2026-05-08: Runtime Operator UI Is Authenticated And Live

The dev operator app is closed with simple signed-cookie authentication. The
default credentials are `admin / pur-dev-password` and can be overridden through
environment variables. This is deliberately a dev/runtime guard, not a final
multi-user auth subsystem.

The Analytics tab is now the default landing page and uses live Telegram runtime
data, not imported batch analytics. A virtual run `Telegram live` is computed
from `telegram_source_messages`, `enrichment_jobs`, and `enrichment_results`.
Migration `0008_runtime_analytics_cleanup` clears old imported analytics rows
so the operator does not review stale archive data as if it came from connected
channels.

Notifications for Telegram-originated enrichments include source-message links:
a Telegram permalink when derivable and an app link to
`#/analytics/message/{source_message_id}`. Analytics rows also offer a direct
"Проверить" action that opens the message in Testing and starts enrichment.
Only enrichment jobs linked to `telegram_source_messages` enqueue notifications;
manual Testing jobs intentionally skip notification routing.

Rationale:

- The connected-channel workflow is now the primary production-like path.
- Batch analytics remains useful for calibration, but mixing old archive rows
  with live channel rows makes review quality hard to reason about.
- Operators need to move between Telegram, analytics review, and deterministic
  testing without manually copying text.
- Testing is a diagnostic workflow, so rechecking the same text must not resend
  production lead notifications.
- A simple dev auth layer is enough for the current exposed dev URL while
  keeping production identity/access design separate.

## 2026-05-08: Telegram Input Uses Live Listener And Persisted Cooldown

The Telegram input service runs in live listener mode by default. It uses
Telethon `NewMessage` updates for configured source chats, persists every new
text message in `telegram_source_messages`, and creates normal enrichment jobs
through the existing Celery/Redis worker queue. On startup, a source without a
cursor is bootstrapped by saving the current latest Telegram message id; a
resolved source gets one bounded recovery read after `last_message_id` to cover
service downtime. Historical imports stay in batch tooling.

Telegram `FloodWait` is persisted at the userbot-account level as
`cooldown_until` plus `last_error`. While that timestamp is in the future, the
service skips the account entirely and makes no Telegram read/resolve calls,
including after container restarts. The old polling mode remains available only
as an explicit diagnostic mode and uses the same cooldown guard.

After an account resumes from cooldown, source recovery is intentionally
throttled: each source is recovered one at a time, backlog is drained in small
delayed batches, and the service also delays between source reads. The dev
runtime uses 10 messages per recovery batch and 15 seconds between batches or
sources.

System Status separates these counters:

- worker progress journal rows in `enrichment_events`;
- Telegram messages received by userbot;
- Telegram messages whose enrichment result is ready and therefore visible in
  live Analytics;
- Telegram messages still waiting for enrichment or failed enrichment.

Rationale:

- FloodWait is based on Telegram API calls, not the number of new messages. A
  polling loop that repeatedly resolves and reads quiet chats can still trigger
  rate limits.
- Persisting cooldown prevents process restarts from immediately retrying and
  extending the wait window.
- Soft recovery after cooldown prevents the first successful retry from
  immediately reading every configured chat/channel and triggering another
  FloodWait.
- Live updates plus one bounded recovery read preserve durability without
  importing old channel history by accident.
- Operator status must not imply that worker progress events are the same thing
  as analytics candidates.

## 2026-05-08: Manual Review Is A Separate Operator Workspace

Analytics remains a scanning surface. Candidate rows keep quick links, but
manual verdicts are handled by a dedicated route:
`#/analytics/review/{source_message_id}`.

Review state is stored in `message_reviews`, keyed by the Telegram source
message id. The row contains operator feedback: verdict, comment, tags, and
timestamps. It does not modify the deterministic enrichment result, score,
temperature, or automatic review lane. The Analytics API overlays that immutable
evidence with an effective operator lead status: `lead` forces lead,
`not_lead`/`noise` force non-lead, and `uncertain` keeps the automatic verdict.
Saving `not_lead` or `noise` cancels unsent pending/sending notification outbox
rows for the same Telegram source message so a manual noise verdict cannot be
sent later as a lead alert.

The Review page combines the existing expanded Analytics evidence with manual
actions: `Лид`, `Не лид`, `Сомнительно`, `Шум`, a comment field, and a
text-selection constructor.

Rationale:

- Operator ground truth must be preserved separately from machine output so it
  can be audited and reused for calibration.
- Putting verdict buttons directly into the Analytics table would make the
  scanning view too dense and too easy to click accidentally.
- A separate page gives enough room for evidence, comments, and the future
  settings constructor without duplicating the whole Analytics table.

## 2026-05-08: Review Constructor Writes NLP Settings

The Review page constructor now supports all first-pass targets:

- `В словарь`: selected text is added to an existing or new alias catalog item
  under `vendors`, `protocols`, `devices`, or `software`.
- `В факт`: selected text is added to an existing or new fact rule as either an
  exact phrase or a lemmatized phrase.
- `В доменный сигнал`: selected text is added to an existing or new signal rule
  as either an exact phrase or a lemmatized phrase.
- `В шум`: selected text is added to `operator_noise`.

All actions write normal editable config data by creating a new
`nlp_config_revisions` row. New domain signals get `weights.signals[type] = 0`
so rule discovery is visible in evidence but does not silently inflate lead
scores.

Rationale:

- The operator loop should be short: observe a false positive or missing entity,
  select the evidence in Review, and update settings without opening the full
  Settings Center first.
- Constructor changes must remain auditable through the same settings UI and
  deeplinks as manual settings edits.
- New positive signals are risky; defaulting their score weight to zero keeps
  matching and scoring as separate deliberate decisions.

## 2026-05-08: First Constructor Action Writes Operator Noise

The first active constructor action was `В шум` on the Review page. It sends the
selected source-text fragment to `POST /api/v1/settings/nlp/constructor/noise`.
The backend writes a new active PostgreSQL NLP config revision containing a
normal editable domain signal:

- `type`: `operator_noise`;
- `label`: `Операторский шум`;
- exact phrase tokens built from the selected fragment;
- signal weight `-50` when the weight is absent;
- membership in `noise_signal_types` and `lead_veto_signal_types`;
- membership in the hard-noise score cap, so manual noise can cap score to `0`;
- inclusion in the noise review lane and exclusion from non-noise lanes.

The endpoint returns the updated NLP settings snapshot so the frontend updates
its settings cache immediately.

Rationale:

- Operators need a fast way to convert observed false-positive text into
  deterministic settings without editing YAML or losing context.
- A noise constructor must create normal config data, not hidden code rules, so
  later audits and Settings UI links show exactly why future messages were
  vetoed.
- Only the selected phrase is added automatically; broader rule design still
  needs an explicit operator/config workflow.

## 2026-05-08: Analytics Is A Review Queue, Not Only A Report

Live Analytics must expose review state in the candidate list. The list API
returns the saved `message_reviews` row when it exists and accepts filters for
`review_status` (`reviewed` / `unreviewed`) and operator `verdict`. The UI shows
review chips in the table, defaults to the unreviewed queue, and uses human
labels for common review lanes.

Review links include a URL-encoded `return` hash containing the current
Analytics filters, selected run, and pagination offset. Returning from
`#/analytics/review/{source_message_id}` should bring the operator back to the
same queue context instead of a fresh Analytics page.

Review records include structured `tags` in addition to free comments. Tags
represent repeatable calibration reasons such as equipment-only, DIY, sale,
weak context, false alias, or missing rule. The Review page can save and then
open the next candidate from the same return hash; this is a frontend queue
workflow over the existing list API, not a second queue source of truth.

Rationale:

- The operator workflow is queue processing: new candidates, reviewed items,
  false positives, and uncertain messages must be separable without manual text
  filters.
- A dedicated Review page is still correct, but it must not make the operator
  lose the working slice they were reviewing.
- Review verdicts are ground truth for calibration, so they should be visible
  in the scan table immediately after saving.
- Structured tags make false-positive analysis queryable later; comments alone
  are too hard to aggregate.
- Hash URLs are the current SPA routing contract; preserving filters in the URL
  keeps browser back/forward and copyable links useful without introducing a
  new router dependency.

## 2026-05-08: Telegram Runtime Protects Cursors And Notification Idempotency

Telegram input settings are split conceptually into editable fields and runtime
state. Ordinary settings saves update account/source form fields, but preserve
resolved chat ids, source cursors, last errors, authorization metadata, and
FloodWait cooldowns for unchanged sources/accounts. Changing a source identity
resets the cursor deliberately.

The userbot creates an enrichment job before saving a source message, but that
job starts with a blocked `enrichment_task_outbox` row. The
`telegram_source_messages` insert activates the task outbox row to `pending` in
the same transaction, then the app may publish immediately through the
dispatcher path. That ordering prevents the worker from completing before
Telegram source context exists and keeps publish failures retryable. If a
concurrent ingester loses the unique source-message insert, it discards the
unpublished enrichment job instead of leaving a queued job that will never be
published.

The enrichment worker claims jobs with a conditional update from `queued` to
`running`. Celery redelivery or duplicate task publication cannot rerun a job
that is already running, completed, or failed.

Notification outbox rows created from Telegram source messages carry
`source_message_id` and `enrichment_job_id`. `(source_message_id, route_id)` is
unique, so worker redelivery cannot enqueue the same route notification twice.
The dispatcher claims rows by moving them to `sending` with `claimed_at` through
`FOR UPDATE SKIP LOCKED`; stale claims can be picked up again after timeout.
Rows claimed in a flush cycle but not sent because a partial batch is not due
are released back to `pending` immediately.

Telegram source cursors are monotonic. The listener sends the maximum seen
message id per source, and the PostgreSQL update uses `greatest(existing,
incoming)` so out-of-order live callbacks cannot move `last_message_id`
backwards.

Rationale:

- Cursors are runtime safety state; clearing them through a normal settings save
  can silently skip channel messages.
- A completed enrichment without source context creates an invisible lost
  notification.
- Telegram sends need at-least-once processing internally but at-most-once
  enqueueing per source message and route.
- Non-due partial notification batches should wait as `pending`, not as
  artificially claimed `sending` rows.
- Telegram message delivery order is not a cursor guarantee; cursor state must
  be protected at both application and persistence boundaries.

## 2026-05-08: Lead Score And Auto-Lead Verdict Are Separate

The deterministic score remains an additive explanation of matched facts and
domain signals. The auto-lead verdict is now additionally guarded by
`lead_scoring.lead_veto_signal_types`: when a configured veto noise signal is
found, the system keeps the score and score reasons visible, but returns
`is_lead=false` and `temperature=none`.

The bootstrap config treats clear supply/sale/equipment-only/price-only/ordinary
household contexts as veto signals. It also splits research/value questions into
`research_warm` instead of `direct_pur_lead`; the direct lane now requires a PUR
domain plus active customer/provider/installation evidence.

Rationale:

- A vendor or device alias can legitimately add domain evidence, but a sale,
  self-pickup, DIY, or ordinary non-smart context should not produce automatic
  Telegram lead notifications just because the additive score is high.
- Operators still need the high score and reasons to calibrate rules, so the
  system should not hide the evidence by clamping score to zero.
- Research questions are useful warm signals, but mixing them with direct
  contractor/order requests makes notification and review queues noisy.

## 2026-05-09: Hard Noise Can Cap Lead Score

Lead scoring now supports configurable `lead_scoring.score_caps`. A cap matches
configured signal, fact, reason, or noise types and limits the final score to
`max_score`. The scorer records the cap as a synthetic `score_cap` reason with a
negative adjustment, so the operator still sees the original positive evidence
and the exact reason the final score was reduced.

The bootstrap config uses `hard_noise` with `max_score: 0` for explicit
supply/sale/equipment-only/price-only/ordinary-household noise. Operator noise
is connected to the same cap by the active-DB migration/constructor once the
operator rule exists. The broad `модуль управления` relay alias was removed
because it misclassified generic video software license text such as DSS
parking management modules as smart-home automation.

Rationale:

- Veto alone stopped notifications but still left obvious noise with hot-looking
  scores in analytics.
- Score caps keep the review queue closer to operator intuition while preserving
  an auditable `score_cap` adjustment row.
- Overbroad alias spellings should be removed from dictionaries instead of
  compensated by code.

## 2026-05-09: Video Device Aliases Are Domain Evidence, Not Automation Evidence

`camera` and `nvr_dvr` device aliases now emit the specific fact
`video_device` instead of broad `automation_component` and `controlled_device`
facts. The `video_surveillance` signal weight is below the lead threshold, so a
single word like `камера` can explain the domain but cannot by itself become a
lead or place the message into the smart-home solution area.

Rationale:

- `controlled_device` feeds the smart-home solution area, so using it for any
  camera made video-only fragments look like smart-home automation.
- `automation_component` and `controlled_device` add score reasons; attaching
  both to generic camera aliases overheated sparse messages.
- Direct video-surveillance leads should be detected through domain plus intent:
  order/provider search, installation, consultation, customer request, project
  context, or similar evidence.

## 2026-05-09: Domain Signals Depend On Facts, Not Alias Catalogs

Alias matches now emit identity facts named `alias:<catalog>:<key>`. Domain
signals in the default config use `match.facts` and no longer use
`match.aliases`. For example, `devices.camera` emits `alias:devices:camera` and
`video_device`; `video_surveillance` depends on those facts and is emitted with
`source=fact_dependency`.

The API and config loader reject new direct `match.aliases` dependencies.
Existing active revisions are migrated by `0021_signal_fact_dependencies`; any
manual config must use `match.facts` only.

Rationale:

- The operator mental model is one pipeline: text -> dictionaries/rules -> facts
  -> domain signals -> lead scoring.
- Direct `dictionary -> signal` links made the UI hard to explain and hid which
  intermediate evidence actually caused a signal.
- Identity facts preserve exact alias-key dependencies without broadening facts
  such as `vendor`, `software`, or `controlled_device`.

## 2026-05-09: Enrichment Evidence Has A Visual Chain

The operator UI now shows a visual evidence chain in Testing and expanded
Analytics. The chain is derived from the same enrichment result and lead
assessment that feed the detailed tables:
text fragment -> dictionary or rule -> fact -> domain signal -> score
contribution.

Rationale:

- The user needs to see the causal path while analyzing a message, not only
  read long tables.
- The UI must remain an explanation layer: it reconstructs links from returned
  spans, source types, matched texts, and score reasons, but does not run a
  second classifier.
- Every node that can map to a setting reuses the existing modal/deeplink
  behavior, so visual inspection and configuration audit stay connected.

## 2026-05-09: Operator Reviews Drive The First Eval Loop

Use saved `message_reviews` as the first ground-truth source for deterministic
lead-quality evaluation. The backend CLI `app.cli.eval_reviews` compares
operator verdicts with persisted `lead_assessment.is_lead` and reports
TP/FP/TN/FN, precision, recall, specificity, accuracy, F1, verdict counts, and
false-positive/false-negative examples.

Verdict mapping:

- `lead` is positive ground truth.
- `not_lead` and `noise` are negative ground truth.
- `uncertain` is excluded from the confusion matrix.

Rationale:

- Rule and weight tuning needs measured feedback, not only individual examples.
- Review labels already live in PostgreSQL and are separate from deterministic
  enrichment output, so they can evaluate the classifier without rewriting
  historical evidence.
- A small CLI is enough while the labeled set is small; the UI can surface the
  same metrics later after the workflow stabilizes.

Update:

- The report logic now lives in the application layer and is reused by both the
  CLI and `GET /api/v1/analytics/review-eval`.
- The Analytics section surfaces it on a separate `Качество ревью` page as
  `Качество по ревью`, with reviewed/evaluated counts,
  precision/recall/F1/accuracy, FP/FN counts, and links from examples to the
  full Review page. This keeps the candidate review queue from becoming a
  mixed dashboard.

## 2026-05-09: Analytics Is Split Into Focused Internal Pages

The Analytics section had become overloaded after adding aggregate blocks,
candidate filters/table, expanded evidence, and review-quality metrics to the
same screen. It now has internal pages:

- `Кандидаты` as the default operational queue.
- `Обзор` for KPIs and aggregate distributions.
- `Качество ревью` for eval metrics and FP/FN examples.

Existing deeplinks remain stable: `#/analytics/message/{id}` still opens the
candidate context, and `#/analytics/review/{id}` still opens the dedicated
Review page.

Rationale:

- Operators reviewing messages need the queue first, without calibration panels
  pushing it down.
- Aggregate analytics and eval quality are different tasks and should not
  compete with the review workflow.
- Keeping the pages inside the same Analytics section preserves shared run
  selection, filters, and existing links while reducing visual load.

## 2026-05-09: Bare IR/ИК Does Not Emit High-Level Domain Signals

Short aliases such as `ИК` are too ambiguous to directly trigger PUR domain
signals. The `infrared` protocol catalog no longer includes bare `IR`/`ИК` or
the device phrase `инфракрасный пульт`, and `protocol_gateway` /
`climate_automation` no longer depend directly on `alias:protocols:infrared` or
`alias:devices:ir_remote`.

Rationale:

- A single short token `ИК` was producing both `Протоколы / шлюзы / интеграции`
  and `Автоматизация климата`, which inflated score and created a false lead.
- High-level signals should come from sufficiently specific facts. For climate,
  the config keeps contextual device aliases such as `пульт для кондиционера`
  under climate equipment instead of using a bare infrared protocol fact.
- IR remotes can still be represented as devices, but they should not by
  themselves imply a gateway/integration or climate-automation need.

## 2026-05-09: Domain Evidence Without Intent Is Capped Below Lead

The default scoring config now includes `domain_without_intent`, a configurable
score cap with `max_score: 34`. It matches domain signals but is skipped when an
explicit intent signal is present: need, customer/provider search, installation,
consultation, solution selection, education, value question, implementation
intent, or hot-lead intent.

The cap keeps isolated domain evidence such as `Нептун`, `хаб`, `шайба`,
`кондиционер`, `умный дом`, or `умный дом от застройщика` out of automatic lead
status unless the surrounding message contains a request, question, need, or
action. Active DB migrations also clean stale config that made plain lighting
fixtures (`бра`, `треки`) behave like smart-lighting automation, narrow
developer-context matching to actual developer wording, and remove cross-domain
protocol dependencies such as `PoE -> gateway/video/power`.

Rationale:

- Dictionaries should enrich evidence; they should not turn a lone brand,
  device, protocol, or solution-area phrase into a Telegram lead notification.
- The additive score remains auditable: the cap appears as a `score_cap` reason
  with a negative adjustment instead of hiding the original matches.
- Signals remain useful for analytics, but auto-lead status now requires domain
  evidence plus explicit user intent.

## 2026-05-09: App Shell Should Not Own Feature UI

`frontend/src/App.tsx` remains the top-level shell for auth, theme, hash routing,
and cross-page state. Feature-heavy UI is split into focused modules. The first
large split moved Testing/enrichment rendering into
`frontend/src/enrichment/TestingWorkspace.tsx`, enrichment DTO types into
`frontend/src/enrichment/types.ts`, and settings target navigation helpers into
`frontend/src/settings/navigation.ts`.

Rationale:

- The app shell had grown past 6000 lines and mixed routing, runtime state,
  settings editors, Testing UI, and result explanation components.
- Keeping feature UI outside the shell makes future refactors safer and keeps
  `App.tsx` focused on composition.
- Shared target/hash helpers prevent deeplink behavior from being duplicated
  across Testing, Analytics, and Settings.

## 2026-05-08: Live Analytics Candidate Lists Are SQL-Backed

The live Telegram analytics run still uses PostgreSQL runtime tables as the
source of truth, but the main candidate list no longer loads every completed
enrichment into Python before filtering. The repository now applies score,
temperature, nested JSON evidence, source, date, review status, verdict, and
text filters in SQL and returns only the requested page.

Run counters for the virtual `Telegram live` run are also SQL-backed. Live
aggregates still parse completed enrichment JSON because they need top lists
from nested arrays, but they now include review status and verdict counts for
calibration.

Rationale:

- The operator table is the hot path and must stay responsive as Telegram
  history grows.
- PostgreSQL JSONB containment is enough for current deterministic NLP arrays;
  ClickHouse can wait until aggregate workloads outgrow this shape.
- Review-quality metrics should be visible in Analytics without adding a second
  analytics datastore.

## 2026-05-09: NLP Config V3 Replaces The Old Semantic Taxonomy

The default NLP/domain configuration is rewritten as config v3 without
preserving old semantic names as compatibility targets. The model now uses four
explicit layers:

- dictionaries emit alias identity facts and generic fact types;
- fact rules emit `intent_*`, `context_*`, `object_*`, `domain_*`, and
  `noise_*` facts;
- domain signals depend only on facts through `match.facts`;
- lead scoring maps v3 signal/fact types to score, solution areas, customer
  segments, caps, and review lanes.

Active PostgreSQL settings are migrated by `0026_config_v3_taxonomy` to replace
facts, signals, and lead scoring with the v3 bootstrap documents. Existing alias
catalogs remain in the active config so operator-curated spellings are not
discarded, and an existing `operator_noise` signal is carried into hard-noise
scoring if present.

Rationale:

- The previous model had accumulated mixed layers: the same setting could mean
  intent, fact, dictionary dependency, domain, or score reason.
- V3 makes the evidence chain auditable in the UI: dictionary/fact first,
  signal second, score third.
- Domain-only evidence is capped below lead, and intent without a PUR domain is
  capped below lead, so isolated words like `камера` or off-domain requests like
  "где заказать обычный стол" do not become automatic PUR leads.
