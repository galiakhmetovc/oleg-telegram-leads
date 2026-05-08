# Current State

## Active Work

- Build PUR Leads v2 from a clean scaffold.
- Keep v1 only as reference material.
- Use exported production-confirmed lead messages as seed examples for later design.
- Follow root `AGENTS.md` as the project working rules.
- First product slice: web text enrichment UI with FastAPI snapshots, SSE
  progress, Celery worker execution, PostgreSQL persistence, and configurable
  Natasha/Yargy NLP pipeline.
- Current dev UI is exposed through host Caddy at
  `https://secclaw.qlbc.ru:19443/`; `/api/*` and SSE are proxied to FastAPI.
- Dev UI/API are now protected by a simple signed-cookie login. Dev defaults are
  `admin / pur-dev-password`; `/health` remains open.
- The default page after login is Analytics. The previous "Обогащение" page is
  now named "Тестирование".
- Analytics now defaults to a virtual live run, `Telegram live`, computed from
  `telegram_source_messages`, `enrichment_jobs`, and `enrichment_results`.
  Migration `0008_runtime_analytics_cleanup` cleared old batch analytics rows in
  the dev database.
- Live Analytics candidate pagination and filters now run in PostgreSQL for the
  Telegram live run instead of loading all completed enrichments into Python.
  SQL filters cover score, temperature, signal, reason, solution area, customer
  segment, review lane, source channel, received date, review status, verdict,
  and text search. Live aggregates also include review status/verdict counts.
- Analytics rows include links to the source Telegram message when derivable,
  an internal analytics permalink, a "Ревью" action, and a "Проверить" action
  that opens the text in Testing and starts enrichment. Notification messages
  now append Telegram and app analytics links for Telegram-originated
  enrichments.
- Message review is stored separately from deterministic enrichment in
  `message_reviews`. The route `#/analytics/review/{source_message_id}` opens a
  full review workspace where the operator can mark `Лид`, `Не лид`,
  `Сомнительно`, or `Шум`, add a comment, inspect the same evidence as in
  Analytics, and select a text fragment for the future settings/entity
  constructor.
- Analytics candidate lists now include saved review state, show a review chip
  (`Без ревью`, `Лид`, `Не лид`, `Сомнительно`, `Шум`), and can filter by
  `review_status` and `verdict`. Review links carry a return URL with the
  current filters, run, and pagination offset, so the operator can return to the
  same queue context after opening a dedicated Review page.
- The default Analytics queue is now `Без ревью`. Review records store
  structured `tags` in addition to verdict/comment. The Review page supports
  verdict hotkeys `1/2/3/4`, `Ctrl+Enter` to save, `N` to save and open the next
  message from the same queue, quick tag chips, and a short "Почему сработало"
  summary before the detailed evidence tables.
- The UI now includes "Логи" and "Статус системы" tabs backed by durable
  runtime state and health counters. System Status distinguishes worker progress
  journal rows from Telegram messages visible in live Analytics.
- Runtime logs now have backend filtering by service, level, text, and time
  range, limit/offset pagination in the UI, and configurable retention caps for
  enrichment events and non-pending notification outbox rows so log-like tables
  do not grow without bound. Docker Compose also rotates per-service stdout logs
  at 10 MB x 5 files.
- The UI now includes "Проектная документация": a read-only file browser for
  repository markdown docs from `README.md`, `AGENTS.md`, `docs/`, `notes/`,
  and `state/`, served through an allowlisted backend API.
- Telegram FloodWait is treated as a persisted temporary rate limit on the
  userbot account. The userbot stores `cooldown_until` and skips Telegram
  read/resolve calls for that account until the timestamp expires, including
  after container restarts. Source chats stay in their previous non-error state
  and keep the wait reason in `last_error`. After cooldown expiration, recovery
  is soft-resumed with small delayed batches and a delay between source reads so
  the service does not burst through all chats at once.
- Telegram userbot listener now keeps running after a handled FloodWait or
  ordinary reconnectable exception instead of reading a stale/missing loop
  summary. Saving Telegram input settings preserves runtime cursor/error/
  cooldown state for unchanged sources and accounts, so ordinary settings edits
  do not reset `last_message_id`.
- Telegram runtime now guards high-water marks and queues more defensively:
  out-of-order live messages cannot move `last_message_id` backwards; PostgreSQL
  cursor writes use `greatest(existing, incoming)`; a duplicate source-message
  insert discards the losing unpublished enrichment job; and notification
  outbox rows claimed but not ready for a 5-minute partial flush are released
  back to `pending` immediately.
