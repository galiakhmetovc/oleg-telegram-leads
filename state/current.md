# Current State

## Handoff 2026-05-14

This is the current continuation point for the next agent/session.

### Lead Handling Bot Update 2026-05-15

- Added Telegram lead handling persistence: `lead_handlings`,
  `lead_handling_events`, and `lead_bot_sessions` via Alembic revision
  `0035_lead_handling_bot`.
- Added notification route `delivery_mode`: existing/omitted routes default to
  `batched`; `interactive` routes send one Telegram card per lead with buttons
  `Взял` and `Не лид`.
- Added `lead-bot` Docker Compose service. It polls Telegram Bot API updates for
  enabled bots used by interactive notification routes. Poll offsets are stored
  in `lead_bot_sessions` with reserved `telegram_user_id="__offset__"`.
- Group button behavior:
  - `Взял` claims the lead and edits the sales group card.
  - `Не лид` writes a `not_lead` review and cancels unsent notifications for
    that source message.
- Private bot behavior:
  - Operators can send `/start`, open `Мои лиды`, open their own lead cards,
    change status (`Написал`, `Ждет`, `Закрыт`), and add one-message comments.
  - Private open/status/comment actions enforce ownership and do not reveal
    another operator's lead text.
  - Operators must start the bot privately (`/start`) before expecting Telegram
    private bot UX to be discoverable.
- Runtime status after deploy:
  - `docker compose run --rm migrate` upgraded
    `0034_llm_settings_queue -> 0035_lead_handling_bot`.
  - `docker compose up -d backend notification-dispatcher lead-bot` started
    `lead-bot`.
  - Runtime notification route `hot_leads` is now switched to
    `delivery_mode="interactive"`.
  - `lead-bot` is running and polling Telegram Bot API; future logs suppress
    `httpx/httpcore` INFO output so bot tokens are not printed in request URLs.
- Verification:
  - `uv run pytest tests/test_notification_outbox.py tests/test_interactive_notification_outbox.py tests/test_notification_settings_api.py tests/test_worker_notifications.py tests/test_lead_handling_repository.py tests/test_lead_handling_use_cases.py tests/test_telegram_bot_worker.py tests/test_telegram_sender.py -q`
    -> `45 passed`.
  - `uv run ruff check app tests/test_notification_outbox.py tests/test_interactive_notification_outbox.py tests/test_notification_settings_api.py tests/test_lead_handling_repository.py tests/test_lead_handling_use_cases.py tests/test_telegram_bot_worker.py tests/test_telegram_sender.py`
    -> passed.
  - `docker compose config >/tmp/pur-leads-compose.yml` -> passed.
  - `uv run mypy app` still fails in pre-existing LLM verification/LLM
    notification code paths, not in the lead-bot files.

### Workspace And Runtime

- Work in the git worktree:
  `/home/admin/.config/superpowers/worktrees/oleg-telegram-leads/v2-from-scratch`.
- The live dev UI is exposed at `https://secclaw.qlbc.ru:19443/`.
- Docker Compose is the active runtime. Main services: `backend`, `frontend`,
  `postgres`, `redis`, `worker`, `llm-worker`, `enrichment-dispatcher`,
  `notification-dispatcher`, `userbot`, `lead-bot`.
- The worktree is dirty with many intentional product changes and untracked
  migrations/modules. Do not reset or revert unrelated files.
- Current operator flow is production/dev live, not local-only experiments.
  The user expects changes to affect the running app at the public URL.

### Current System State

Last verified on 2026-05-14 after adding the latest approved sources:

- Telegram source chat rows: `74`.
- Enabled Telegram source chats: `73`.
- Telegram source chats actually present in the userbot dialogs: `63`.
- Missing/pending/private sources: `10`.
- Redis queue lengths: `celery=0`, `llm=0`.
- Enrichment jobs: all `completed`, last observed total `6226`.
- Userbot logs after restart showed only a normal Telegram connection, no
  FloodWait or captcha warning.
- One enrichment worker is enough for the current load. Do not add a second
  enrichment worker unless there is real backlog such as `celery > 50`, queued
  enrichment jobs stuck for minutes, or visible delay from Telegram message to
  Analytics.

Missing/pending/private Telegram sources at the last check:

- `Design Wall Street | Чат` -> `https://t.me/designwallstreet`
- `Home Assistant / SprutAI` -> `https://t.me/SprutAI_HomeAssistant`
- `smarch архитекторы дизайнеры проектировщики инженеры конструкторы художники чат`
  -> `https://t.me/sm_arch001`