- Default NLP config now recognizes the smart-home automation lead case with
  customer intent, vendor, solution area, and electrical design context signals.
- Default NLP config also recognizes hot Zigbee installation requests with
  provider search, service location, automation components, and controlled devices.
- Default NLP config recognizes apartment video surveillance requests with
  provider search, consultation need, camera, wall mounting, and wiring outputs.
- Settings Center is available in the UI. NLP/domain settings are viewed,
  previewed, and saved as active PostgreSQL revisions; YAML files are bootstrap
  defaults only. Runtime/env settings are shown read-only.
- Settings Center now includes Telegram notification routing. Operators manage
  bots, chats, and routes separately: bots own masked tokens, chats own
  destination `chat_id` values, and routes choose bot+chat based on completed
  enrichment data such as lead verdict, score, temperature, review lane,
  solution areas, customer segments, signals, facts, reasons, and noise. Runtime
  enrichment jobs enqueue matched notifications into `notification_outbox`;
  `notification-dispatcher` sends Telegram bot messages in batches. Batch-runner
  does not send notifications and stays a testing/calibration tool.
- Settings Center now includes Telegram input/userbot settings. Operators manage
  userbot accounts with phone, Telegram app `api_id`/`api_hash`, masked session
  state, interactive login code, and source chats with `input_ref` and
  high-water mark status. The `userbot` service listens to configured source
  chats through Telethon live updates, does one bounded recovery read after
  startup, persists text messages in `telegram_source_messages`, and creates
  normal Celery-backed enrichment jobs. Legacy history polling remains available
  as an explicit diagnostic mode.
- Telegram input UI now explicitly explains that "Сохранить Telegram вход"
  persists both userbot accounts and source chats. Source-chat `draft` is a
  saved runtime state before userbot resolution, and the UI has "Обновить
  статус" to reread resolved chat ids and cursors from backend.
- Telegram notification delivery is batched by bot+chat under the Bot API
  `sendMessage` 4096-character limit. Full batches are sent immediately; partial
  batches flush when the oldest pending item is at least 5 minutes old.
- Telegram notification outbox rows for source messages are idempotent per
  `(source_message_id, route_id)`. The dispatcher atomically claims pending rows
  with status `sending`/`claimed_at`, so worker retries do not enqueue duplicate
  route notifications and parallel dispatchers do not send the same row.
- Default Telegram lead notifications now use a structured operator-readable
  template with score, review lane label, solution areas, customer segments,
  score reasons, text preview, and separate source/app links. Existing routes
  that still had the old default template are migrated to the new format.
- Telegram lead notifications are now queued only for enrichment jobs linked to
  `telegram_source_messages`. Manual Testing enrichments may reuse a live
  message's text, but they do not send duplicate Telegram alerts.
- The UI Help tab now documents current editable NLP settings: pipeline stages,
  exact and lemmatized matching, domain signals, facts, alias dictionaries, lead
  signal dependencies, scoring, thresholds, weights, solution areas, customer
  segments, intent/noise signals, and review lanes.
- Domain signals and facts now support editable `group` folders stored in NLP
  config revisions. Settings Center groups large rule lists by these folders,
  and Help explains how signal dependencies work.
- Brand/model spellings such as `Нептун`, `Нептуп`, `Neptun ProW`, and
  `Profi Wi-Fi` live only in alias catalogs. Domain signals keep semantic
  phrases and explicitly reference dictionaries through `match.aliases`; alias
  catalogs emit structured facts through `fact_types` and no longer carry
  `signal_types`.
- Settings rule editing now presents operator-facing matching modes: exact
  phrases and lemmatized phrases. Exact/semantic rules are edited with explicit
  add/edit/delete actions. New lemmatized phrases are built by the backend from
  operator-entered text and preserve `source_text` alongside generated lemmas.
- Rule matching no longer exposes `caseless` as an active mode. Exact phrases
  are literal lowercased matches for technical spellings such as `Wi-Fi`, `220v`,
  `Z-Wave`, and abbreviations; lemmatized phrases remain Yargy `normalized`
  rules. Old `caseless` config revisions are invalid and should be replaced,
  not adapted at runtime.
- A Help tab in the web UI explains exact versus lemmatized matching and when to
  use each mode.
- Settings Center now also exposes editable alias catalogs for `vendors`,
  `protocols`, `devices`, and `software`. These catalogs keep canonical names,
  Latin/Cyrillic/transliterated/mistyped aliases, alias type, and fact type
  links. Domain signal dictionary dependencies are edited on the signal rule
  itself.
- Alias matching is configurable in Settings Center under Pipeline. It ignores
  register via casefold and can normalize separators, `ё/е`, mixed
  Latin/Cyrillic confusable letters, and limited fuzzy edit distance with
  minimum alias length, long-alias distance, and explicit fuzzy exclusions.
- Alias matching now keeps the longest overlapping dictionary match and drops
  shorter nested spans, so full model/platform aliases such as `Нептуп ProW` or
  `Profi Wi-Fi` do not produce extra nested facts for `Нептуп` or `Wi-Fi`.
- Domain signal dependencies in Settings Center are no longer edited through
  mini-language text such as `vendors:neptun`. Operators add/remove dependency
  rows with buttons, select the alias catalog, choose concrete alias entries,
  and choose dependent fact types from existing facts and alias `fact_types`.
- Default NLP config includes a broad curated first pass for РФ/СНГ smart-home
  market terms: Яндекс/Сбер/Aqara/Xiaomi/Tuya/Sonoff/Rubetek/Livicom/Wiren Board,
  leak protection brands, CCTV/access vendors, Matter/Zigbee/Z-Wave/KNX/Wi-Fi/
  BLE/Modbus/MQTT/PoE protocols, common devices, and smart-home software such as
  Алиса, Home Assistant, Apple Home/HomeKit, Google Home, Smart Life, Aqara Home,
  Mi Home, eWeLink, Zigbee2MQTT, Node-RED, ioBroker, MajorDoMo, and video apps.
- Default NLP config recognizes the confirmed artifact lead about hiding a leak
  sensor in porcelain stoneware and documenting the solution on drawings/schemes.
- Enrichment results include `lead_assessment`: deterministic PUR lead verdict,
  score, temperature, solution areas, customer segments, reasons, and noise
  signals. Lead scoring thresholds, weights, and mappings are editable in the
  Settings Center and stored in PostgreSQL config revisions.
- Batch analytics candidates now include configurable review lanes. Lane rules
  live under `lead_scoring.review_lanes`, are visible/editable with lead scoring
  settings, are assigned during analytics import, and can be viewed/filtered in
  the analytics UI. Current bootstrap lanes split candidates into noise, direct
  PUR leads, project context, domain interest, off-domain demand, generic
  context, and other candidates.
- Enrichment overview now explains the deterministic result in operator terms:
  dictionary entities, facts, and domain signals include source and why text;
  lead score shows the arithmetic formula; solution areas, customer segments,
  and review lanes show the configured matched labels/groups. Score, category,
  review-lane, dictionary, fact, and signal tables use links wherever a setting
  can be identified.
- Enrichment facts/signals now carry structured `settings_refs` for the rule or
  alias row that produced them. The frontend turns these into separate settings
  detail pages such as `#/settings/aliases/devices/electric_curtain`; navigation
  stays inside the SPA, so the current input text/result context is preserved.
- Annotated source text converts backend Unicode code point ranges into browser
  UTF-16 ranges before slicing, so matches after emoji are highlighted on the
  intended fragment.
- Analytics candidate rows now expand into an enrichment-style review view with
  highlighted message fragments, lead temperature/score, review lane, solution
  areas, customer segments, intent/noise signals, score reasons, domain signals,
  and facts.
- Expanded Analytics evidence now uses the same settings-link model as the
  Testing overview: facts, domain signals, score reasons, taxonomy categories,
  alias dependencies, weights, and review lanes link to the corresponding
  Settings detail target. Left click opens the quick settings preview modal;
  Ctrl/Cmd or middle click follows the full settings deeplink.
- Analytics highlighting now prefers backend span ranges and converts Python
  Unicode code point offsets into browser UTF-16 offsets before slicing. Text
  search remains only as a fallback for old/live rows that do not carry ranges.
- Empty Analytics copy is Telegram-live aware and no longer tells the operator
  that only a batch-runner import can populate the screen.
- Default NLP config recognizes the developer-provided smart-home apartment
  modification lead: apartments with smart home from a developer, socket/switch
  changes, electrical scheme changes, and warranty risk.
- Default NLP config recognizes early research/design leads where the author asks
  which useful smart-home systems to implement in a project and where to study
  the topic.
- Default NLP config recognizes value-evaluation smart-home leads where customers
  ask whether they need a smart home, who it is for, what benefits it gives, and
  mention family apartment context, budget constraints, climate, or lighting
  scenarios.