- `Дизайнеры интерьера | chat` -> `https://t.me/interiordesignchat`
- `Заказы по ремонту квартир чат` -> `https://t.me/zakazi_remont_kvartir2`
- `СОЮЗ МОНТАЖНИКОВ` -> `https://t.me/souzmo`
- `Слаботочка - что и почем чат` -> `https://t.me/leprice_chat`
- `Строители Москвы | чат` -> `https://t.me/stroiteli_moskva`
- `Строительство Москва Чат` -> `https://t.me/stroitelimsk4`
- `Электрика. Чат для коллег` -> `https://t.me/electricianclub`

Interpretation:

- Several of these are likely pending moderation after `JOIN_REQUEST_SENT`.
- `Home Assistant / SprutAI` and `СОЮЗ МОНТАЖНИКОВ` behaved as private or
  inaccessible in manual join attempts.
- Do not hammer this missing list. Recheck occasionally; if still missing,
  leave them as pending/private unless the user explicitly wants cleanup.

### Telegram Joining Procedure

The userbot receives live updates automatically only for dialogs it has joined.
The app settings remain necessary as the whitelist and metadata source:

- `telegram_source_chats` decides which dialogs the listener should subscribe
  to and gives each message a stable `source_chat_id`.
- Being in a Telegram dialog alone is not enough; if the chat is not in settings
  it is ignored by the app listener.
- Adding a source should be: resolve candidate -> insert source setting with
  `telegram_chat_id` -> join through userbot account -> restart or wait for
  userbot settings reload.

When joining chats:

- Join one by one.
- Use long pauses around 180-260 seconds between successful joins.
- After each join, inspect recent chat messages and recent DMs for captcha-like
  text such as `капча`, `captcha`, `не бот`, `докажите`, `пройдите проверку`,
  `verify human`, or button/verification language.
- Stop immediately on captcha or FloodWait and tell the user what happened.
- Do not solve captchas automatically and do not click verification buttons.
  The user solves them manually and then says `готово`/`продолжай`.
- Do not run parallel Telethon join/search commands while a join script is
  active.

Recently added and successfully joined sources:

- `Aqara.ru | Чат` -> `https://t.me/aqararuchat`
- `Проектировщики и Строители Россия` -> `https://t.me/stroy_proekt_chat`
- `Чат взаимопомощи: проектировщики` -> `https://t.me/help_club_engineers`
- `Чат Строительство домов| Москва и МО Chat` -> `https://t.me/landhausartchat`
- `HOMESTYLER | Чат дизайнеров интерьера` -> `https://t.me/homestyler_chat`
- `Всем подряд - Субподряды. Строительные заказы для всех`
  -> `https://t.me/vsem_podryad`
- `LAB | REMONT Чубарова Николая (ремонт квартир, дизайн-проект) Chat`
  -> `https://t.me/chat_labremont`
- `Чат ЭЛЕКТРИКА | САНТЕХНИКА | ОТОПЛЕНИЕ`
  -> `https://t.me/c_electrika_santehnika_otoplenie`
- `Электрика | Умный дом | Чат`
  -> `https://t.me/smarthomekrum`
- `чат Videsign | Дизайн интерьера, электрика, умный дом`
  -> `https://t.me/vi_desssign`
- `ПТО | Проектировщики | Сметчики | Инженеры`
  -> `https://t.me/chat_injeneri_pto_ovik`
- Earlier successful additions included `ЗАКАЗЫ ПО РЕМОНТУ КВАРТИР И ВАННЫХ
  КОМНАТ`, `Чат Видеонаблюдение в Сочи, WiFi, СКУД, Сети`, `Чат архитекторы |
  дизайнеры | проектировщики`, and `Чат. Стройка и ремонт Москва`.

Latest Telegram expansion notes:

- The user manually joined the latest approved batch. Six sources were added to
  `telegram_source_chats` with their current latest message id as the cursor, so
  old history is not imported.
- `@stroitel_birja` was in the user's joined list, but a dialogs check did not
  show it in the userbot account. It was not added to source settings. Recheck
  the dialog before adding it.
- Captcha/DM check found `AqaraChatGuardBot` saying the Aqara chat verification
  was passed. Older `arch_chat_check_bot` verification messages were still
  visible in recent DMs but were not from the latest batch.

### Telegram Live Architecture

Current intended model:

- `userbot` runs in live listen mode with Telethon `NewMessage` updates.
- It should not poll history for every configured chat in normal operation.
- The live listener resolves configured sources and subscribes to updates.
- `telegram_userbot_worker.py` supports `--settings-reload-interval`; Compose
  sets `${TELEGRAM_SETTINGS_RELOAD_INTERVAL:-600}`.
- After adding many new chats, restarting `userbot` is acceptable to subscribe
  immediately. Recent restarts were clean.

Important code paths:

- `backend/app/application/telegram_ingestion/live_service.py`
- `backend/app/cli/telegram_userbot_worker.py`
- `backend/app/infrastructure/telegram/userbot_history.py`
- `backend/app/infrastructure/persistence/telegram_ingestion_repository.py`

### LLM Verification State

LLM verification is an additional final-stage checker, not a replacement for
deterministic rules.

Current product direction:

- Cold and warm leads route to LLM.
- LLM-verified cold/warm leads can enqueue Telegram notifications.
- LLM notification confidence threshold is `>= 0.5`.
- Do not force-send warm notifications manually; let the dispatcher send them.
- LLM prompt must stay compact and Russian-operator-facing:
  send the message text, concise Russian labels for current signals/facts/
  dictionaries, and compact golden examples. Do not dump internal UUIDs or full
  alias catalog JSON into the prompt.
- The user rejected verbose `catalog:key`/UUID-heavy prompts. Labels should be
  human-readable Russian where possible.

Important code paths:

- `backend/app/application/llm_verification/`
- `backend/app/infrastructure/persistence/llm_verification_repository.py`
- `backend/app/infrastructure/llm/ollama_client.py`
- `backend/app/api/llm_settings.py`
- `backend/app/api/llm_verifications.py`
- `frontend/src/llm/`
- `backend/app/application/notifications/use_cases.py`
- `backend/app/worker/tasks.py`

### NLP And Operator Rules

Approved conceptual model:

- `alias` handles canonicalization and known names/spellings.
- `fact` handles meaning.
- `signal` handles inference/lead logic.
- `span` and `sentence` are coordinates.
- `relations` connect facts.
- `same_span` and `same_sentence` are service/computed relations, usually not
  manually configured.
- `intent_object`, `located_at`, and `negates` are the small explicit relation
  set when needed.

Text ownership rule:

- A word/phrase should live in one clear owner.
- Market spellings and variants belong in dictionaries/alias catalogs.
- Fact rules own semantic exact/lemmatized phrases.
- Signals should not own raw text phrases; signals depend on facts.
- Dictionaries support exact/light fuzzy alias matching, but not lemmatized
  semantic search. Lemmatized matching belongs in fact rules.
- Example: `домофон` and `домофоны` should not both be duplicated in a
  dictionary if a lemmatized fact rule already covers the semantic form.

Span behavior:

- Longer spans should intercept shorter spans when they overlap.
- Example: in `умный дом у себя дома и на даче`, `умный дом` should produce
  the smart-home domain/object fact; standalone `дома` and `даче` can produce
  location/object context without stealing the `дом` inside `умный дом`.

Operator documentation already exists and should stay current:

- `docs/how-to-work-in-system.md`
- `docs/operator-golden-rules.md`
- `docs/llm-verifier.md`
- `docs/architecture.md`
- `docs/decisions.md`

### UI State

Current top-level UI includes:

- Analytics
- Golden
- Testing
- Settings
- Operator guide / `Как работать`
- LLM
- Runtime/status/logs/docs pages

Configurator was intentionally hidden from normal navigation because the user
said it is not currently useful. If touching routing/navigation, keep this in
mind: hiding the tab was requested, not necessarily disabling deep links.

Important UI changes already made:

- Normal URLs/routes were added so pages can be shared.
- Golden examples can be deleted.
- Dictionaries are collapsed by default.
- Analytics defaults to newer messages first.
- LLM pages/settings show routing and context information.
- LLM raw JSON should be formatted/readable.
- Settings LLM routes should use dropdowns with human-readable names, not raw
  ID text fields.

### Verification Commands Used Recently

Useful checks:

```bash
docker compose ps
docker compose logs --since=90s userbot
docker compose exec -T redis sh -lc 'printf "celery="; redis-cli llen celery; printf "llm="; redis-cli llen llm'
docker compose exec -T postgres psql -U pur_leads -d pur_leads_v2 -c "select status, count(*) from enrichment_jobs group by status order by status;"
```

Backend tests that passed after recent architecture changes:

```bash
cd backend && uv run pytest tests/test_telegram_live_sources.py tests/test_telegram_userbot_worker_cli.py -q
cd backend && uv run pytest tests/test_notification_outbox.py tests/test_worker_notifications.py::test_worker_queues_llm_notification_after_completed_run -q
```

### Next Reasonable Steps

If the next session continues chat expansion:

1. Search for more Telegram candidates without adding or joining.
2. Exclude sources already in `telegram_source_chats`.
3. Inspect recent messages for live useful traffic versus spam/ads/USDT/
   vacancies.
4. Show the candidate list to the user first.
5. Only after approval, add a small batch to settings and join one by one with
   captcha/FloodWait checks.

If the next session works on product quality:

1. Review new incoming Analytics messages from the newly joined chats.
2. Mark false positives/false negatives in Review/Golden.
3. Update dictionaries/facts/signals according to the approved ownership rules.
4. Keep operator docs updated after any rule/process change.

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
  Analytics, and select a text fragment for the settings/entity constructor.
- Review constructor action `В шум` is now active. It sends the selected
  fragment to `POST /api/v1/settings/nlp/constructor/noise`, creates or updates
  an editable `operator_noise_fact` fact and connects the existing
  `operator_noise` signal through `match.facts`, keeps the signal in noise/veto
  scoring lists and review-lane exclusions, and refreshes the frontend settings
  cache from the response.
- Review constructor actions `В словарь` and `В факт` are active. They open
  target-selection dialogs and write selected text to exactly one alias catalog
  or fact rule through PostgreSQL NLP revisions. Signals do not own text
  phrases; they depend on facts through `match.facts`, so traces stay
  fragment -> dictionary/rule -> fact -> signal -> score.
- NLP/domain settings are now config v3. The active PostgreSQL config revision
  is `31` from migration `0026_config_v3_taxonomy`; old semantic names are not
  compatibility targets. The current chain is: dictionaries emit alias facts,
  fact rules emit `intent_*`/`context_*`/`object_*`/`domain_*`/`noise_*` facts,
  domain signals depend on facts through `match.facts`, and lead scoring maps
  v3 types into score, solution areas, segments, caps, and review lanes.
- Frontend review-constructor UI code now lives in
  `frontend/src/analytics/ReviewConstructor.tsx`, separate from the main
  Analytics page. `AnalyticsPage.tsx` keeps page state, review flow, and
  candidate tables; constructor dialogs and constructor API payloads are owned
  by the feature module. Shared analytics/review UI contracts live in
  `frontend/src/analytics/types.ts`. Candidate evidence rendering, settings
  links, highlighting, and candidate label formatting live in
  `frontend/src/analytics/CandidateEvidence.tsx`.
- Runtime operator pages for "Логи", "Статус системы", and "Проектная
  документация" now live in `frontend/src/runtime/RuntimePages.tsx` instead of
  the app shell.
- The Testing workspace was split out of `frontend/src/App.tsx` into
  `frontend/src/enrichment/TestingWorkspace.tsx`; shared enrichment DTO types
  live in `frontend/src/enrichment/types.ts`, and settings target hash/deeplink
  helpers live in `frontend/src/settings/navigation.ts`. `App.tsx` remains the
  top-level router/state shell.
- The Settings Center was split out of the app shell into
  `frontend/src/settings/SettingsCenter.tsx`. It owns the settings tabs,
  NLP rule editors, alias dictionaries, lead scoring editor, notification
  routing editor, Telegram input editor, settings target modal, and settings
  section routing helpers. Shared settings DTO types live in
  `frontend/src/settings/types.ts`; the settings help page lives in
  `frontend/src/settings/SettingsHelpPage.tsx`.
- Settings load is optimized for operator responsiveness: the app preloads the
  settings snapshot into an in-memory ref without forcing a full React state
  update on non-settings pages, NLP draft dirty-state no longer does full
  `JSON.stringify` comparisons on every render, collapsed settings accordions
  do not mount heavy editors until opened, and the backend reads active NLP
  revisions through the fast PostgreSQL path while caching bootstrap YAML for
  the rare seed case.
- The operator UI supports light and dark themes. The toggle lives in the top
  toolbar, applies MUI theme mode plus app CSS variables, and stores the
  operator-local preference in browser `localStorage`.
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
- Manual review now overlays the automatic lead status in Analytics. `Шум` and
  `Не лид` make the API/UI expose the message as non-lead while keeping the
  automatic score and evidence visible for audit; `Лид` can force a lead, and
  `Сомнительно` keeps the automatic verdict. Saving `Шум` or `Не лид` cancels
  unsent pending/sending Telegram notification outbox rows for that source
  message.
- Analytics is split into focused internal pages: `Кандидаты` is the default
  operator queue, `Обзор` contains KPIs and aggregate distributions, and
  `Качество ревью` contains the manual-review quality report. Existing
  `#/analytics/message/{id}` and `#/analytics/review/{id}` deeplinks remain
  stable.
- Bare `ИК`/`IR` is no longer treated as a protocol or climate automation
  signal. The active PostgreSQL NLP config was migrated in
  `0022_ir_signal_disambiguation`: `protocol_gateway` and `climate_automation`
  no longer depend directly on `alias:protocols:infrared` or
  `alias:devices:ir_remote`, while contextual climate aliases such as
  `пульт для кондиционера` remain under climate equipment.
- Operator reviews can now be evaluated in the Analytics UI and from the backend
  CLI with `uv run python -m app.cli.eval_reviews --format markdown|json`. The
  shared report reads `message_reviews` plus persisted enrichment results and
  computes TP/FP/TN/FN, precision, recall, specificity, accuracy, F1, verdict
  counts, and false-positive/false-negative examples. The web page
  `Качество ревью` calls `GET /api/v1/analytics/review-eval` and links FP/FN
  examples to the full Review page. Current dev DB has one reviewed `noise`
  row, and the eval reports it as a false positive with automatic `score=105`.
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
- The UI now includes "Golden": a separate panel for curated golden examples.
  Examples are stored in PostgreSQL table `golden_examples`, can be created
  manually or idempotently promoted from Analytics/Review messages, and run
  through the regular enrichment/SSE pipeline with the same explainability UI as
  Testing.
- Operator rules for using Golden as the rule-calibration loop are documented in
  `docs/operator-golden-rules.md`, including the example "я хочу установить
  умный дом у себя дома и на даче".
- The Configurator is now a Rule IDE rather than another dense settings form:
  the left explorer selects domain folders or rule layers, the central graph
  visualizes dictionary -> fact -> signal -> score chains, and the right panel
  combines compact selected-node editing with draft preview through
  `/api/v1/settings/nlp/preview`. `Advanced` links still open the full Settings
  Center deeplink for the selected signal, fact, or dictionary entity.
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
- Enrichment task publication now uses a PostgreSQL outbox. API/Testing jobs
  create pending `enrichment_task_outbox` rows; Telegram jobs create blocked
  rows that are activated when the source message insert commits. The
  `enrichment-dispatcher` service publishes pending rows to Celery/Redis and
  leaves broker failures retryable in PostgreSQL. The worker atomically claims
  only queued jobs, so Celery redelivery or duplicate task publication cannot
  rerun completed/failed enrichments.
- Enrichment jobs now record the claimed PostgreSQL NLP config revision
  (`nlp_config_revision_id` and `nlp_config_revision`) when the worker moves a
  job from `queued` to `running`. Workers resolve the active revision at claim
  time and cache compiled NLP pipelines by revision, so new settings revisions
  affect new jobs without a manual worker restart. System Status exposes the
  active config revision, latest worker-used revision, backend code version,
  and latest worker code version; dev Compose restarts the worker on Python
  source changes through `watchfiles`.
- The operator UI now makes config freshness visible: Settings Center shows the
  active NLP revision and, after saving NLP settings, links directly to Golden
  checks; Testing/Golden job status shows the NLP revision used by the completed
  job; System Status has a dedicated "Свежесть правил и кода" block for active
  revision, latest worker revision, backend code version, and worker code
  version.
- The operator UI now includes a top-level "Конфигуратор" page. It is a
  frontend workspace over the active PostgreSQL NLP settings revision: left
  navigation by domain groups and rule layers, a central selected entity editor,
  and a dependency/impact inspector for the chain dictionaries -> facts ->
  domain signals -> lead scoring. The first slice supports simple edits for
  rule labels/groups/confidence/weights, dictionary aliases/fact outputs, and
  lead thresholds, then saves the full NLP draft through the existing
  `PUT /api/v1/settings/nlp` revision endpoint. Settings Center remains the
  advanced editor for full CRUD and detailed rule phrase management.
- Frontend Vitest now uses verbose reporting and a 30-second test timeout. The
  full `App.test.tsx` suite is currently a heavy integration suite: it passes,
  but takes roughly 2.5 minutes on the dev host and should be split/optimized in
  a future frontend test cleanup.
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
  `Profi Wi-Fi` live only in alias catalogs. Domain signals keep no text
  phrases and reference dictionaries only through facts such as
  `alias:vendors:neptun` in `match.facts`; alias catalogs emit structured facts
  through `fact_types` and no longer carry `signal_types`.