- Default NLP config recognizes the latest follow-up PUR lead examples: child
  room smart speaker/audio wiring as a warm lead, leak sensor power/output
  questions, commercial intercom/access-control recovery, white-box smart-home
  design planning, security technical projects with video/access/alarm systems,
  nanny camera contractor search, and Wi-Fi electric curtain control.
- Default NLP config recognizes the latest motion-lighting, Zigbee/Yandex relay,
  and HVAC/design leads: timed night lighting by motion sensor with independent
  wall-light control, smart relay modules for lights/tracks connected to Alice,
  and O'Climate/Orac static-pressure chambers for channel air conditioning
  without misclassifying them as video surveillance.
- Default NLP config recognizes Neptun/Нептун water leak monitoring leads,
  including the typo `Нептуп`, ProW/Profi product mentions, wired leak sensors,
  sensor-trigger monitoring, and smartphone information output.
- Default lead scoring now separates additive score from auto-lead verdict:
  configured `lead_veto_signal_types` keep the score visible but force
  `is_lead=false` and `temperature=none` for explicit supply/sale/DIY/price-only
  or ordinary household noise. Research/value smart-home questions now route to
  `research_warm` instead of `direct_pur_lead`.
- Review lane matching is centralized in `app.application.review_lanes`. The
  deterministic scorer and analytics import/list code use the same priority,
  exclusion, score/temperature, and match-group logic, including matched group
  indexes for explanations.
- Dev PostgreSQL active NLP config has been refreshed through revision 27. The `need`
  signal no longer stores Russian forms such as `нужно`, `нужна`, `нужен` as
  exact phrases; they are represented as lemmatized phrase rules with preserved
  operator source text. Revision 16 also includes the Neptun water leak
  monitoring lead calibration, and revision 19 includes the smart-home alias
  catalogs plus calibrated semantic signal/fact weights. Revision 20 was
  reseeded from current bootstrap YAML after dropping `caseless` compatibility;
  revision 22 adds rule-group folders to the active PostgreSQL config; revision
  23 removes direct Neptun/ProW/Profi brand/model rules so those spellings are
  emitted only through alias catalogs; revision 24 migrates alias
  `signal_types` into explicit `signals[].match.aliases` dependencies and
  removes signal outputs from alias dictionaries; revision 26 stores the
  configurable `pipeline.alias_matching` section, removes duplicated literal
  alias spellings across catalogs, lowers generic off-domain demand weights, and
  keeps PUR lead examples passing while avoiding ordinary non-PUR provider-search
  messages. Revision 27 adds lead-veto noise signals, an
  `ordinary_household_system` noise signal, and the `research_warm` review lane.
- `RussianTextEnricher` now precompiles Yargy parsers once per enricher
  instance and shares one Yargy `MorphTokenizer` across compiled rules instead
  of creating a separate `pymorphy2` analyzer for every parser. This keeps
  default-config rule tests around hundreds of MB instead of multi-GB RSS. A
  local batch CLI can write full enrichment JSONL for exported messages without
  creating API/Celery jobs per message.
- Benchmark on the first 300 designer-channel messages with full enrichment:
  300 processed, 0 failed, 6 leads, 65.31 seconds, 4.59 messages/sec, peak RSS
  about 1.34 GB, output 1.9 MB. Linear estimate for 528953 messages on one
  process is about 32 hours and about 3.24 GiB JSONL output.
- Agent verification should avoid Caddy smoke checks unless explicitly requested;
  use backend tests and direct service/container checks by default.
- Backend `uv run pytest -q` skips slow full-Natasha NLP smoke tests by default.
  Run them explicitly with `uv run pytest --runslow ...` when validating the
  full morph/syntax/NER path.

## Blockers

- Product flows for v2 are not specified yet.
- Host disk pressure is high: after clearing npm/uv caches, `/` still had about
  2.3 GB free and 98% usage on 2026-05-07.

## Next Steps

1. Continue high-priority audit fixes: Telegram ingestion idempotency, outbox
   flush timing, cursor monotonicity, and SQL-backed live analytics pagination.
2. Review live `research_warm`, `noise`, and `direct_pur_lead` candidates after
   revision 27 to tune false positives with operator verdicts.
3. Promote confirmed production examples into a curated eval/golden dataset
   after deciding what text can be committed versus kept in ignored artifacts.
4. Keep an eye on host disk usage before larger dependency/model downloads.