- Text ownership validation now uses runtime-equivalent keys for separators and
  Latin/Cyrillic confusables, treats alias `canonical` as display-only, and
  rejects dangling `match.facts` / lead-scoring fact references. Migration
  `0031_text_owner_config_repair` repairs active PostgreSQL configs by moving
  legacy signal text into facts and removing stale fact references.
- Settings rule editing now presents operator-facing matching modes: exact
  phrases and lemmatized phrases. Exact/semantic rules are edited with explicit
  add/edit/delete actions. New lemmatized phrases are built by the backend from
  operator-entered text and preserve `source_text` alongside generated lemmas.
- Rule matching no longer exposes `caseless` as an active mode. Exact phrases
  are lowercased token-sequence matches for non-catalog technical spellings such
  as `220v` and abbreviations; market spellings such as `Wi-Fi` stay in alias
  catalogs. Non-word separators such as `@`, emoji, punctuation, and newlines
  may appear between exact-phrase tokens. Lemmatized phrases remain Yargy
  `normalized` rules. Old `caseless` config revisions are invalid and should be
  replaced, not adapted at runtime.
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
  mini-language text such as `vendors:neptun` and no longer use direct alias
  dependencies. Operators add/remove fact-dependency rows with buttons and
  choose from Yargy fact types, alias `fact_types`, and concrete alias identity
  facts like `alias:vendors:neptun`.
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
- Testing and expanded Analytics now include a visual evidence chain. It shows
  how each matched text fragment flows through dictionary/rule evidence, facts,
  domain signals, and score contribution. Nodes reuse the existing settings
  modal/deeplink behavior, and manual review verdicts are respected when the
  chain displays the lead/non-lead outcome.
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
  configured `lead_veto_signal_types` force `is_lead=false` and
  `temperature=none` for explicit supply/sale/DIY/price-only or ordinary
  household/operator noise. Configured `score_caps` can also limit final
  score; bootstrap `hard_noise` caps these clear noise classes at `0` and emits
  an explanatory `score_cap` reason. Operator-created noise is added to that cap
  by migration/constructor code when the operator noise rule exists.
- Default device aliases no longer include the broad phrase `модуль управления`
  for relay modules. Migration `0018_lead_scoring_caps` patches the active
  PostgreSQL NLP config with `score_caps` and removes that alias from
  `devices.relay_module`.
- Migration `0019_operator_noise_score_cap` appends `operator_noise` to the
  active hard-noise score cap. The Review "В шум" constructor also maintains
  that link for future operator-created noise phrases.
- Config v3 keeps alias/fact/signal layers explicit. Camera and recorder aliases
  emit `video_device`; `камера` gives at most `pur_video_surveillance` and stays
  below lead without intent. A bare `ИК` emits no high-level climate/gateway
  signal. Plain fixtures such as `бра` remain controlled-device evidence only,
  not smart-lighting automation.
- Default scoring has `domain_without_intent` and `intent_without_pur_domain`
  score caps. Isolated domain words and aliases such as `Нептун`, `хаб`,
  `шайба`, `кондиционер`, `умный дом`, and `PoE` stay below lead without
  intent; off-domain requests such as "где заказать обычный стол" stay below
  lead without a PUR domain.
- Review lane matching is centralized in `app.application.review_lanes`. The
  deterministic scorer and analytics import/list code use the same priority,
  exclusion, score/temperature, and match-group logic, including matched group
  indexes for explanations.
- Dev PostgreSQL active NLP config revision is `31`, source
  `migration_0026_config_v3_taxonomy`. It replaces active facts, signals, and
  lead scoring with v3 defaults while preserving existing alias catalogs and
  existing operator noise wiring when present.
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

1. Review live `research_warm`, `noise`, and `direct_pur_lead` candidates and
   rerun `app.cli.eval_reviews` after each calibration pass.
2. Promote confirmed production examples into a curated eval/golden dataset
   after deciding what text can be committed versus kept in ignored artifacts.
3. Decide whether to close the remaining rare Telegram crash window by combining
   enrichment job creation and source-message insert into one repository unit of
   work, or by cleaning up stale blocked `enrichment_task_outbox` rows.
4. Keep an eye on host disk usage before larger dependency/model downloads.
