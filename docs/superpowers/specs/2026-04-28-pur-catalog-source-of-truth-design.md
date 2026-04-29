# PUR Catalog Source Of Truth Design

Date: 2026-04-28

## Goal

Build a durable source-of-truth layer for PUR lead detection.

The system must continuously read the PUR Telegram channel, parse messages and documents, extract products/services/terms/offers into SQLite, use those catalog facts immediately for lead detection, and let Oleg correct the system through a web interface. Telegram remains an information channel, not the main working UI.

## Core Decisions

- SQLite is the primary data store.
- The PUR channel is the raw source of truth for facts.
- The approved/auto-added SQLite catalog is the operational source of truth for classification.
- New catalog facts are auto-added by default as `auto_pending`.
- `auto_pending` facts are active immediately in the classifier.
- Feedback must be traceable to the exact lead, catalog item, term, source, and classifier version that caused a match.
- Video is not downloaded by default. Documents are downloaded and parsed.
- Telegraph and configured external pages are fetched and parsed.
- Oleg can manually add examples of leads, non-leads, catalog facts, or source links.
- The web interface starts with one role: `admin`.
- The web interface uses Material Web as the first design system for operator-facing screens. Bootstrap is not mixed into the same UI layer. Custom CSS is limited to layout, spacing, product composition, and Material token overrides.
- A built-in local administrator account exists for bootstrap. Telegram admin accounts are added through that account.
- On startup, the built-in administrator has a temporary password written to `PUR_BOOTSTRAP_ADMIN_PASSWORD_FILE` when the account still requires a password change. After the first successful local login and password change, the file is deleted and `must_change_password=false` becomes the durable marker that prevents regenerating or rewriting the bootstrap password on later restarts.
- A clean installation/reset contains only the built-in local administrator and empty system tables. Telegram userbots, notification groups, bot tokens, Telegram API credentials, Z.AI/API credentials, AI provider routes, sources, catalog data, and generated session files are added explicitly by an administrator through the web/admin onboarding flow.
- Runtime workers must not silently seed provider accounts, userbots, notification chats, source rows, session files, or secrets from the deployment environment. Defaults may exist in code for form help and explicit "load defaults" actions, but they do not create operational database rows until an administrator confirms them.
- `auto_pending` notification styling, campaign expiry, and external fetch domains are configurable in the web interface.
- CRM is included as a lightweight client-memory layer, not a heavy sales pipeline.
- CRM starts empty. Clients, interests, assets, and notes can be created manually or from confirmed leads.
- The first version assumes a single active admin user workflow, but tables include ownership/assignee fields for future expansion.
- A central CRM job is generating reasons to contact existing or previously interested clients when catalog changes create a useful follow-up opportunity.
- Runtime work is processed by a continuous job loop, not a single monolithic polling cycle.
- Start with no Telegram userbot sessions configured. The first and additional userbot sessions are created through interactive web login; the first runtime default remains one Telegram worker and one read job per configured session.
- Monitoring chats are added through web onboarding with access check and preview before activation.
- New live monitoring sources default to `from_now`; historical backfill is explicit and retro/web-only by default.
- Telegram-read jobs are serialized per userbot session. AI and parse jobs can run in parallel with configurable limits.
- Logging and audit are first-class requirements for source sync, access issues, AI calls, parser runs, catalog changes, CRM changes, and notifications.
- AI batching, reclassification, and retro research behavior are configurable because they will need tuning after real traffic is observed.
- Retro research is a separate product workflow for testing new commercial directions against historical chat demand before adding them to the operational catalog.
- All readable monitoring-source messages are stored, even if they are not leads, because reclassification, research, deduplication, sender intelligence, and future semantic search depend on historical data.
- `Leads Inbox` works with `lead_clusters`, not raw `lead_events`, so multiple related messages become one work item.
- `lead_events` remain auditable detection facts tied to exact messages, classifier versions, and matches.
- Automatic lead clustering is configurable and manually correctable through merge/split/context-only actions.
- Feedback distinguishes classifier quality from commercial outcome. "Not a lead" teaches detection; "no answer", "too expensive", or "bought elsewhere" are CRM/work outcomes, not negative classifier examples.
- `not_lead` feedback requires a reason and should be applied to the narrowest useful target: cluster, event, match, term, sender, or message.
- Confirmed clusters produce CRM conversion candidates, not full CRM records, unless Oleg explicitly accepts them.
- `Take into work` creates an action task only. Client, interest, opportunity, support case, and contact reason conversion happens after clarification.
- Catalog ingestion uses a layered pipeline: immutable source, parsed chunks, extracted facts, deduplicated catalog candidates, then operational catalog.
- Manual catalog additions use the same source/evidence/candidate path as AI extraction, with faster approval defaults for Oleg/admin.
- Quality/evaluation is part of the product: golden sets, feedback-derived regression cases, precision/recall metrics, and quality dashboards are required.
- Backup, restore, and secret hygiene are required first-class operational features.
- There is no separate reduced MVP. The first production target is the full first-phase spec, with only explicitly agreed next-phase items left out.
- Embeddings/semantic matching are designed into the schema but disabled initially.
- Retention is based on time and hot database size. Large/old data is archived and rotated, not simply deleted.
- Local archive storage is the first phase. S3-compatible storage is represented in the schema and planned for a later phase.

## Resource Orchestration And Capacity Planning

The runtime must treat connected providers, models, Telegram user accounts, ordinary Telegram bots, and local worker processes as one capacity system.

The goal is not to set one large worker count manually. The system must calculate how much work can be usefully executed from the currently connected resources, then let the scheduler keep those resources busy without starving live lead handling.

### Resource Pools

Each external or scarce capability is represented as a resource pool:

- `ai_provider_account:model`: one concrete provider account and one concrete model, for example `zai-account-1:GLM-4-Plus`.
- `telegram_userbot`: one Telegram user account session that can read chats/channels and download Telegram documents.
- `telegram_bot`: one ordinary Bot API token that can send notifications, delete setup messages, and operate notification groups.
- `local_parser`: CPU/local IO capacity for PDF text extraction, chunking, deduplication, and local heuristics.
- `external_fetch`: HTTP fetch capacity for Telegraph and other configured domains.
- `worker`: the global runtime execution slot used by every job.

AI limits are scoped to concrete provider account + model. A model with the same public name on two enabled provider accounts is two separate pools. Provider-level model defaults may be used as a fallback, but the runtime planner must display and eventually enforce the account-level pool.

Every resource pool stores or derives:

- provider/account/model/bot/userbot identity;
- capability tags such as `llm.text.fast`, `llm.text.strong`, `ocr.document`, `telegram.read_history`, `telegram.download_document`, `telegram.notify`;
- raw limit;
- utilization ratio, default `0.8`;
- effective limit, using `max(1, floor(raw_limit * utilization_ratio))`;
- active leases;
- available slots;
- current health: active, paused, flood-wait, rate-limited, disabled, missing credentials, or errored.

AI model metadata must describe capabilities, not just a name and concurrency limit. For each provider model the registry stores the endpoint family, supported input/output modalities, whether the model supports structured JSON output, whether it supports thinking/reasoning controls, and which provider-specific control values are valid.

This is provider-specific by design:

- Z.AI chat-completion models that support reasoning use `thinking.type=enabled|disabled`; there is no `min/medium/high/xhigh` scale for Z.AI.
- Other providers may expose reasoning effort as `off|min|medium|high|xhigh` or another enum. The route stores provider-neutral `thinking_mode`; the provider adapter translates it to the concrete API payload.
- Z.AI structured output is a chat-completion capability enabled with `response_format={"type":"json_object"}` and must be sent only to models that support it.
- Z.AI OCR is not a normal chat-completion model. `GLM-OCR` uses the `layout_parsing` endpoint, accepts PDF/images, and must not receive chat-only `thinking` or `response_format` options.

Sources used for the initial Z.AI capability seed:

- Chat completion parameters: `https://docs.z.ai/api-reference/llm/chat-completion`
- Thinking mode: `https://docs.z.ai/guides/capabilities/thinking-mode`
- Structured output: `https://docs.z.ai/guides/capabilities/struct-output`
- GLM-OCR layout parsing: `https://docs.z.ai/guides/vlm/glm-ocr`

### Task Definitions

Scheduler job types must map to task definitions. The task definition tells the resource scheduler what is required before a job can run:

| Task | Workload class | Required resource capabilities | Parallelism rule |
| --- | --- | --- | --- |
| `poll_monitored_source` / `telegram_read_history` | live or bulk | `worker`, `telegram.read_history` | serialized per userbot unless explicitly configured higher |
| `download_artifact` | bulk | `worker`, `telegram.download_document` | bounded per userbot |
| `fetch_external_page` | bulk | `worker`, `external_fetch` | bounded by HTTP fetch pool |
| `parse_artifact` | bulk | `worker`, `local_parser` | bounded by local parser pool |
| `ocr_artifact` | bulk | `worker`, `ocr.document` | bounded by selected OCR model pool |
| `extract_catalog_facts` | bulk or normal | `worker`, `llm.text.fast` or `llm.text.strong` | routed by catalog agent route |
| `classify_message_batch` | realtime | `worker`, optional `llm.text.fast` for shadow | lead fuzzy path is local, LLM shadow uses AI pool |
| `send_notifications` | realtime | `worker`, `telegram.notify` | bounded per bot/group route |
| `generate_contact_reasons` | normal | `worker`, `llm.text.fast` or local | routed by CRM agent route when enabled |

Each scheduler job may store a workload class:

- `realtime`: live leads, operator notifications, source access problems requiring action;
- `normal`: current catalog updates, CRM reminders, routine checks;
- `bulk`: initial channel ingest, historical backfill, retro research, large document batches.

Bulk work may use all free capacity, but it must not permanently consume capacity reserved for realtime work.

### Model Selection Strategy

The scheduler must not blindly use the strongest model for every AI task.

Model choice is task-dependent:

- Fast/light language models are preferred for first-pass extraction, lead shadow checks, deduplication, normalization, and high-volume catalog chunks.
- Stronger/heavier language models are reserved for low-confidence extraction, conflicting facts, high-value sources, final synthesis, or manual recheck.
- OCR models are used only for scanned PDFs/images or files where local text extraction produced empty/low-quality chunks.
- Fallback routes are explicit: fast model first, strong model on low confidence or invalid structured output, local heuristic fallback when configured.

Agent routes therefore support multiple enabled models per task:

- `primary`
- `fallback`
- `shadow`
- `ensemble`
- `split`
- `manual_test`

The route selector chooses from enabled routes that match the task, workload class, input type, and required capability. If several provider accounts expose the same model class, the least-loaded healthy pool wins.

### Worker Count Calculation

The system exposes three numbers:

- `configured_worker_concurrency`: what the running worker process is currently configured to use.
- `resource_limited_worker_capacity`: how many concurrent jobs can be useful given active resource pools.
- `recommended_worker_concurrency`: `min(worker_global_cap, resource_limited_worker_capacity)`.

Worker concurrency is adjustable at runtime. The worker process rereads `worker_concurrency` between scheduling batches and changes the number of active async job loops without requiring a container restart. Lowering the setting is graceful: existing jobs finish, and the next batch starts fewer loops. Raising the setting allows the next batch to start more loops, bounded by the configured value and later by scheduler resource leases.

The resource-limited capacity is not just AI capacity. It combines active pools that can run independent jobs:

- active AI model slots across provider accounts and selected agent routes;
- active Telegram userbot read/download slots;
- ordinary bot notification slots;
- local parser slots;
- external page fetch slots.

The UI must show the bottleneck explicitly. Examples:

- If `GLM-4-Plus` has 16 effective slots but `configured_worker_concurrency=1`, the bottleneck is global worker count.
- If there are 16 worker slots but one Telegram userbot, initial message fetching remains limited by that one userbot.
- If scanned PDFs are queued and `GLM-OCR` has one effective slot, OCR is the bottleneck.
- If live lead notifications are queued and no Telegram bot is enabled, notification routing is the bottleneck.

### Reservations And Priority

Realtime lead handling has priority over bulk catalog ingest.

Initial default policy:

- keep a configurable realtime worker reserve, default `2`;
- keep a configurable realtime AI reserve per routed lead model when live LLM lead checks are enabled;
- keep Telegram notification capacity available for urgent lead/operator messages;
- let bulk catalog ingest consume all remaining free capacity;
- avoid preemption in the first implementation by keeping jobs bounded and short.

Future policy can support preemption or dynamic throttling, but the first implementation only needs short leases, frequent scheduling, and clear priority ordering.

### Observability

The web UI must expose a capacity view:

- configured vs recommended worker count;
- active provider accounts and model pools;
- raw/effective/used/free slots per model account;
- active userbots and their read/download slots;
- active bots and notification routes;
- queued/running jobs by workload class and job type;
- current bottlenecks and recommended operator actions.

Capacity calculation is advisory first, then becomes enforceable as resource leases are moved from individual adapters into the scheduler.

## Bootstrap Onboarding Flow

After the built-in administrator changes the temporary password, the web UI routes incomplete installations to `/onboarding`.

The onboarding flow is part of the product UI, not a deployment-only script:

- Auth and onboarding controls use a local pinned Material Web bundle served from the application static assets. External CDN examples are not used in production runtime.
- The page shows embedded Russian setup guidance and a live checklist for password change, required resource types, and first monitored source.
- The main onboarding workspace is a single resource list with one `Добавить ресурс` action. The admin selects a resource type in a dialog, then fills only the fields for that type.
- All resource instances have a human-readable name, status, health, type, delete action, and a future edit action. Type-specific secrets and runtime fields remain in their existing tables.
- Initial resource types are `telegram_bot`, `telegram_notification_group`, `telegram_userbot`, and `ai_provider_account`.
- The ordinary Telegram bot token is pasted in the resource dialog, validated through Telegram Bot API `getMe`, and stored as a local file-backed `secret_refs` value. API responses and UI state never return the raw token.
- Notification group setup is discovered through Bot API `getUpdates`: the admin adds the bot to a group/topic, sends a setup message, and selects the discovered chat in the resource dialog. Saving the group sends a test `sendMessage` and stores `telegram_lead_notification_chat_id` plus optional `telegram_lead_notification_thread_id`.
- Userbot setup uses interactive phone/code/2FA login from the resource dialog. Existing Telethon `.session` file upload is not part of the onboarding flow. The generated session file is stored on disk with owner-only permissions; Telegram API hash is stored as a `secret_refs` value.
- Userbot setup includes external helper links to Telegram API application management and Telegram Web. These pages are opened as separate tabs because Telegram sets frame restrictions that make iframe embedding unreliable.
- LLM provider setup is required before adding the first monitored source. The first provider is Z.AI: the admin enters resource name, base URL, and API key. The system stores the API key as a local `secret_refs` value and bootstraps known provider/model/limit metadata.
- LLM model selection is not part of onboarding. Model capabilities and agent routes live in the AI registry/admin surface, where the operator can manage provider metadata, model capabilities, limits, and task routes.
- AI routes bind a task to a concrete provider account and model. Runtime clients resolve the selected account's `auth_secret_ref` and `base_url`, so two Z.AI resources with different tokens are separate executable pools rather than aliases for one global key.
- Runtime web authentication and workers resolve Telegram bot/API credentials from settings-backed secret refs first, with environment fallback only for development or explicitly configured deployments.
- The onboarding flow does not create monitoring sources implicitly. Source onboarding remains a separate audited web flow with access check and preview before activation.

## Source Layers

### Raw Sources

Raw sources are immutable or append-only records:

- Telegram channel messages from `@purmaster`.
- Message text and media captions.
- Downloaded document metadata.
- Parsed PDF/DOC/XLS text.
- Telegraph pages and configured external pages.
- Manual source links provided by Oleg.

Raw source records are never manually edited. If something is wrong, a correction is stored as feedback or review metadata.

### Operational Catalog

The operational catalog contains extracted and reviewed business knowledge:

- categories;
- products;
- services;
- solution bundles;
- brands;
- models;
- keywords and aliases;
- prices, offers, and terms;
- lead intent examples;
- evidence links to raw sources.

Statuses control how the classifier uses each object.

### CRM Memory

The CRM layer stores what PUR knows about clients over time:

- who the client/contact is;
- what object they have: house, apartment, dacha, cottage settlement, office, warehouse, production site;
- what they wanted, failed to find, postponed, bought, or asked about;
- what PUR installed or sold;
- support and maintenance history;
- contact reasons generated from new catalog facts, seasonal triggers, price changes, support dates, and manual reminders.

CRM starts from an empty database. Manual input is a first-class workflow. Future import is allowed by the schema but is not part of the first implementation.

### Retro Research

Retro research is used to test future product or service directions. It is different from live lead detection:

- it may start from a hypothesis that is not part of PUR's current catalog;
- it searches historical demand signals in saved messages and, if configured, temporary backfill from selected sources;
- it produces a web report first;
- it can later create catalog entries, leads, client interests, or contact reasons by explicit action or setting.

This supports cases where Oleg decides to sell a new category. The system can estimate whether past chat history contains real demand before that category becomes part of the operational catalog.

## Status Model

Catalog items, terms, attributes, and offers support these statuses:

- `auto_pending`: automatically added, active in classifier, waiting for review.
- `approved`: confirmed by Oleg/admin, active in classifier.
- `rejected`: not used.
- `muted`: temporarily disabled but retained.
- `needs_review`: active or inactive depending on setting, requires human review.
- `deprecated`: old but retained for history.
- `expired`: expired price/offer/temporary promotion.

Default classifier inclusion:

- include `approved`;
- include `auto_pending`;
- exclude `rejected`, `muted`, `deprecated`, `expired`;
- `needs_review` is configurable.

## Current External Limits To Track

This section documents public limits and operational constraints as of 2026-04-28. These values must not be treated as permanent constants. Store them in SQLite settings/model-limit tables and update them when provider documentation or observed runtime behavior changes.

### Telegram / Telethon Userbot Limits

Telegram does not publish exact MTProto request limits for every method/account/source combination. Telethon documentation explicitly notes that exact limits are not known and depend on many factors. Therefore the system must be adaptive:

- Start with one userbot session and one serialized Telegram-read worker.
- Use small bounded jobs and persist checkpoints after every job.
- Handle `FLOOD_WAIT`/`FloodWaitError` as a normal runtime state, not an exceptional crash.
- Store flood wait seconds in `rate_limit_states.paused_until`.
- Continue processing other sources/jobs while one account/source is paused.
- Use operator notifications only when a human action is required or repeated failures cross thresholds.

Known public Telethon guidance:

- `FloodWaitError` indicates the same request was repeated too many times and exposes wait seconds.
- Telethon can auto-sleep on flood waits under `flood_sleep_threshold`.
- For `GetHistoryRequest`, Telethon documentation says Telegram's flood wait limit "seems to be around 30 seconds per 10 requests"; the default history wait behavior is designed to reduce flood waits.
- Retrieving more than roughly 3000 messages takes longer and may require wait time between requests.

Sources:

- Telethon RPC Errors: `https://docs.telethon.dev/en/stable/concepts/errors.html`
- Telethon TelegramClient / iter_messages: `https://docs.telethon.dev/en/stable/modules/client.html`

Design implication:

- The web UI should show observed limits/flood waits per userbot and source.
- Adding more userbot accounts is a future scaling path, configured in the web UI.
- The system should never try to bypass anti-bot protections. It should surface `needs_join`, `needs_captcha`, `private_or_no_access`, `banned`, and `flood_wait` clearly.

### z.ai Coding Plan / API Limits

z.ai limits depend on plan, model, time window, and whether the usage is through supported tools.

Current public Coding Plan notes:

- Supported Coding Plan models: `GLM-5.1`, `GLM-5-Turbo`, `GLM-4.7`, `GLM-4.5-Air`.
- Coding Plan quota is based on 5-hour and weekly windows.
- Approximate plan limits:
  - Lite: up to about 80 prompts per 5 hours, about 400 weekly.
  - Pro: up to about 400 prompts per 5 hours, about 2000 weekly.
  - Max: up to about 1600 prompts per 5 hours, about 8000 weekly.
- Concurrency limits are plan-dependent and dynamically adjusted; public guidance is Max > Pro > Lite.
- GLM-5.1 and GLM-5-Turbo consume more quota during peak/off-peak periods according to z.ai's current rules.
- Peak hours are documented as 14:00-18:00 UTC+8.
- z.ai states the Coding Plan is limited to officially supported tools/products and unsupported SDK/third-party integrations may be restricted.

Current public model/API notes:

- `GLM-5.1`: context length 200K, maximum output 128K.
- `GLM-4.7`: context length 200K, maximum output 128K.
- `GLM-4.5`: context length 128K, maximum output 96K.
- Chat Completions endpoint supports `thinking.type` enabled/disabled for supported models.
- Chat Completions response includes `usage` fields with prompt/completion/total tokens.

Sources:

- z.ai Coding Plan overview: `https://docs.z.ai/devpack/overview`
- z.ai Coding Plan usage policy: `https://docs.z.ai/devpack/usage-policy`
- z.ai Coding Plan FAQ: `https://docs.z.ai/devpack/faq`
- z.ai Chat Completion API: `https://docs.z.ai/api-reference/llm/chat-completion`
- GLM-5.1 model page: `https://docs.z.ai/guides/llm/glm-5.1`
- GLM-4.7 model page: `https://docs.z.ai/guides/llm/glm-4.7`
- GLM-4.5 model page: `https://docs.z.ai/guides/llm/glm-4.5`

Design implication:

- The AI provider layer must distinguish Coding Plan from regular API platform / enterprise usage.
- The UI should surface the policy warning when using Coding Plan credentials for this application.
- AI scheduler must track model usage, token usage, errors, provider throttling, and per-model concurrency leases.
- PromptBuilder must record prompt token estimates and actual response usage.
- Parallel AI job limits are configured per `provider:model`, not per model name globally.
- Configured provider limits are raw limits. Runtime effective limits use a configurable safety ratio, default `0.8`, as with Telegram safety margins.
- Effective concurrency formula: `max(1, floor(raw_limit * utilization_ratio))`. This preserves one active slot when the provider limit is `1`.
- One task may route to multiple models through agent routes: primary, fallback, shadow, ensemble, split, and manual-test routes.
- OCR is a first-class AI task because catalog files may contain scanned PDFs, images, or price sheets.

Initial z.ai model concurrency seed, from the operator-provided limit table:

| Provider | Model | Type | Raw concurrency |
| --- | --- | --- | --- |
| `zai` | `GLM-4.6` | language | 3 |
| `zai` | `GLM-4.6V-FlashX` | language | 3 |
| `zai` | `GLM-4.7` | language | 2 |
| `zai` | `GLM-Image` | image_generation | 1 |
| `zai` | `GLM-5-Turbo` | language | 1 |
| `zai` | `GLM-5V-Turbo` | language | 1 |
| `zai` | `GLM-5.1` | language | 1 |
| `zai` | `GLM-4.5` | language | 10 |
| `zai` | `GLM-4.6V` | language | 10 |
| `zai` | `GLM-4.7-Flash` | language | 1 |
| `zai` | `GLM-4.7-FlashX` | language | 3 |
| `zai` | `GLM-OCR` | ocr | 2 |
| `zai` | `GLM-5` | language | 2 |
| `zai` | `GLM-4-Plus` | language | 20 |
| `zai` | `GLM-4.5V` | language | 10 |
| `zai` | `GLM-4.6V-Flash` | language | 1 |
| `zai` | `AutoGLM-Phone-Multilingual` | language | 5 |
| `zai` | `GLM-4.5-Air` | language | 5 |
| `zai` | `GLM-4.5-AirX` | language | 5 |
| `zai` | `GLM-4.5-Flash` | language | 2 |
| `zai` | `GLM-4-32B-0414-128K` | language | 15 |
| `zai` | `CogView-4-250304` | image_generation | 5 |
| `zai` | `GLM-ASR-2512` | realtime_audio_video | 5 |
| `zai` | `ViduQ1-text` | video_generation | 5 |
| `zai` | `Viduq1-Image` | video_generation | 5 |
| `zai` | `Viduq1-Start-End` | video_generation | 5 |
| `zai` | `Vidu2-Image` | video_generation | 5 |
| `zai` | `Vidu2-Start-End` | video_generation | 5 |
| `zai` | `Vidu2-Reference` | video_generation | 5 |
| `zai` | `CogVideoX-3` | video_generation | 1 |

## Data Flow

```text
@purmaster
  -> telegram source sync
  -> raw sources
  -> artifact downloader
  -> document/page parser
  -> parsed chunks
  -> extraction runs
  -> extracted facts
  -> auto_pending catalog updates
  -> classifier snapshot
  -> lead detection
  -> lead matches
  -> Oleg feedback
  -> catalog/classifier updates
  -> contact reason generation
```

Lead monitoring flow:

```text
monitored source message
  -> source_messages
  -> context fetch
  -> AI/classifier decision
  -> lead_events + lead_matches
  -> lead clustering
  -> lead_clusters for Leads Inbox
  -> notification policy per cluster
  -> Oleg feedback / CRM follow-up
```

Runtime execution uses a continuous scheduler:

```text
while running:
  pick next due job
  run a bounded unit of work
  save cursor/checkpoint/result
  update rate-limit state
  schedule follow-up jobs
  move to the next job
```

The daemon should always keep working. If one source is blocked by access issues or flood wait, the worker records that state and moves to other available work.

Manual examples use the same downstream path:

```text
Oleg link/forward/manual text
  -> manual source or feedback event
  -> optional message fetch
  -> parsed source/chunk
  -> lead example / catalog fact / feedback
  -> optional client / interest / contact reason
  -> classifier update
```

## SQLite Schema

ID naming rules:

- `sources.id` is the raw source/evidence identity for Telegram messages, documents, Telegraph pages, external pages, and manual inputs.
- `monitored_sources.id` is the configured chat/channel/DM identity.
- `source_messages.id` is the canonical identity for a fetched Telegram message used by lead detection, clustering, context, reclassification, and research.
- New lead/research/AI tables should use explicit `source_message_id`, `monitored_source_id`, or `raw_source_id`; avoid ambiguous bare `source_id` except in raw-source/evidence tables.
- In catalog/CRM/evidence tables, `source_id` means `sources.id`.

### `userbot_accounts`

Stores Telegram userbot accounts that can read monitored Telegram sources.

Key fields:

- `id`
- `display_name`
- `telegram_user_id`
- `telegram_username`
- `session_name`
- `session_path`
- `status`: `active`, `paused`, `needs_login`, `banned`, `disabled`
- `priority`
- `max_parallel_telegram_jobs`
- `flood_sleep_threshold_seconds`
- `last_connected_at`
- `last_error`
- `created_at`
- `updated_at`

Rules:

- First implementation uses one active userbot account and one Telegram worker.
- The web UI may register additional userbot accounts, but default runtime concurrency remains one active Telegram worker and one read job per session until settings are changed.
- Session files are secrets and must never be exposed in the UI or logs.

### `monitored_sources`

Stores chats/channels/DMs that may be monitored.

Key fields:

- `id`
- `source_kind`: `telegram_group`, `telegram_supergroup`, `telegram_private_group`, `telegram_channel`, `telegram_comments`, `telegram_dm`
- `telegram_id`
- `username`
- `title`
- `invite_link_hash`
- `input_ref`
- `source_purpose`: `lead_monitoring`, `catalog_ingestion`, `both`
- `assigned_userbot_account_id`
- `priority`: `low`, `normal`, `high`
- `status`: `draft`, `checking_access`, `preview_ready`, `active`, `paused`, `needs_join`, `needs_captcha`, `private_or_no_access`, `flood_wait`, `banned`, `read_error`, `disabled`
- `lead_detection_enabled`
- `catalog_ingestion_enabled`
- `phase_enabled`
- `start_mode`: `from_now`, `from_message`, `recent_limit`, `recent_days`
- `start_message_id`
- `start_recent_limit`
- `start_recent_days`
- `historical_backfill_policy`: `none`, `retro_web_only`, `live_notifications_allowed`
- `checkpoint_message_id`
- `checkpoint_date`
- `last_preview_at`
- `preview_message_count`
- `next_poll_at`
- `poll_interval_seconds`
- `last_success_at`
- `last_error_at`
- `last_error`
- `added_by`
- `activated_by`
- `activated_at`
- `created_at`
- `updated_at`

Rules:

- First implementation enables public groups/supergroups for lead monitoring.
- Catalog ingestion enables configured channels, including `@purmaster`.
- Other source kinds are represented in the schema but can be hidden or marked "later" in UI.
- Chats are added from the web interface, not through Telegram commands.
- New live monitoring sources default to `start_mode = from_now`.
- Historical backfill defaults to `retro_web_only` so old messages do not create urgent Telegram noise.
- `active` sources are the only sources polled by the runtime worker.

### `source_access_checks`

Stores explicit access checks performed during source onboarding or recheck.

Key fields:

- `id`
- `monitored_source_id`
- `userbot_account_id`
- `check_type`: `onboarding`, `manual_recheck`, `scheduled_health_check`
- `status`: `succeeded`, `needs_join`, `needs_captcha`, `private_or_no_access`, `flood_wait`, `banned`, `failed`
- `resolved_source_kind`
- `resolved_telegram_id`
- `resolved_title`
- `last_message_id`
- `can_read_messages`
- `can_read_history`
- `flood_wait_seconds`
- `error`
- `checked_at`

Purpose:

- Show whether the selected userbot can legitimately read the source.
- Preserve the result that led to `preview_ready`, `active`, or an access issue.

### `source_preview_messages`

Stores a small preview sample shown before activation.

Key fields:

- `id`
- `monitored_source_id`
- `access_check_id`
- `telegram_message_id`
- `message_date`
- `sender_display`
- `text`
- `caption`
- `has_media`
- `media_metadata_json`
- `sort_order`
- `created_at`

Rules:

- Preview fetches a small configured number of recent readable text/caption messages.
- Preview does not download attachments.
- Preview does not move the live monitoring checkpoint.

### `source_messages`

Stores every readable message fetched from monitoring and catalog sources.

Key fields:

- `id`
- `monitored_source_id`
- `raw_source_id`
- `telegram_message_id`
- `sender_id`
- `message_date`
- `text`
- `caption`
- `normalized_text`
- `has_media`
- `media_metadata_json`
- `reply_to_message_id`
- `thread_id`
- `forward_metadata_json`
- `raw_metadata_json`
- `fetched_at`
- `classification_status`: `unclassified`, `queued`, `classified`, `skipped`, `archived`
- `archive_pointer_id`
- `is_archived_stub`
- `text_archived`
- `caption_archived`
- `metadata_archived`
- `created_at`
- `updated_at`

Rules:

- For monitoring sources, files are not downloaded by default, but media metadata is stored.
- Text and captions are stored for all readable messages.
- Media-only messages are stored as metadata records.
- Message text should be indexed with FTS5 while in the hot DB.
- Retention must keep the identity row as a hot stub; archive jobs move large text/caption/metadata payloads, not the primary row.
- Archived message stubs keep a hot pointer/snippet so UI and research can request restore without breaking foreign keys.

### `sender_profiles`

Stores observed Telegram senders and manual/feedback-derived role hints.

Key fields:

- `id`
- `telegram_user_id`
- `telegram_username`
- `display_name`
- `first_seen_source_id`
- `first_seen_at`
- `last_seen_at`
- `sender_role`: `unknown`, `potential_customer`, `customer`, `expert`, `vendor`, `bot`, `own_account`, `ignored`
- `role_confidence`
- `role_source`: `system`, `feedback`, `manual`, `crm`
- `crm_contact_id`
- `crm_client_id`
- `feedback_count`
- `notes`
- `created_at`
- `updated_at`

Rules:

- Sender role is a hint, not a hard block, unless explicitly set to `ignored`.
- `expert` and `vendor` senders can still provide context but should not become customer leads by default.
- Feedback such as `expert_or_advice` can create or update a sender role review candidate.

### `message_context_links`

Stores context relationships between messages.

Key fields:

- `id`
- `source_message_id`
- `related_source_message_id`
- `relation_type`: `reply_parent`, `reply_ancestor`, `neighbor_before`, `neighbor_after`, `same_thread`
- `distance`
- `created_at`

Purpose:

- Allow the classifier to include reply chains and neighboring messages.
- Preserve context for reclassification and retro research.

### `embeddings`

Stores vector embeddings for future semantic search.

Key fields:

- `id`
- `entity_type`: `source_message`, `parsed_chunk`, `catalog_item`, `catalog_term`, `client_interest`
- `entity_id`
- `provider`
- `model`
- `vector_blob`
- `dimensions`
- `text_hash`
- `status`: `active`, `stale`, `archived`, `failed`
- `created_at`
- `updated_at`

Rules:

- Embedding generation is disabled initially.
- Schema and jobs exist so it can be enabled later without redesign.
- Semantic match component returns no matches while embeddings are disabled.

### `access_issues`

Stores source access problems that require operator attention or retry.

Key fields:

- `id`
- `monitored_source_id`
- `userbot_account_id`
- `issue_type`: `needs_join`, `needs_captcha`, `private_or_no_access`, `flood_wait`, `banned`, `read_error`, `network_error`
- `status`: `open`, `resolved`, `ignored`
- `detected_at`
- `resolved_at`
- `retry_after_at`
- `operator_message`
- `technical_details`
- `notification_sent_at`
- `created_at`
- `updated_at`

Rules:

- Captcha/join/private/banned issues notify Telegram immediately.
- Temporary read/network errors notify after configured repeat thresholds.
- The system does not bypass anti-bot protections. It records the issue and asks an operator to complete legitimate access steps.

### `scheduler_jobs`

Stores continuous background work.

Key fields:

- `id`
- `job_type`: `poll_monitored_source`, `check_source_access`, `fetch_message_context`, `build_ai_batch`, `classify_message_batch`, `reclassify_messages`, `retro_research_scan`, `sync_pur_channel`, `download_artifact`, `parse_artifact`, `extract_catalog_facts`, `generate_contact_reasons`, `send_notifications`
- `status`: `queued`, `running`, `succeeded`, `failed`, `paused`, `cancelled`
- `priority`: `low`, `normal`, `high`
- `scope_type`: `global`, `telegram_userbot`, `telegram_source`, `ai_provider`, `ai_model`, `parser`, `archive`, `backup`
- `scope_id`
- `userbot_account_id`
- `monitored_source_id`
- `source_message_id`
- `idempotency_key`
- `run_after_at`
- `next_retry_at`
- `locked_by`
- `locked_at`
- `lease_expires_at`
- `attempt_count`
- `max_attempts`
- `checkpoint_before_json`
- `checkpoint_after_json`
- `result_summary_json`
- `payload_json`
- `last_error`
- `created_at`
- `updated_at`

Rules:

- Telegram jobs are serialized per `userbot_account_id`.
- Telegram/source/account scope fields must be SQL-visible for locking and rate-limit routing; they must not live only inside `payload_json`.
- `idempotency_key` prevents duplicate bounded jobs from processing the same source/window.
- `lease_expires_at` lets another worker recover abandoned jobs.
- Checkpoint fields store before/after cursors for resumability and audit.
- `result_summary_json` stores compact counters; detailed logs go to `job_runs` and `operational_events`.
- AI and parse jobs can run in parallel according to provider/parser settings.
- Jobs must be small and resumable.

### `job_runs`

Stores each execution attempt for observability.

Key fields:

- `id`
- `scheduler_job_id`
- `worker_name`
- `started_at`
- `finished_at`
- `status`
- `duration_ms`
- `result_json`
- `error`
- `log_correlation_id`

### `operational_events`

Stores structured runtime logs that should be queryable in the web UI.

Key fields:

- `id`
- `event_type`: `source_sync`, `access_check`, `telegram_request`, `ai_request`, `parser_run`, `catalog_extraction`, `notification`, `crm_generation`, `scheduler`
- `severity`: `debug`, `info`, `warning`, `error`, `critical`
- `entity_type`
- `entity_id`
- `correlation_id`
- `message`
- `details_json`
- `created_at`

Purpose:

- Keep operational visibility inside the product, not only in text log files.
- Support debugging without exposing secrets or excessive personal data.
- Link related events across scheduler jobs, provider calls, source sync, and notifications.

### `ai_usage_events`

Stores AI usage and quota observations.

Key fields:

- `id`
- `ai_provider_account_id`
- `ai_model_id`
- `provider`
- `model`
- `model_type`
- `ai_agent_id`
- `ai_agent_route_id`
- `ai_run_id`
- `ai_run_output_id`
- `scheduler_job_id`
- `classifier_version_id`
- `request_started_at`
- `request_finished_at`
- `status`
- `prompt_tokens`
- `completion_tokens`
- `total_tokens`
- `cached_tokens`
- `estimated_tokens`
- `thinking_enabled`
- `temperature`
- `max_tokens`
- `error`
- `raw_usage_json`
- `created_at`

Purpose:

- Track z.ai/API consumption.
- Compare estimated vs actual prompt size.
- Support future throttling, plan selection, and model switching.

### `ai_batches`

Stores AI classification batches and their prompt-size observations.

Key fields:

- `id`
- `batch_type`: `lead_detection`, `reclassification`, `retro_research`, `catalog_extraction`
- `strategy`: `source_time_window`, `thread_time_window`, `message_individual`, `keyword_clustered`, `adaptive`
- `monitored_source_id`
- `thread_id`
- `classifier_version_id`
- `message_count`
- `target_message_count`
- `context_message_count`
- `prompt_chars`
- `estimated_prompt_tokens`
- `actual_prompt_tokens`
- `actual_completion_tokens`
- `model`
- `status`: `queued`, `sent`, `parsed`, `failed`
- `wait_time_seconds`
- `created_at`
- `updated_at`

Rules:

- AI must return decisions per target message, never only for the batch as a whole.
- Batching strategy and size are settings.
- Prompt stats are used to tune full-catalog vs matched-hints strategies later.

### `ai_batch_messages`

Links messages to AI batches.

Key fields:

- `id`
- `ai_batch_id`
- `source_message_id`
- `monitored_source_id`
- `raw_source_id`
- `telegram_message_id`
- `role`: `target`, `reply_context`, `neighbor_before`, `neighbor_after`, `thread_context`
- `sort_order`
- `created_at`

Rules:

- Target and context rows reference `source_messages.id`.
- `monitored_source_id` and `telegram_message_id` are denormalized only for fast diagnostics and batch debugging.

### `notification_events`

Stores outbound Telegram/web notifications.

Key fields:

- `id`
- `notification_type`: `lead`, `lead_update`, `retro_lead`, `research_summary`, `task`, `contact_reason`, `access_issue`, `ai_error`, `sync_error`, `digest`
- `target_channel`: `telegram`, `web`, `email`, `none`
- `target_ref`
- `entity_type`
- `entity_id`
- `notification_policy`: `immediate`, `digest`, `web_only`, `suppressed`
- `status`: `queued`, `sent`, `failed`, `suppressed`
- `priority`: `low`, `normal`, `high`, `urgent`
- `dedupe_key`
- `cooldown_until`
- `suppression_reason`
- `payload_summary`
- `decision_snapshot_json`
- `error`
- `sent_at`
- `created_at`

Purpose:

- Audit what was sent to Telegram and why.
- Avoid duplicate urgent notifications.
- Support notification cooldowns and digests.
- Prove that a lead was only shown in web when Telegram delivery was intentionally suppressed.

### `archive_segments`

Stores archive segment metadata.

Key fields:

- `id`
- `segment_type`: `messages`, `parsed_chunks`, `operational_events`, `ai_usage`, `notifications`, `job_runs`, `research`, `embeddings`, `mixed`
- `period_start`
- `period_end`
- `storage_backend`: `local`, `s3_compatible`
- `archive_format`: `parquet_zstd`, `jsonl_zstd`, `sqlite_zstd`
- `compression`: `zstd`, `none`
- `base_path`
- `storage_uri`
- `manifest_path`
- `schema_version`
- `sha256`
- `size_bytes`
- `row_count`
- `status`: `writing`, `verified`, `failed`, `restored`, `deleted`
- `created_at`
- `updated_at`

Rules:

- First implementation uses `storage_backend = local`.
- S3-compatible storage is planned for a later phase but represented in the schema.
- Default archive format is `parquet_zstd` when dependencies are available.
- `jsonl_zstd` is the fallback for simple inspection and emergency recovery.
- `sqlite_zstd` is optional for compact whole-table snapshots.
- Archive writes must be verified before hot payload columns are cleared or unreferenced rows are deleted.
- Archive manifests must contain schema version, table names, row counts, hashes, and source query/window metadata.

### `archive_files`

Stores files belonging to archive segments.

Key fields:

- `id`
- `archive_segment_id`
- `storage_backend`
- `path`
- `storage_uri`
- `table_name`
- `format`
- `compression`
- `sha256`
- `size_bytes`
- `row_count`
- `created_at`

### `archive_pointers`

Keeps lightweight hot-db pointers to archived entities.

Key fields:

- `id`
- `entity_type`
- `entity_id`
- `archive_segment_id`
- `lookup_key`
- `snippet`
- `content_hash`
- `created_at`

Purpose:

- Let UI show that a historical message/log exists in archive.
- Enable restore jobs for research/reclassification.
- Keep enough metadata to search and request restore without keeping full text in the hot DB forever.
- Provide a stable pointer even when the hot row is only a retained stub.

### `archive_restore_jobs`

Stores restore requests.

Key fields:

- `id`
- `archive_segment_id`
- `requested_by`
- `reason`: `research`, `reclassification`, `manual_review`, `debug`, `export`
- `status`: `queued`, `running`, `completed`, `failed`, `cancelled`
- `restore_scope_json`
- `started_at`
- `finished_at`
- `error`
- `created_at`

### `archive_manifests`

Stores parsed manifest metadata for archive validation.

Key fields:

- `id`
- `archive_segment_id`
- `schema_version`
- `manifest_json`
- `verified_at`
- `created_at`

### `rate_limit_states`

Stores observed provider/account/source rate limits.

Key fields:

- `id`
- `scope_type`: `telegram_global`, `telegram_userbot`, `telegram_source`, `ai_provider`, `ai_model`, `parser`
- `scope_id`
- `provider`
- `reason`: `flood_wait`, `slow_mode`, `quota_exhausted`, `concurrency_limit`, `timeout`, `manual_pause`
- `paused_until`
- `last_error`
- `observed_limit_json`
- `created_at`
- `updated_at`

Purpose:

- Do not hard-code Telegram limits.
- Record observed `FLOOD_WAIT`/quota responses and let the scheduler route around paused scopes.

### `ai_providers`

Stores logical AI provider definitions.

Key fields:

- `id`
- `provider_key`: `zai`, `openai_compatible`, `openai`, `local`, `other`
- `display_name`
- `provider_type`: `openai_compatible_chat`, `zai_platform`, `local_runtime`, `custom`
- `default_base_url`
- `documentation_url`
- `status`: `active`, `disabled`, `deprecated`
- `metadata_json`
- `created_at`
- `updated_at`

Rules:

- Provider identity is separate from account/API key identity.
- The same provider can have multiple accounts or base URLs later.

### `ai_provider_accounts`

Stores credentials and account-level runtime policy for a provider.

Key fields:

- `id`
- `ai_provider_id`
- `display_name`
- `base_url`
- `auth_secret_ref`
- `plan_type`: `coding_lite`, `coding_pro`, `coding_max`, `api_platform`, `enterprise`, `unknown`
- `enabled`
- `priority`
- `request_timeout_seconds`
- `policy_warning_required`
- `policy_warning_acknowledged_at`
- `metadata_json`
- `notes`
- `created_at`
- `updated_at`

Rules:

- Secret values are referenced, not stored in plaintext.
- For z.ai Coding Plan, the UI must show a usage-policy warning if the plan is used outside officially supported coding tools.
- Account status can disable all routes that depend on that account without deleting model history.

### `ai_models`

Stores concrete models under a concrete provider.

Key fields:

- `id`
- `ai_provider_id`
- `provider_model_name`
- `normalized_model_name`
- `display_name`
- `model_type`: `language`, `vision_language`, `ocr`, `embedding`, `image_generation`, `video_generation`, `realtime_audio_video`, `audio`, `other`
- `context_window_tokens`
- `max_output_tokens`
- `supports_structured_output`
- `supports_json_mode`
- `supports_thinking`
- `supports_tools`
- `supports_streaming`
- `supports_image_input`
- `supports_document_input`
- `supports_audio_input`
- `supports_video_input`
- `default_temperature`
- `status`: `active`, `disabled`, `deprecated`
- `source_url`
- `verified_at`
- `metadata_json`
- `created_at`
- `updated_at`

Rules:

- Model names are scoped by provider. `provider:model` is the concurrency and routing identity.
- `metadata_json` includes provider-specific capability details such as `endpoint_family`, `thinking_control_style`, `thinking_control_values`, `structured_output_mode`, and source URLs used to seed or verify those capabilities.
- Structured output and thinking controls are independent flags. OCR/image/video/realtime models may share concurrency accounting with language models, but their request payloads are provider-specific.
- The UI should allow enabling/disabling a model without deleting historical runs.

### `ai_model_limits`

Stores known and configured per-provider-model limits.

Key fields:

- `id`
- `ai_provider_id`
- `ai_model_id`
- `limit_scope`: `concurrency`, `requests_per_window`, `tokens_per_window`, `cost_budget`, `observed_backoff`
- `raw_limit`
- `utilization_ratio`
- `effective_limit`
- `window_seconds`
- `source`: `operator_configured`, `provider_docs`, `observed_runtime`, `system_default`
- `quota_multiplier_json`
- `source_url`
- `verified_at`
- `notes`
- `created_at`
- `updated_at`

Rules:

- Make model limits visible and editable in the web UI.
- Use `effective_limit = max(1, floor(raw_limit * utilization_ratio))` for concurrency.
- Default `utilization_ratio` is `0.8`; this is a safety margin, not a provider guarantee.
- Provider limits for raw `1` stay effective `1`.
- Allow prompt builder to estimate token budget and choose fallback strategies.

### `ai_agents`

Stores logical AI workers that perform a task, independent of model choice.

Key fields:

- `id`
- `agent_key`: `catalog_extractor`, `lead_detector`, `lead_shadow_detector`, `ocr_extractor`, `crm_summarizer`, `research_matcher`, `manual_test`
- `display_name`
- `task_type`: `catalog_extraction`, `lead_detection`, `ocr`, `crm`, `research`, `evaluation`, `generation`
- `input_schema_json`
- `output_schema_json`
- `default_strategy`: `primary_fallback`, `shadow`, `ensemble`, `split`, `manual`
- `enabled`
- `metadata_json`
- `created_at`
- `updated_at`

Rules:

- An agent is the stable application contract. Models can change without changing the rest of the pipeline.
- Agents must request structured output whenever the provider/model supports it.
- Agent output must be validated before it can mutate catalog, leads, CRM, or notification state.

### `ai_agent_routes`

Maps one agent to one or more provider/model/account routes.

Key fields:

- `id`
- `ai_agent_id`
- `ai_provider_account_id`
- `ai_model_id`
- `route_role`: `primary`, `fallback`, `shadow`, `ensemble_member`, `split_bucket`, `manual_test`
- `priority`
- `weight`
- `enabled`
- `max_input_tokens`
- `max_output_tokens`
- `temperature`
- `thinking_enabled`
- `thinking_mode`: provider-neutral value such as `off`, `on`, `min`, `medium`, `high`, `xhigh`; provider adapters translate it to the concrete API payload
- `structured_output_required`
- `fallback_on_error`
- `fallback_on_rate_limit`
- `fallback_on_invalid_output`
- `route_conditions_json`
- `metadata_json`
- `created_at`
- `updated_at`

Rules:

- A task can use several models. Examples:
  - catalog extraction: `GLM-5.1` primary, `GLM-4.5-Air` fallback, `GLM-4.5-Flash` shadow.
  - lead detection: fuzzy primary, LLM shadow, later LLM fallback or ensemble.
  - OCR: `GLM-OCR` primary, vision-language fallback if configured.
- The router chooses routes by role, priority, weight, model availability, limits, and route conditions.
- Fallback can be triggered by provider error, rate limit, timeout, invalid JSON, schema validation failure, or operator-disabled route.
- Shadow routes write traces/evaluation records but do not create operational side effects unless explicitly promoted.

### `ai_runs`

Stores one logical AI agent run.

Key fields:

- `id`
- `ai_agent_id`
- `agent_key`
- `task_type`
- `scheduler_job_id`
- `source_id`
- `source_message_id`
- `artifact_id`
- `lead_event_id`
- `lead_cluster_id`
- `catalog_version_id`
- `input_hash`
- `settings_hash`
- `status`: `queued`, `running`, `succeeded`, `failed`, `cancelled`, `superseded`
- `strategy`
- `started_at`
- `finished_at`
- `error`
- `metadata_json`
- `created_at`

Purpose:

- Make every agent decision auditable even when the final application behavior is produced by another route.
- Tie catalog extraction, OCR extraction, lead detection, and future generation tasks to a common trace model.

### `ai_run_outputs`

Stores each provider/model attempt inside an AI agent run.

Key fields:

- `id`
- `ai_run_id`
- `ai_agent_route_id`
- `ai_provider_account_id`
- `ai_model_id`
- `provider`
- `model`
- `model_type`
- `route_role`
- `request_started_at`
- `request_finished_at`
- `status`
- `prompt_tokens`
- `completion_tokens`
- `total_tokens`
- `cached_tokens`
- `estimated_tokens`
- `temperature`
- `max_tokens`
- `thinking_enabled`
- `raw_request_json`
- `raw_response_json`
- `parsed_output_json`
- `schema_validation_json`
- `error`
- `created_at`

Rules:

- Raw request/response may be archived according to retention policy if too large for hot SQLite.
- Parsed output is the only value downstream services consume.
- Token usage and provider errors also feed `ai_usage_events` and quality dashboards.

### `ai_model_concurrency_leases`

Stores active per-provider-model execution slots.

Key fields:

- `id`
- `provider`
- `ai_model_id`
- `model`
- `normalized_model`
- `worker_name`
- `ai_run_id`
- `ai_run_output_id`
- `raw_limit`
- `utilization_ratio`
- `effective_limit`
- `acquired_at`
- `lease_expires_at`
- `metadata_json`

Rules:

- Leases are scoped by `provider:model`.
- Expired leases are reclaimed automatically.
- The lease table coordinates multiple worker loops and multiple containers.

### OCR Agent

OCR is a required AI agent, not a one-off parser.

Flow:

```text
artifact/document/image
  -> parser detects missing or low-quality text
  -> ocr_extractor agent route
  -> ai_runs / ai_run_outputs
  -> parsed_chunks with parser_name = "ai-ocr"
  -> catalog extraction agent
  -> catalog candidates
```

Rules:

- OCR should be used for scanned PDFs, image-only PDFs, photos of catalogs/price sheets, and document pages where text extraction is below a configurable confidence threshold.
- OCR output stores page/region evidence when available.
- OCR is not allowed to silently overwrite deterministic parser text; it creates additional chunks or alternative chunks with evidence.
- OCR failures are operational issues when repeated, not "empty text".

### `sources`

Stores raw source records.

Key fields:

- `id`
- `source_type`: `telegram_message`, `telegraph_page`, `external_page`, `manual_text`, `manual_link`
- `origin`: `purmaster`, chat username, URL host, or manual origin
- `external_id`: Telegram message id, URL, or manual id
- `url`
- `title`
- `author`
- `published_at`
- `fetched_at`
- `raw_text`
- `normalized_text`
- `content_hash`
- `metadata_json`
- `created_at`

Uniqueness:

- `(source_type, origin, external_id)` where applicable.
- `content_hash` can be used for duplicate detection, not as the only identity.

### `artifacts`

Stores downloaded files.

Key fields:

- `id`
- `source_id`
- `artifact_type`: `document`, `image_metadata`, `video_metadata`, `audio_metadata`
- `file_name`
- `mime_type`
- `file_size`
- `sha256`
- `local_path`
- `download_status`: `downloaded`, `skipped`, `failed`
- `skip_reason`: `video_disabled`, `photo_disabled`, `too_large`, `unsupported`
- `created_at`

Rules:

- Documents are downloaded by default.
- Videos are not downloaded by default.
- Photos are not downloaded by default unless later enabled.
- Metadata is still stored for skipped media.

### `parsed_chunks`

Stores text chunks from sources and artifacts.

Key fields:

- `id`
- `source_id`
- `artifact_id`
- `chunk_index`
- `text`
- `text_source`: `deterministic_parser`, `ai_ocr`, `manual`, `external_page`
- `confidence`
- `page_number`
- `region_json`
- `token_estimate`
- `parser_name`
- `parser_version`
- `ai_run_output_id`
- `created_at`

FTS:

- Create FTS5 index over `text`.

Rules:

- Deterministic parser chunks and OCR chunks can coexist for the same artifact/page.
- Downstream extractors receive chunk provenance so OCR-derived facts can be reviewed with appropriate confidence.

### `extraction_runs`

Stores extraction jobs.

Key fields:

- `id`
- `run_type`: `channel_sync`, `document_parse`, `catalog_extraction`, `manual_example_parse`
- `model`
- `ai_agent_id`
- `ai_run_id`
- `ai_run_output_id`
- `prompt_version`
- `catalog_version_id`
- `started_at`
- `finished_at`
- `status`
- `error`
- `stats_json`
- `source_scope_json`
- `extractor_version`
- `candidate_count`
- `fact_count`
- `created_catalog_entity_count`
- `token_usage_json`

### `catalog_versions`

Stores snapshots of operational catalog state used by extraction, classifier builds, and evaluation.

Key fields:

- `id`
- `version`
- `catalog_hash`
- `candidate_hash`
- `item_count`
- `term_count`
- `offer_count`
- `included_statuses_json`
- `created_by`
- `created_at`
- `notes`

Purpose:

- Make extraction/classifier runs reproducible.
- Distinguish catalog snapshots from classifier prompt/model snapshots.

### `extracted_facts`

Stores raw extracted facts before or alongside catalog insertion.

Key fields:

- `id`
- `extraction_run_id`
- `source_id`
- `chunk_id`
- `fact_type`: `category`, `product`, `service`, `bundle`, `brand`, `model`, `term`, `attribute`, `offer`, `lead_intent`
- `canonical_name`
- `value_json`
- `confidence`
- `status`: `new`, `accepted`, `rejected`, `merged`
- `created_at`

Purpose:

- Keep model output auditable.
- Allow re-processing with improved extraction prompts.
- Avoid losing facts that are not immediately accepted into the catalog.

### `catalog_candidates`

Stores normalized, deduplicated proposals before or alongside catalog mutation.

Key fields:

- `id`
- `candidate_type`: `category`, `item`, `term`, `attribute`, `offer`, `relation`, `lead_phrase`, `negative_phrase`
- `proposed_action`: `create`, `update`, `merge`, `expire`, `ignore`
- `canonical_name`
- `normalized_value_json`
- `source_count`
- `evidence_count`
- `confidence`
- `status`: `auto_pending`, `approved`, `rejected`, `merged`, `needs_review`, `muted`
- `target_entity_type`
- `target_entity_id`
- `merge_target_candidate_id`
- `first_seen_at`
- `last_seen_at`
- `created_by`: `system`, `oleg`, `admin`
- `created_at`
- `updated_at`

Purpose:

- Avoid creating duplicate catalog rows when the same product/service/term appears in multiple PUR sources.
- Give Catalog Review one queue for AI-extracted and manually proposed facts.
- Preserve proposed actions and conflicts before mutating operational catalog.

Rules:

- Auto-add can create operational catalog rows from candidates using `auto_pending`.
- Low-confidence, conflicting, too-broad, or price/offer candidates can be forced to `needs_review`.
- Rejected or merged candidates remain for audit and future extractor tuning.

### `catalog_candidate_facts`

Links extracted facts to catalog candidates.

Key fields:

- `id`
- `catalog_candidate_id`
- `extracted_fact_id`
- `created_at`

Purpose:

- Let one candidate aggregate evidence from many facts/sources.
- Preserve the raw model outputs that produced a candidate.

### `catalog_categories`

Stores category tree.

Key fields:

- `id`
- `parent_id`
- `slug`
- `name`
- `description`
- `status`
- `sort_order`
- `created_at`
- `updated_at`

Initial top-level categories:

- `video_surveillance`
- `intercom`
- `security_alarm`
- `access_control`
- `networks_sks`
- `smart_home_core`
- `lighting_shades`
- `power_electric`
- `climate_heating`
- `audio_voice`
- `project_service`

### `catalog_items`

Stores business objects: products, services, bundles, brands, and models.

Key fields:

- `id`
- `category_id`
- `item_type`: `product`, `service`, `bundle`, `brand`, `model`, `solution`
- `name`
- `canonical_name`
- `description`
- `status`
- `confidence`
- `first_seen_source_id`
- `first_seen_at`
- `last_seen_at`
- `created_by`: `system`, `oleg`, `admin`
- `created_at`
- `updated_at`

Examples:

- `Dahua Hero A1`
- `Dahua DH-MR403`
- `Автоматизация въездной группы`
- `ПУР Контроль`
- `Видеонаблюдение под ключ`

### `catalog_terms`

Stores terms that can trigger search/classification.

Key fields:

- `id`
- `item_id`
- `category_id`
- `term`
- `normalized_term`
- `term_type`: `keyword`, `alias`, `brand`, `model`, `problem_phrase`, `lead_phrase`, `negative_phrase`
- `language`
- `status`
- `weight`
- `created_by`
- `first_seen_source_id`
- `created_at`
- `updated_at`

Important distinction:

- A catalog item can be valid while one term is noisy.
- Feedback can mute/reject a term without rejecting the item.

### `catalog_attributes`

Stores structured item facts.

Key fields:

- `id`
- `item_id`
- `attribute_name`
- `attribute_value`
- `value_type`: `text`, `number`, `money`, `bool`, `date`, `json`
- `unit`
- `status`
- `valid_from`
- `valid_to`
- `created_at`
- `updated_at`

Examples:

- `price = 2500 RUB`
- `resolution = 2MP`
- `weather_rating = IP66`
- `connectivity = 4G`
- `storage = MicroSD up to 256GB`

### `catalog_offers`

Stores prices, campaigns, promotions, and time-bound commercial terms.

Key fields:

- `id`
- `item_id`
- `category_id`
- `offer_type`: `price`, `promotion`, `bundle_price`, `service_price`, `campaign`, `terms`
- `title`
- `description`
- `price_amount`
- `currency`
- `price_text`
- `terms_json`
- `status`: `auto_pending`, `approved`, `needs_review`, `expired`, `rejected`, `muted`
- `valid_from`
- `valid_to`
- `ttl_days`
- `ttl_source`: `explicit`, `default_setting`, `manual`, `none`
- `first_seen_source_id`
- `last_seen_source_id`
- `last_seen_at`
- `expired_at`
- `created_by`
- `created_at`
- `updated_at`

Rules:

- Offers/prices are first-class because expiry, price-change contact reasons, and evidence depend on them.
- Offers with no explicit validity use configured TTL and default review policy.
- Expired offers remain for audit and historical classifier/evaluation reconstruction.
- Offer evidence is stored through `catalog_evidence` with `entity_type = offer`.

### `catalog_relations`

Stores relationships between catalog items.

Key fields:

- `id`
- `from_item_id`
- `to_item_id`
- `relation_type`: `brand_of`, `model_of`, `part_of_bundle`, `requires`, `compatible_with`, `alternative_to`, `replaces`
- `status`
- `created_at`

Examples:

- `Dahua Hero A1 -> Dahua` as `model_of`.
- `Wi-Fi камера + 4G роутер + MicroSD` as parts of a bundle.

### `catalog_evidence`

Links catalog objects to source evidence.

Key fields:

- `id`
- `entity_type`: `category`, `item`, `term`, `attribute`, `relation`, `offer`, `catalog_candidate`, `extracted_fact`
- `entity_id`
- `source_id`
- `artifact_id`
- `chunk_id`
- `quote`
- `page_number`
- `location_json`
- `extractor_version`
- `evidence_type`: `ai_quote`, `manual_note`, `source_link`, `document_quote`
- `confidence`
- `created_by`: `system`, `oleg`, `admin`
- `created_at`

Purpose:

- Every fact should answer: "where did this come from?"
- UI can show source proof next to catalog changes.
- Manual additions still need evidence, even if the evidence is "manual note by Oleg".

### `manual_inputs`

Stores manual additions from Oleg/admin before they are processed.

Key fields:

- `id`
- `input_type`: `telegram_link`, `forwarded_message`, `manual_text`, `catalog_note`, `lead_example`, `non_lead_example`, `maybe_example`, `catalog_item`, `catalog_term`, `catalog_offer`, `catalog_relation`, `catalog_attribute`
- `submission_channel`: `web`, `telegram_bot`, `import`
- `text`
- `url`
- `chat_ref`
- `message_id`
- `submitted_by`
- `submitted_at`
- `processing_status`: `new`, `fetched`, `processed`, `failed`
- `metadata_json`

Manual inputs can become:

- source records;
- positive lead examples;
- negative examples;
- catalog item proposals;
- feedback events.

Rules:

- First-phase manual input is submitted through the web UI.
- `submission_channel = telegram_bot` exists for future optional forwarding input and is disabled by default.

### `classifier_examples`

Stores durable positive/negative training and prompt examples for classifier builds.

Key fields:

- `id`
- `example_type`: `lead_positive`, `lead_negative`, `maybe`, `high_value`, `retro`, `catalog_extraction`, `notification_policy`, `clustering`
- `polarity`: `positive`, `negative`, `neutral`
- `status`: `active`, `muted`, `rejected`, `archived`
- `source_message_id`
- `raw_source_id`
- `lead_cluster_id`
- `lead_event_id`
- `category_id`
- `catalog_item_id`
- `catalog_term_id`
- `reason_code`
- `example_text`
- `context_json`
- `weight`
- `created_from`: `manual_input`, `feedback`, `evaluation_case`, `import`
- `created_by`
- `created_at`
- `updated_at`

Rules:

- Feedback can create classifier examples, but only when the learning effect says classifier training should change.
- Active examples are included in classifier snapshots and evaluation metadata.
- Commercial outcomes do not become negative examples by default.

### `classifier_versions`

Stores snapshots of catalog state used by lead detection.

Key fields:

- `id`
- `version`
- `catalog_version_id`
- `created_at`
- `created_by`
- `included_statuses_json`
- `catalog_hash`
- `example_hash`
- `prompt_hash`
- `keyword_index_hash`
- `settings_hash`
- `model`
- `model_config_hash`
- `notes`

Rule:

- Every lead event records the classifier version used.
- A classifier version must be reconstructable from `classifier_snapshot_entries` and `classifier_version_artifacts`; hashes alone are not sufficient.

### `classifier_snapshot_entries`

Stores the actual catalog/example entries included in a classifier version.

Key fields:

- `id`
- `classifier_version_id`
- `entry_type`: `category`, `item`, `term`, `attribute`, `offer`, `example`, `negative_pattern`, `prompt_section`
- `entity_type`
- `entity_id`
- `status_at_build`
- `weight`
- `text_value`
- `normalized_value`
- `metadata_json`
- `content_hash`
- `created_at`

Purpose:

- Reconstruct what the classifier actually saw, not only hashes.
- Make feedback traceable to the exact term/item/example weight used at detection time.
- Preserve included `auto_pending`, `approved`, muted/excluded summary decisions, and prompt-only examples as explicit entries.

### `classifier_version_artifacts`

Stores prompt and generated classifier assets.

Key fields:

- `id`
- `classifier_version_id`
- `artifact_type`: `system_prompt`, `catalog_prompt`, `keyword_index`, `settings_snapshot`, `model_config`, `full_prompt`, `token_estimate`
- `content_text`
- `content_json`
- `content_hash`
- `created_at`

Rules:

- Prompt text and settings/model snapshots must be retained or archived with restore pointers.
- Artifacts can be large and are eligible for archive after hot retention, but their identity rows remain available.

### `lead_events`

Stores auditable lead-detection events tied to exact messages.

Key fields:

- `id`
- `source_message_id`
- `monitored_source_id`
- `raw_source_id`
- `chat_id`
- `telegram_message_id`
- `message_url`
- `sender_id`
- `sender_name`
- `message_text`
- `lead_cluster_id`
- `detected_at`
- `classifier_version_id`
- `decision`: `lead`, `not_lead`, `maybe`
- `detection_mode`: `live`, `reclassification`, `retro_research`, `manual`
- `confidence`
- `commercial_value_score`
- `negative_score`
- `high_value_signals_json`
- `negative_signals_json`
- `notify_reason`
- `reason`
- `event_status`: `active`, `context_only`, `duplicate`, `superseded`, `ignored`
- `event_review_status`: `unreviewed`, `confirmed`, `rejected`, `needs_more_info`
- `duplicate_of_lead_event_id`
- `is_retro`
- `original_detected_at`
- `created_at`

Uniqueness:

- `(source_message_id, classifier_version_id, detection_mode)` for audit.
- Operational notification suppression is cluster-based; `source_message_id` only prevents exact event duplicates for the same classifier run.

Rules:

- Retro events/clusters are visually marked in UI and Telegram notifications.
- Retro notifications must explain that the message is historical and why it surfaced now.
- Reclassification never mutates the old decision in place; it creates a new auditable result tied to the new classifier version.
- AI detection state is preserved separately from cluster inbox/work state.
- `lead_events` are not the primary `Leads Inbox` work item when clustering is enabled.
- Commercial value is scored separately from lead confidence so uncertain but potentially valuable requests can be surfaced without pretending they are confirmed leads.
- `chat_id` and `telegram_message_id` are denormalized display/debug fields; `source_message_id` is the canonical FK.

### `lead_clusters`

Stores the work items shown in `Leads Inbox`.

Key fields:

- `id`
- `monitored_source_id`
- `chat_id`
- `primary_sender_id`
- `primary_sender_name`
- `primary_lead_event_id`
- `primary_source_message_id`
- `category_id`
- `summary`
- `cluster_status`: `new`, `in_work`, `maybe`, `snoozed`, `not_lead`, `duplicate`, `converted`, `closed`
- `review_status`: `unreviewed`, `confirmed`, `rejected`, `needs_more_info`
- `work_outcome`: `none`, `contact_task_created`, `contacted`, `no_response`, `opportunity_created`, `support_case_created`, `client_interest_created`, `contact_reason_created`, `closed_no_action`
- `first_message_at`
- `last_message_at`
- `message_count`
- `lead_event_count`
- `confidence_max`
- `commercial_value_score_max`
- `negative_score_min`
- `dedupe_key`
- `merge_strategy`: `auto`, `manual`, `imported`, `none`
- `merge_reason`
- `last_notified_at`
- `notify_update_count`
- `snoozed_until`
- `duplicate_of_cluster_id`
- `primary_task_id`
- `converted_entity_type`
- `converted_entity_id`
- `crm_candidate_count`
- `crm_conversion_action_id`
- `created_at`
- `updated_at`

Rules:

- `Leads Inbox` lists clusters, not individual events.
- Telegram lead notifications are sent per cluster, not per event.
- `in_work` means the cluster requires human action, not that a client or opportunity already exists.
- CRM objects are created only after clarification or explicit action.
- Cluster status changes never delete underlying messages or lead events.

### `lead_cluster_members`

Links messages and lead events to clusters.

Key fields:

- `id`
- `lead_cluster_id`
- `source_message_id`
- `lead_event_id`
- `member_role`: `primary`, `trigger`, `clarification`, `context`, `negative_context`, `system`
- `added_by`: `system`, `oleg`, `admin`
- `merge_score`
- `merge_reason`
- `created_at`

Purpose:

- Keep the cluster timeline visible.
- Explain why messages/events were grouped.
- Allow a message to be marked as context without becoming a separate work item.

### `lead_cluster_actions`

Stores merge/split/context corrections.

Key fields:

- `id`
- `action_type`: `auto_merge`, `manual_merge`, `split`, `mark_context_only`, `set_primary`, `mark_duplicate`, `undo_merge`
- `from_cluster_id`
- `to_cluster_id`
- `source_message_id`
- `lead_event_id`
- `actor`
- `reason`
- `details_json`
- `created_at`

Purpose:

- Make automatic clustering auditable and reversible.
- Preserve manual corrections for future clustering/prompt tuning.

### `lead_matches`

Stores why a lead matched.

Key fields:

- `id`
- `lead_event_id`
- `source_message_id`
- `classifier_snapshot_entry_id`
- `catalog_item_id`
- `catalog_term_id`
- `catalog_offer_id`
- `category_id`
- `match_type`: `term`, `semantic`, `category`, `manual_example`, `llm_reason`
- `matched_text`
- `score`
- `item_status_at_detection`
- `term_status_at_detection`
- `offer_status_at_detection`
- `matched_weight`
- `matched_status_snapshot`
- `created_at`

This table is required because `auto_pending` is active immediately. Feedback needs to target exact match causes.

Rules:

- `classifier_snapshot_entry_id` points to the exact term/item/offer/example entry seen by the classifier.
- Status and weight snapshot fields allow review even after catalog terms are approved, muted, or reweighted.

### `reclassification_runs`

Stores reclassification jobs triggered by catalog, prompt, feedback, settings, or manual changes.

Key fields:

- `id`
- `trigger_type`: `catalog_change`, `prompt_change`, `feedback_change`, `settings_change`, `manual`
- `old_classifier_version_id`
- `new_classifier_version_id`
- `status`: `queued`, `running`, `completed`, `failed`, `cancelled`
- `source_scope`: `all`, `high_priority_only`, `selected_sources`
- `window_days`
- `max_messages`
- `include_previous_not_leads`
- `include_maybe`
- `include_leads`
- `include_unclassified`
- `notify_new_leads`
- `started_at`
- `finished_at`
- `stats_json`
- `created_by`
- `created_at`

Purpose:

- Re-run historical messages when the classifier changes.
- Find retro leads after catalog/prompt/feedback updates without losing audit history.

### `reclassification_results`

Stores per-message reclassification changes.

Key fields:

- `id`
- `reclassification_run_id`
- `source_message_id`
- `monitored_source_id`
- `raw_source_id`
- `telegram_message_id`
- `old_lead_event_id`
- `new_lead_event_id`
- `old_decision`
- `new_decision`
- `decision_changed`
- `notification_policy`: `notify`, `web_only`, `suppress`
- `created_at`

Rules:

- `maybe` remains web-only by default.
- Historical messages that become `lead` stay web-only by default and can notify Telegram as `retro_lead` only if explicitly enabled.
- Retro notifications must not look like fresh live messages.

### `research_hypotheses`

Stores market/product-direction hypotheses Oleg wants to test against historical chat demand.

Key fields:

- `id`
- `title`
- `description`
- `status`: `draft`, `active_research`, `promising`, `approved_direction`, `rejected`, `parked`
- `created_by`
- `created_at`
- `updated_at`
- `settings_json`

Examples:

- "роботы-газонокосилки"
- "вертикальная гидропоника как отдельный продукт"
- "новая категория камер/датчиков/оборудования"

### `research_terms`

Stores seed and expanded terms for a research hypothesis.

Key fields:

- `id`
- `research_hypothesis_id`
- `term`
- `term_type`: `seed`, `expanded`, `negative`, `brand`, `problem`, `intent_phrase`
- `source`: `manual`, `ai_expansion`, `catalog`, `feedback`
- `weight`
- `status`: `active`, `muted`, `rejected`
- `created_at`

### `research_runs`

Stores concrete retro research scans.

Key fields:

- `id`
- `research_hypothesis_id`
- `status`: `queued`, `running`, `completed`, `failed`, `cancelled`
- `message_scope`: `saved_messages_only`, `temporary_backfill`, `mixed`
- `source_scope`: `all`, `selected_sources`, `high_priority_only`
- `selected_monitored_source_ids_json`
- `history_depth_days`
- `history_start_message_id`
- `history_end_message_id`
- `max_messages`
- `use_ai_term_expansion`
- `use_full_catalog_context`
- `create_leads_automatically`
- `create_contact_reasons_automatically`
- `min_confidence`
- `started_at`
- `finished_at`
- `stats_json`
- `created_by`
- `created_at`

Rules:

- By default, research produces a web report, not live Telegram leads.
- Temporary backfill is configurable and must respect Telegram rate limits.
- Research backfill must not move normal monitoring checkpoints unless explicitly configured.

### `research_matches`

Stores messages found by a research run.

Key fields:

- `id`
- `research_run_id`
- `source_message_id`
- `monitored_source_id`
- `raw_source_id`
- `telegram_message_id`
- `sender_id`
- `matched_terms_json`
- `decision`: `strong_intent`, `weak_intent`, `discussion`, `not_relevant`, `unknown`
- `confidence`
- `intent_type`
- `reason`
- `context_message_ids_json`
- `created_lead_event_id`
- `created_lead_cluster_id`
- `created_contact_reason_id`
- `created_at`

Rules:

- Research matches use `source_message_id` when the message exists in the hot DB.
- Temporary backfill can create a `source_messages` stub before storing the match so later conversion, feedback, and archive restore use the same identity model.

### `research_reports`

Stores aggregate research results.

Key fields:

- `id`
- `research_run_id`
- `summary`
- `unique_senders_count`
- `strong_intent_count`
- `weak_intent_count`
- `discussion_count`
- `top_sources_json`
- `top_terms_json`
- `brands_or_competitors_json`
- `pain_points_json`
- `sample_message_ids_json`
- `recommendation`: `promising`, `weak_signal`, `not_promising`, `needs_more_data`
- `created_at`

Purpose:

- Help Oleg decide if a new direction is worth adding to the catalog or testing commercially.

### `research_conversions`

Stores actions taken from research results.

Key fields:

- `id`
- `research_hypothesis_id`
- `research_run_id`
- `conversion_type`: `catalog_category`, `catalog_item`, `catalog_term`, `lead_event`, `lead_cluster`, `client_interest`, `contact_reason`, `manual_note`
- `target_entity_type`
- `target_entity_id`
- `created_by`
- `created_at`

### `feedback_events`

Stores all Oleg/admin feedback.

Key fields:

- `id`
- `target_type`: `lead_cluster`, `lead_event`, `lead_match`, `source_message`, `sender_profile`, `catalog_item`, `catalog_term`, `category`, `source`, `manual_input`, `client`, `contact`, `client_object`, `client_interest`, `client_asset`, `opportunity`, `support_case`, `contact_reason`, `task`
- `target_id`
- `action`
- `reason_code`
- `feedback_scope`: `classifier`, `catalog`, `clustering`, `crm_outcome`, `source_quality`, `manual_example`, `none`
- `learning_effect`: `positive_example`, `negative_example`, `match_correction`, `term_weight_down`, `term_review`, `sender_role_hint`, `cluster_training`, `source_quality_signal`, `no_classifier_learning`
- `application_status`: `recorded`, `queued`, `applied`, `needs_review`, `ignored`
- `applied_entity_type`
- `applied_entity_id`
- `applied_at`
- `comment`
- `created_by`
- `created_at`
- `metadata_json`

Initial action set:

- `lead_confirmed`
- `not_lead`
- `maybe`
- `duplicate`
- `snooze`
- `take_into_work`
- `correct_match`
- `wrong_category`
- `wrong_item`
- `wrong_product_or_term`
- `approve_item`
- `reject_item`
- `mute_item`
- `approve_term`
- `reject_term`
- `mute_term`
- `term_too_broad`
- `expert_not_customer`
- `expert_or_advice`
- `no_buying_intent`
- `not_our_topic`
- `diy_only`
- `too_cheap_or_free`
- `spam_or_noise`
- `old_irrelevant`
- `commercial_no_answer`
- `commercial_too_expensive`
- `commercial_bought_elsewhere`
- `commercial_postponed`
- `commercial_not_region`
- `source_outdated`
- `source_wrong`
- `manual_positive_example`
- `manual_negative_example`
- `merge_clusters`
- `split_cluster`
- `mark_context_only`
- `set_primary_message`
- `mark_duplicate_cluster`
- `create_client`
- `create_interest`
- `create_asset`
- `contact_reason_done`
- `contact_reason_dismissed`
- `contact_reason_snoozed`
- `support_needed`
- `support_done`

The UI can expose a small button set at first while the DB supports richer feedback.

Rules:

- `not_lead` requires a `reason_code`.
- Commercial outcomes use `feedback_scope = crm_outcome` and `learning_effect = no_classifier_learning` by default.
- Classifier feedback should target the narrowest object that caused the error.
- Feedback may create review tasks instead of mutating catalog/terms immediately.

### `crm_conversion_candidates`

Stores proposed CRM records extracted from a lead cluster.

Key fields:

- `id`
- `lead_cluster_id`
- `lead_event_id`
- `candidate_type`: `client_candidate`, `contact_candidate`, `object_candidate`, `interest_candidate`, `opportunity_candidate`, `support_case_candidate`, `contact_reason_candidate`, `task_candidate`
- `extracted_json`
- `display_summary`
- `confidence`
- `status`: `proposed`, `accepted`, `rejected`, `edited`, `converted`, `superseded`
- `created_by`: `system`, `oleg`, `admin`
- `created_entity_type`
- `created_entity_id`
- `reviewed_by`
- `reviewed_at`
- `created_at`
- `updated_at`

Rules:

- Candidates do not become CRM records until accepted or edited by Oleg/admin.
- Candidates can be regenerated when the cluster summary, catalog match, or prompt version changes.
- Rejected candidates remain as training/audit data.

### `crm_conversion_actions`

Stores the conversion of a lead cluster into CRM/work entities.

Key fields:

- `id`
- `lead_cluster_id`
- `action_type`: `create_task`, `create_client`, `link_client`, `create_contact`, `create_object`, `create_interest`, `create_opportunity`, `create_support_case`, `create_contact_reason`, `close_without_conversion`
- `used_candidate_ids_json`
- `created_entity_type`
- `created_entity_id`
- `linked_client_id`
- `linked_contact_id`
- `manual_changes_json`
- `next_step`
- `next_step_at`
- `created_by`
- `created_at`

Purpose:

- Keep an audit trail of what was created from a cluster.
- Distinguish automatic suggestions from confirmed CRM memory.
- Let one cluster create multiple CRM/work records when appropriate.

Rules:

- A cluster becomes `converted` after a primary CRM/work entity is created: `client_interest`, `opportunity`, `support_case`, `contact_reason`, or `client + task`.
- Creating only the default contact task from `Take into work` does not mark the cluster as `converted`.
- Duplicate checks must run before creating new clients/contacts.

### `clients`

Stores client accounts. A client can be a person, family, company, cottage settlement, HOA/TSN, residential complex, or unknown entity.

Key fields:

- `id`
- `client_type`: `person`, `family`, `company`, `cottage_settlement`, `hoa_tsn`, `residential_complex`, `unknown`
- `display_name`
- `status`: `active`, `archived`, `do_not_contact`
- `source_type`: `manual`, `lead`, `import`
- `source_id`
- `owner_user_id`
- `assignee_user_id`
- `notes`
- `created_at`
- `updated_at`

Rules:

- `owner_user_id` and `assignee_user_id` are stored now but hidden in the first UI because the first version uses a single admin workflow.
- `do_not_contact` suppresses generated contact reasons and Telegram reminders.

### `contacts`

Stores contact methods and people linked to clients.

Key fields:

- `id`
- `client_id`
- `contact_name`
- `telegram_user_id`
- `telegram_username`
- `phone`
- `email`
- `whatsapp`
- `preferred_channel`: `telegram`, `phone`, `whatsapp`, `email`, `unknown`
- `source_type`: `manual`, `lead`, `import`
- `source_id`
- `is_primary`
- `notes`
- `created_at`
- `updated_at`

Rules:

- A client can have multiple contacts.
- A lead can create a contact candidate, but attaching it to a client is manual or a confirmed action.

### `client_objects`

Stores the physical or business object associated with a client.

Key fields:

- `id`
- `client_id`
- `object_type`: `apartment`, `house`, `dacha`, `cottage_settlement`, `office`, `retail`, `warehouse`, `production`, `unknown`
- `name`
- `location_text`
- `project_stage`: `design`, `construction`, `renovation`, `operation`, `unknown`
- `notes`
- `created_at`
- `updated_at`

Examples:

- "дача в Ногинске"
- "квартира под аренду"
- "КП с въездной группой"
- "склад/производство"

### `client_interests`

Stores what the client wanted, asked about, could not find, postponed, rejected, or bought elsewhere.

Key fields:

- `id`
- `client_id`
- `client_object_id`
- `category_id`
- `catalog_item_id`
- `catalog_term_id`
- `interest_text`
- `interest_status`: `interested`, `postponed`, `not_found`, `too_expensive`, `bought_elsewhere`, `already_has`, `unknown`, `closed`
- `source_type`: `lead`, `manual`, `support`, `import`
- `source_id`
- `last_seen_at`
- `next_check_at`
- `notes`
- `created_at`
- `updated_at`

Purpose:

- Preserve old demand even when it did not become a sale.
- Let new catalog items/offers reactivate old conversations.

Example:

- Client asked for a Wi-Fi camera for a dacha, but no suitable model was available. Later a new Dahua model or 4G camera bundle appears, creating a contact reason.

### `client_assets`

Stores what the client already bought, installed, or operates.

Key fields:

- `id`
- `client_id`
- `client_object_id`
- `category_id`
- `catalog_item_id`
- `asset_name`
- `asset_status`: `planned`, `installed`, `active`, `needs_service`, `retired`, `unknown`
- `installed_at`
- `warranty_until`
- `service_due_at`
- `source_type`: `manual`, `lead`, `support`, `import`
- `source_id`
- `notes`
- `created_at`
- `updated_at`

Purpose:

- Support repeat sales, upgrades, maintenance, warranty follow-up, and compatibility checks.

### `opportunities`

Stores lightweight commercial opportunities. This is intentionally simpler than a full sales pipeline.

Key fields:

- `id`
- `client_id`
- `client_object_id`
- `source_lead_cluster_id`
- `source_lead_event_id`
- `primary_category_id`
- `title`
- `status`: `new`, `qualified`, `contacted`, `proposal`, `won`, `lost`, `not_lead`, `snoozed`
- `lost_reason`: `no_intent`, `not_our_topic`, `too_far`, `too_small`, `too_expensive`, `competitor`, `no_response`, `duplicate`, `other`
- `estimated_value`
- `currency`
- `owner_user_id`
- `assignee_user_id`
- `next_step`
- `next_step_at`
- `created_at`
- `updated_at`
- `closed_at`

Rules:

- A lead does not have to become an opportunity.
- Oleg can create an opportunity from a lead cluster, lead event, client interest, contact reason, or manual note.
- The first UI should not expose complex team assignment even though fields exist.

### `support_cases`

Stores support and service interactions.

Key fields:

- `id`
- `client_id`
- `client_object_id`
- `client_asset_id`
- `source_lead_cluster_id`
- `source_lead_event_id`
- `title`
- `status`: `new`, `in_progress`, `waiting_client`, `resolved`, `closed`
- `priority`: `low`, `normal`, `high`, `urgent`
- `issue_text`
- `resolution_text`
- `owner_user_id`
- `assignee_user_id`
- `created_at`
- `updated_at`
- `closed_at`

Purpose:

- Keep support history tied to client assets.
- Generate follow-up reasons after support or maintenance.

### `contact_reasons`

Stores reasons to contact a client. This is a central CRM object for PUR.

Key fields:

- `id`
- `client_id`
- `contact_id`
- `client_object_id`
- `client_interest_id`
- `client_asset_id`
- `catalog_item_id`
- `catalog_offer_id`
- `catalog_attribute_id`
- `source_id`
- `source_lead_cluster_id`
- `source_lead_event_id`
- `reason_type`: `new_matching_product`, `new_matching_offer`, `support_followup`, `maintenance_due`, `warranty_followup`, `upgrade_available`, `price_change`, `seasonal`, `catalog_reactivation`, `manual`
- `title`
- `reason_text`
- `priority`: `low`, `normal`, `high`
- `status`: `new`, `accepted`, `dismissed`, `done`, `snoozed`
- `due_at`
- `snoozed_until`
- `created_at`
- `updated_at`

Examples:

- A client previously wanted a dacha Wi-Fi camera. A new 4G router + camera bundle appears.
- A client has a camera/NVR installation and service is due.
- Dahua prices are about to increase and an old quote can be reactivated.
- A new AirShield/security offer matches a rental-apartment protection interest.

### `touchpoints`

Stores history of interactions with a client.

Key fields:

- `id`
- `client_id`
- `contact_id`
- `opportunity_id`
- `support_case_id`
- `contact_reason_id`
- `lead_cluster_id`
- `lead_event_id`
- `channel`: `telegram`, `phone`, `whatsapp`, `email`, `meeting`, `other`
- `direction`: `inbound`, `outbound`, `internal_note`
- `summary`
- `outcome`
- `next_step`
- `created_by`
- `created_at`

Purpose:

- Keep the client memory lightweight but useful.

### `tasks`

Stores simple reminders.

Key fields:

- `id`
- `client_id`
- `lead_cluster_id`
- `lead_event_id`
- `opportunity_id`
- `support_case_id`
- `contact_reason_id`
- `title`
- `description`
- `status`: `open`, `done`, `cancelled`, `snoozed`
- `priority`: `low`, `normal`, `high`
- `due_at`
- `owner_user_id`
- `assignee_user_id`
- `created_at`
- `updated_at`
- `completed_at`

Rules:

- First UI shows tasks as Oleg's personal reminders.
- Assignment fields exist for later team expansion.

### `evaluation_datasets`

Stores named quality datasets.

Key fields:

- `id`
- `name`
- `dataset_type`: `golden`, `feedback_regression`, `retro_research`, `catalog_extraction`, `notification_policy`, `crm_conversion`
- `description`
- `status`: `active`, `archived`, `draft`
- `created_by`
- `created_at`
- `updated_at`

Purpose:

- Keep stable samples for measuring classifier/catalog/notification quality.
- Separate hand-labeled golden sets from automatically collected feedback cases.

### `evaluation_cases`

Stores expected outcomes for quality checks.

Key fields:

- `id`
- `evaluation_dataset_id`
- `source_message_id`
- `lead_cluster_id`
- `lead_event_id`
- `source_id`
- `message_text`
- `context_json`
- `expected_decision`: `lead`, `maybe`, `not_lead`
- `expected_category_id`
- `expected_catalog_item_ids_json`
- `expected_reason_code`
- `expected_notification_policy`: `immediate`, `digest`, `web_only`, `suppressed`
- `expected_cluster_behavior`: `new_cluster`, `merge`, `context_only`, `split`
- `expected_crm_candidate_json`
- `label_source`: `manual`, `feedback`, `import`, `synthetic`
- `created_by`
- `created_at`
- `updated_at`

Rules:

- Feedback can promote real mistakes into regression cases.
- Evaluation cases should keep enough context to reproduce the decision.

### `evaluation_runs`

Stores evaluation executions against a classifier/catalog/prompt version.

Key fields:

- `id`
- `evaluation_dataset_id`
- `run_type`: `lead_detection`, `catalog_extraction`, `notification_policy`, `clustering`, `crm_conversion`, `full_pipeline`
- `classifier_version_id`
- `catalog_hash`
- `prompt_hash`
- `model`
- `settings_hash`
- `status`: `queued`, `running`, `completed`, `failed`, `cancelled`
- `started_at`
- `finished_at`
- `metrics_json`
- `error`
- `created_by`
- `created_at`

### `evaluation_results`

Stores per-case evaluation output.

Key fields:

- `id`
- `evaluation_run_id`
- `evaluation_case_id`
- `actual_decision`
- `actual_category_id`
- `actual_catalog_item_ids_json`
- `actual_notification_policy`
- `actual_cluster_behavior`
- `actual_crm_candidate_json`
- `passed`
- `failure_type`: `false_positive`, `false_negative`, `wrong_category`, `wrong_item`, `wrong_notification`, `wrong_cluster`, `wrong_crm_candidate`, `parse_error`, `other`
- `details_json`
- `created_at`

### `quality_metric_snapshots`

Stores aggregate quality metrics over time.

Key fields:

- `id`
- `scope`: `overall`, `source`, `category`, `model`, `classifier_version`, `notification_policy`, `catalog_extraction`
- `scope_id`
- `period_start`
- `period_end`
- `precision`
- `recall`
- `f1`
- `false_positive_count`
- `false_negative_count`
- `maybe_count`
- `maybe_resolution_rate`
- `high_value_precision`
- `retro_precision`
- `telegram_notification_precision`
- `catalog_candidate_accept_rate`
- `catalog_candidate_reject_rate`
- `feedback_count`
- `metrics_json`
- `created_at`

Purpose:

- Show whether lead quality is improving or degrading after catalog/prompt/setting changes.
- Let admin compare model/prompt/classifier versions.

### `secret_refs`

Stores references to secrets without exposing secret values.

Key fields:

- `id`
- `secret_type`: `telegram_session`, `telegram_api`, `ai_api_key`, `web_session_secret`, `bootstrap_admin_password`, `archive_s3_credentials`, `other`
- `display_name`
- `storage_backend`: `env`, `file`, `system_keyring`, `external_secret_manager`
- `storage_ref`
- `status`: `active`, `rotating`, `revoked`, `missing`
- `last_rotated_at`
- `last_checked_at`
- `created_at`
- `updated_at`

Rules:

- Secret values are never stored in SQLite plaintext.
- UI/logs may show display name and status, not the value.
- Rotation and failed secret checks are audited.

### `backup_runs`

Stores backup job metadata.

Key fields:

- `id`
- `backup_type`: `sqlite`, `archives`, `artifacts`, `sessions`, `config`, `secrets_manifest`, `full`
- `storage_backend`: `local`, `s3_compatible`
- `storage_uri`
- `status`: `queued`, `running`, `completed`, `failed`, `verified`, `expired`
- `started_at`
- `finished_at`
- `size_bytes`
- `sha256`
- `manifest_json`
- `error`
- `created_at`

Rules:

- SQLite backup must use a consistent backup/snapshot mechanism, not a raw copy of a live database.
- Backup artifacts must be verified before old backups are expired.
- Telegram sessions are not backed up by default.
- Session/secret-value backup requires an explicit encrypted local backup policy and a configured encryption secret reference.
- Config and secret manifests can be backed up without raw secret values.

### `restore_runs`

Stores restore attempts and validation.

Key fields:

- `id`
- `backup_run_id`
- `restore_type`: `sqlite`, `archives`, `artifacts`, `sessions`, `config`, `full`, `dry_run`
- `status`: `queued`, `running`, `completed`, `failed`, `cancelled`
- `target_path`
- `validation_status`: `not_checked`, `passed`, `failed`
- `validation_details_json`
- `started_at`
- `finished_at`
- `error`
- `created_by`
- `created_at`

Rules:

- Restore should support dry-run validation.
- Restore actions are admin-only and audited.
- Full restore must include post-restore health checks.

### `settings`

Stores configurable behavior.

Key fields:

- `id`
- `key`
- `value_json`
- `value_type`: `bool`, `int`, `float`, `string`, `json`, `secret_ref`
- `scope`: `global`, `userbot_account`, `monitored_source`, `ai_provider`, `ai_model`, `notification`, `archive`, `backup`
- `scope_id`
- `description`
- `requires_restart`
- `is_secret_ref`
- `updated_by`
- `updated_at`

Rules:

- Settings are versioned and audited.
- Secret values are represented through `secret_refs`, not stored directly.
- Runtime workers should read settings through one typed settings layer so web changes, scheduler behavior, and prompt building stay consistent.
- Empty-bootstrap rule: no settings row is created during reset/startup except those explicitly changed by an administrator. Built-in defaults are read-only fallback behavior until the administrator saves an override.

### `settings_revisions`

Stores immutable setting-change history.

Key fields:

- `id`
- `setting_key`
- `scope`
- `scope_id`
- `old_value_hash`
- `new_value_hash`
- `old_value_json`
- `new_value_json`
- `changed_by`
- `change_reason`
- `created_at`

Purpose:

- Reconstruct behavior for classifier/evaluation runs.
- Explain why notifications, archive policy, or source behavior changed.

### Default Settings

- `auto_add_catalog_items = true`
- `auto_add_terms = true`
- `auto_add_attributes = true`
- `catalog_candidates_enabled = true`
- `catalog_candidate_auto_create_operational_rows = true`
- `catalog_candidate_low_confidence_threshold = 0.55`
- `catalog_candidate_auto_pending_threshold = 0.70`
- `catalog_candidate_conflict_status = "needs_review"`
- `catalog_candidate_price_status_default = "needs_review"`
- `catalog_candidate_offer_requires_ttl = true`
- `catalog_candidate_too_broad_term_status = "needs_review"`
- `catalog_candidate_merge_similarity_threshold = 0.85`
- `manual_catalog_add_enabled = true`
- `manual_catalog_create_candidate_first = true`
- `manual_catalog_default_status_for_admin = "approved"`
- `manual_catalog_requires_evidence_note = true`
- `manual_catalog_allow_direct_approved = true`
- `web_manual_forward_import_enabled = true`
- `telegram_manual_forward_input_enabled = false`
- `use_auto_pending_in_classifier = true`
- `use_needs_review_in_classifier = false`
- `download_documents = true`
- `download_video = false`
- `download_photos = false`
- `fetch_telegraph_pages = true`
- `fetch_external_pages = true`
- `external_fetch_allowed_domains_json = ["telegra.ph"]`
- `notify_catalog_candidates = true`
- `notify_leads = true`
- `notify_live_leads = true`
- `notify_maybe = false`
- `notify_retro_leads = false`
- `notify_reclassification_leads = false`
- `notify_high_value_low_confidence = true`
- `high_value_maybe_notify_exception = true`
- `lead_notify_min_confidence = 0.70`
- `lead_notify_high_value_min_confidence = 0.45`
- `commercial_value_scoring_enabled = true`
- `high_value_notify_enabled = true`
- `high_value_notify_threshold = 0.75`
- `high_value_negative_score_max = 0.35`
- `high_value_requires_human_review = true`
- `high_value_categories_json = []`
- `high_value_source_priorities_json = ["high", "normal"]`
- `high_value_signals_json = ["whole_object", "turnkey", "installer_needed", "project_or_estimate", "multiple_systems", "urgent", "quantity", "b2b_or_hoa", "known_client"]`
- `negative_value_signals_json = ["expert_advice", "diy_only", "free_or_too_cheap", "not_commercial", "already_solved_elsewhere"]`
- `lead_notify_categories_json = []`
- `lead_notify_source_priorities_json = ["high", "normal"]`
- `lead_notify_duplicate_suppression_window_hours = 24`
- `lead_clustering_enabled = true`
- `lead_cluster_window_minutes = 60`
- `lead_cluster_same_sender_required = false`
- `lead_cluster_allow_reply_merge = true`
- `lead_cluster_allow_topic_merge = true`
- `lead_cluster_allow_ai_continuation_signal = true`
- `lead_cluster_similarity_threshold = 0.75`
- `lead_cluster_manual_merge_required_for_cross_sender = true`
- `lead_cluster_notify_on_update = false`
- `lead_cluster_notify_update_min_value_delta = 0.20`
- `lead_cluster_update_cooldown_minutes = 60`
- `lead_cluster_split_requires_reason = true`
- `notify_ai_errors = true`
- `telegram_notify_auto_pending_confidence = true`
- `telegram_auto_pending_label = "auto_pending"`
- `telegram_notification_cooldown_minutes = 15`
- `telegram_error_repeat_threshold = 3`
- `telegram_error_repeat_window_minutes = 30`
- `telegram_digest_enabled = true`
- `telegram_digest_times_json = ["09:00", "18:00"]`
- `telegram_digest_timezone = "Europe/Moscow"`
- `telegram_digest_include_catalog_candidates = true`
- `telegram_digest_include_maybe = true`
- `telegram_digest_include_contact_reasons = true`
- `telegram_digest_include_source_errors = true`
- `auto_expire_campaign_prices = true`
- `default_campaign_price_ttl_days = 30`
- `default_offer_ttl_days = 30`
- `active_web_roles_json = ["admin"]`
- `future_web_roles_enabled = false`
- `bootstrap_admin_enabled = true`
- `bootstrap_admin_username = "admin"`
- `bootstrap_admin_password_change_required = true`
- `telegram_admin_add_enabled = true`
- `telegram_admin_only_after_bootstrap = true`
- `feedback_not_lead_requires_reason = true`
- `feedback_default_scope_for_work_outcomes = "crm_outcome"`
- `feedback_work_outcomes_affect_classifier = false`
- `feedback_term_too_broad_creates_review = true`
- `feedback_wrong_match_creates_catalog_review = true`
- `feedback_expert_reason_updates_sender_profile = true`
- `feedback_context_only_updates_clustering = true`
- `feedback_wrong_merge_updates_clustering = true`
- `feedback_auto_apply_catalog_mutations = false`
- `feedback_reason_codes_json = ["no_buying_intent", "expert_or_advice", "not_our_topic", "wrong_category", "wrong_product_or_term", "term_too_broad", "diy_only", "too_cheap_or_free", "spam_or_noise", "old_irrelevant", "context_only", "wrong_merge"]`
- `telegram_auth_enabled = true`
- `crm_enabled = true`
- `crm_auto_create_client_from_confirmed_lead = false`
- `crm_auto_create_interest_from_manual_note = true`
- `crm_auto_create_contact_reasons = true`
- `crm_contact_reasons_include_auto_pending_catalog = true`
- `crm_generate_conversion_candidates = true`
- `crm_auto_convert_candidates = false`
- `crm_conversion_wizard_enabled = true`
- `crm_conversion_candidate_types_json = ["client_candidate", "contact_candidate", "object_candidate", "interest_candidate", "opportunity_candidate", "support_case_candidate", "contact_reason_candidate", "task_candidate"]`
- `crm_conversion_require_confirmation = true`
- `crm_conversion_mark_cluster_converted_on_task_only = false`
- `crm_conversion_duplicate_check_enabled = true`
- `crm_duplicate_check_telegram_user_id = true`
- `crm_duplicate_check_username = true`
- `crm_duplicate_check_phone = true`
- `crm_duplicate_check_name_similarity = true`
- `crm_duplicate_check_object_interest_similarity = true`
- `crm_show_assignee_fields = false`
- `crm_default_contact_reason_ttl_days = 30`
- `telegram_worker_count = 1`
- `telegram_default_userbot_account_id = null`
- `telegram_add_userbot_accounts_enabled = true`
- `telegram_read_jobs_per_userbot = 1`
- `telegram_flood_sleep_threshold_seconds = 60`
- `telegram_get_history_wait_seconds = 1`
- `telegram_access_issue_retry_threshold = 3`
- `telegram_access_issue_retry_window_minutes = 30`
- `telegram_access_issue_repeat_notification_cooldown_minutes = 180`
- `source_add_requires_preview = true`
- `source_default_purpose = "lead_monitoring"`
- `source_default_start_mode = "from_now"`
- `source_preview_message_count = 20`
- `source_preview_download_attachments = false`
- `source_backfill_default_policy = "retro_web_only"`
- `source_backfill_notify_telegram = false`
- `source_allow_both_purpose = false`
- `source_reset_checkpoint_requires_confirmation = true`
- `source_default_poll_interval_seconds = 60`
- `lead_monitoring_public_groups_enabled = true`
- `lead_monitoring_private_groups_enabled = false`
- `lead_monitoring_channels_enabled = false`
- `lead_monitoring_comments_enabled = false`
- `lead_monitoring_dms_enabled = false`
- `catalog_ingestion_channels_enabled = true`
- `catalog_ingestion_pur_channel_enabled = true`
- `catalog_ingestion_external_pages_enabled = true`
- `ai_parse_max_parallel_jobs = 2`
- `ai_provider_policy_warning_enabled = true`
- `ai_default_provider_key = "zai"`
- `ai_registry_auto_bootstrap_enabled = false`
- `ai_registry_load_defaults_requires_admin_action = true`
- `ai_default_provider_account_id = null`
- `ai_model_concurrency_utilization_ratio = 0.8`
- `ai_model_concurrency_default_limit = 1`
- `ai_model_concurrency_lease_seconds = 180`
- `ai_model_registry_seed_enabled = true`
- `ai_agent_catalog_extractor_enabled = true`
- `ai_agent_catalog_extractor_strategy = "primary_fallback"`
- `ai_agent_catalog_extractor_routes = [{"model":"GLM-5.1","role":"primary"},{"model":"GLM-4.5-Air","role":"fallback"}]`
- `ai_agent_lead_detector_enabled = true`
- `ai_agent_lead_detector_strategy = "fuzzy_primary_llm_shadow"`
- `ai_agent_lead_detector_routes = [{"model":"builtin-fuzzy","role":"primary"},{"model":"GLM-4.5-Flash","role":"shadow"}]`
- `ai_agent_ocr_extractor_enabled = true`
- `ai_agent_ocr_extractor_strategy = "primary_fallback"`
- `ai_agent_ocr_extractor_routes = [{"model":"GLM-OCR","role":"primary"}]`
- `ai_agent_route_fallback_on_rate_limit = true`
- `ai_agent_route_fallback_on_invalid_output = true`
- `ai_agent_shadow_writes_side_effects = false`
- `ai_batching_strategy = "source_time_window"`
- `ai_batch_max_messages = 20`
- `ai_batch_max_prompt_tokens = 60000`
- `ai_batch_max_text_chars = 50000`
- `ai_batch_max_wait_seconds = 60`
- `ai_batch_group_by_source = true`
- `ai_batch_group_by_thread = true`
- `ai_batch_include_reply_context = true`
- `ai_batch_context_before = 3`
- `ai_batch_context_after = 1`
- `ai_batch_reply_depth = 2`
- `ai_batch_allow_cross_source = false`
- `ai_batch_priority_high_max_wait_seconds = 15`
- `ai_batch_priority_low_max_wait_seconds = 180`
- `reclass_enabled = true`
- `reclass_on_catalog_change = true`
- `reclass_on_prompt_change = true`
- `reclass_on_feedback_change = true`
- `reclass_window_days = 30`
- `reclass_max_messages_per_run = 1000`
- `reclass_include_previous_not_leads = true`
- `reclass_include_maybe = true`
- `reclass_include_leads = false`
- `reclass_include_unclassified = true`
- `reclass_sources_scope = "all"`
- `reclass_only_if_catalog_categories_changed = true`
- `reclass_only_messages_with_term_overlap = false`
- `reclass_schedule_mode = "queued"`
- `reclass_debounce_minutes = 30`
- `reclass_nightly_time = "03:00"`
- `reclass_priority = "low"`
- `reclass_respect_rate_limits = true`
- `reclass_create_new_lead_events = true`
- `reclass_preserve_original_decision = true`
- `reclass_notify_new_leads = false`
- `reclass_notify_changed_to_maybe = false`
- `reclass_notify_changed_to_not_lead = false`
- `reclass_require_review_before_notify = false`
- `research_enabled = true`
- `research_default_message_scope = "saved_messages_only"`
- `research_allow_temporary_backfill = true`
- `research_backfill_moves_monitoring_checkpoints = false`
- `research_default_history_depth_days = 180`
- `research_default_source_scope = "selected_sources"`
- `research_max_messages_per_run = 5000`
- `research_use_ai_term_expansion = true`
- `research_use_full_catalog_context = false`
- `research_create_leads_automatically = false`
- `research_create_contact_reasons_automatically = false`
- `research_min_confidence = 0.65`
- `research_notify_summary_to_telegram = true`
- `research_retro_leads_are_web_first = true`
- `research_retro_lead_telegram_label = "retro"`
- `embeddings_enabled = false`
- `embed_new_messages = false`
- `embed_parsed_chunks = false`
- `embed_catalog_items = false`
- `embedding_default_provider_account_id = null`
- `embedding_default_model = null`
- `embedding_max_parallel_jobs = 1`
- `retention_enabled = true`
- `archive_enabled = true`
- `archive_storage_backend = "local"`
- `archive_s3_enabled = false`
- `archive_s3_bucket = null`
- `archive_s3_endpoint = null`
- `archive_s3_region = null`
- `archive_s3_prefix = null`
- `archive_path = "artifacts/archives"`
- `archive_format = "parquet_zstd"`
- `archive_fallback_format = "jsonl_zstd"`
- `archive_compression = "zstd"`
- `archive_rotate_by = "month"`
- `archive_max_segment_size_mb = 512`
- `archive_hot_messages_retention_days = 365`
- `archive_hot_operational_events_retention_days = 90`
- `archive_hot_ai_usage_retention_days = 180`
- `archive_hot_research_matches_retention_days = 365`
- `archive_hot_embeddings_retention_days = 365`
- `archive_hot_db_max_size_mb = 2048`
- `archive_tables_json = ["source_messages", "parsed_chunks", "operational_events", "ai_usage_events", "notification_events", "job_runs", "research_matches", "embeddings"]`
- `archive_verify_after_write = true`
- `archive_trim_payloads_after_verify = true`
- `archive_delete_unreferenced_hot_rows_after_verify = false`
- `archive_keep_hot_pointers = true`
- `archive_keep_identity_stub_rows = true`
- `archive_auto_restore_for_reclassification = false`
- `archive_auto_restore_for_research = false`
- `archive_restore_requires_manual_confirmation = true`
- `quality_evaluation_enabled = true`
- `quality_auto_create_regression_cases_from_feedback = true`
- `quality_golden_set_required_before_prompt_change = true`
- `quality_run_on_catalog_change = true`
- `quality_run_on_prompt_change = true`
- `quality_run_on_model_change = true`
- `quality_min_precision_threshold = 0.80`
- `quality_min_recall_threshold = 0.60`
- `quality_track_maybe_resolution = true`
- `quality_track_high_value_precision = true`
- `quality_track_retro_precision = true`
- `quality_track_notification_precision = true`
- `quality_dashboard_enabled = true`
- `backup_enabled = true`
- `backup_storage_backend = "local"`
- `backup_path = "artifacts/backups"`
- `backup_sqlite_enabled = true`
- `backup_archives_enabled = true`
- `backup_artifacts_enabled = true`
- `backup_sessions_enabled = false`
- `backup_config_enabled = true`
- `backup_secrets_manifest_enabled = true`
- `backup_secret_values_enabled = false`
- `backup_encryption_required_for_secrets = true`
- `backup_encryption_secret_ref_id = null`
- `backup_schedule_cron = "0 3 * * *"`
- `backup_retention_days = 30`
- `backup_verify_after_write = true`
- `restore_dry_run_required = true`
- `secrets_never_log_values = true`
- `secrets_mask_in_ui = true`
- `secret_rotation_audit_enabled = true`
- `first_release_scope = "full_spec"`

Settings are editable in the web interface and versioned through both `settings_revisions` and `audit_log`.

### `web_users`

Stores users allowed into the web interface.

Key fields:

- `id`
- `telegram_user_id`
- `telegram_username`
- `display_name`
- `auth_type`: `local`, `telegram`
- `local_username`
- `password_hash`
- `must_change_password`
- `role`: `admin`
- `status`: `active`, `disabled`, `pending`
- `created_at`
- `updated_at`
- `last_login_at`

Rules:

- First implementation has only one active role: `admin`.
- A built-in local `admin` user is seeded for bootstrap.
- The built-in admin can add Telegram accounts with role `admin`.
- Telegram-authenticated users cannot log in until their Telegram user id is added by an existing admin.
- More specific roles such as catalog manager, lead reviewer, and viewer are a future expansion, not part of the first UI.
- Disabled users cannot log in even if local password or Telegram authentication succeeds.

### `web_auth_sessions`

Stores web sessions created after successful local or Telegram web login.

Key fields:

- `id`
- `user_id`
- `auth_method`: `local`, `telegram`
- `session_token_hash`
- `created_at`
- `expires_at`
- `last_seen_at`
- `ip_address`
- `user_agent`
- `revoked_at`

Rules:

- Store only a hash of the session token.
- Session duration is configurable.
- Revoking a user revokes active sessions.

### `audit_log`

Stores user/system state changes. This is separate from `operational_events`: audit answers "who changed what"; operational events answer "what happened while the system was running".

Key fields:

- `id`
- `actor`
- `action`
- `entity_type`
- `entity_id`
- `old_value_json`
- `new_value_json`
- `created_at`

## Manual Oleg Input

Oleg must be able to add information in several ways:

1. Paste a Telegram message link.
2. Paste or upload forwarded-message content in the web UI.
3. Paste raw text into the web UI.
4. Add a catalog note manually, such as "Dahua X is ours" or "do not treat this as a lead".
5. Mark an existing lead as a good/bad example.
6. Add a client, client interest, installed asset, support note, or contact reminder manually.

### Telegram Link Flow

```text
Oleg pastes t.me/chat/message
  -> manual_inputs row
  -> userbot fetches message
  -> sources row created
  -> parsed_chunks row created
  -> optional lead_event and lead_cluster created as manual example
  -> feedback_events row records Oleg intent
```

The UI should ask what kind of manual input this is:

- positive lead example;
- negative lead example;
- catalog fact;
- client/contact note;
- client interest;
- installed asset;
- support case;
- contact reminder;
- source to parse;
- unclear / process automatically.

### Forwarded Message Flow

First-phase forwarded-message input is web-only. Oleg/admin can paste forwarded text, an exported message block, or a Telegram message link into the web UI. If the original source chat and message id can be resolved, the userbot fetches the original message to preserve link and metadata.

Telegram-bot forwarding is represented as a future optional input and is disabled by default through `telegram_manual_forward_input_enabled = false`.

### Manual Text Flow

Manual text becomes `source_type = manual_text`. It can still create extracted facts, lead examples, CRM notes, client interests, support cases, contact reasons, or feedback.

## Source Onboarding And Monitoring

Monitoring sources are managed in the web interface. Telegram commands are not used for adding chats.

Recommended add-source flow:

1. Oleg opens `Sources -> Add Telegram source`.
2. Oleg pastes `@username`, `t.me/...`, invite link, or a link to a specific message.
3. Oleg selects source purpose:
   - `lead_monitoring`: search for leads;
   - `catalog_ingestion`: extract catalog knowledge;
   - `both`: represented in the schema, but can be hidden in the first UI.
4. Oleg selects start mode:
   - `from_now` by default;
   - recent N messages;
   - recent N days;
   - from a specific message id.
5. The system selects an available userbot or asks for manual assignment.
6. The system runs `source_access_checks`.
7. If access succeeds, the system fetches a preview of recent text/caption messages.
8. Oleg reviews title, type, access status, last message id, preview messages, and effective settings.
9. Oleg clicks `Activate`.

Default startup policy:

- New live lead-monitoring sources start from `from_now`.
- Historical backfill must be explicit.
- Historical backfill results are `retro` and web-only by default.
- Preview/backfill must not move the live monitoring checkpoint unless explicitly activated.

Data collected from monitoring sources:

- message text;
- caption;
- message date;
- chat id, message id, and message URL;
- sender id, username, and display name when available;
- reply-to id;
- nearby context messages according to settings;
- topic/thread id when available;
- forward metadata;
- media metadata;
- relevant service/system metadata.

Monitoring-source attachments are not downloaded by default. Text/captions and metadata are enough for first-stage lead detection.

Access and anti-bot policy:

- The system does not bypass Telegram protections.
- If join/captcha/private access is required, the source status changes and an `access_issue` is created.
- Operator-required access issues can notify Telegram immediately.
- After the operator fixes access manually, web UI offers `Recheck`.

Polling policy:

- First implementation uses one Telegram worker and one userbot session.
- Sources are polled in priority order.
- Each job reads a bounded message batch.
- Checkpoints are saved after every successful batch.
- `FLOOD_WAIT` pauses the affected source/account scope and the scheduler moves to other work.
- Resetting checkpoints requires explicit confirmation and creates an audit event.

## Lead Clustering And Deduplication

The system stores all raw messages and all lead-detection events. Deduplication happens at the working layer through `lead_clusters`.

Automatic clustering should group messages/events when strong evidence says they are part of the same request:

- same source/chat;
- same sender within `lead_cluster_window_minutes`;
- explicit reply chain to an already clustered message;
- same topic/thread and sufficiently similar topic;
- similar category, terms, or matched items;
- AI marks the new message as continuation, clarification, budget, deadline, or update for the same request.

Automatic clustering should not group:

- different people each asking for themselves;
- the same author asking about a different category or object later;
- old and new requests separated by a meaningful time gap;
- expert/vendor replies as new customer leads;
- simple "thanks/found it" messages as new leads.

Cluster timeline roles:

- `primary`: the best message to show as the main request;
- `trigger`: a message that independently produced a lead event;
- `clarification`: budget, timing, requirements, location, object size;
- `context`: surrounding message needed to understand the request;
- `negative_context`: message that explains why it is not a lead;
- `system`: service/system message that affects context.

Manual correction actions:

- merge clusters;
- split selected message/event into a new cluster;
- mark message as context only;
- set primary message;
- mark duplicate of another cluster;
- undo a wrong merge when possible.

Notification behavior:

- Telegram lead notifications are sent per cluster, not per lead event.
- New events inside an already notified cluster do not notify Telegram by default.
- A cluster update can notify only if enabled and the new event materially changes value, urgency, contact info, budget, deadline, or requirements.
- Duplicate/cooldown state is tracked on the cluster through `dedupe_key`, `last_notified_at`, and `notify_update_count`.

Rules:

- Cluster changes never delete `source_messages` or `lead_events`.
- Manual merge/split actions are stored in `lead_cluster_actions` and `audit_log`.
- Feedback can target a cluster, one lead event, one lead match, or one message.
- Cross-sender clustering is manual by default unless settings explicitly allow automatic grouping.

## CRM Conversion From Lead Clusters

CRM conversion is a deliberate step after a cluster is confirmed or clarified.

`Take into work` behavior:

- confirms that the cluster needs human action;
- creates a task to contact the person;
- does not automatically create a client, contact, interest, opportunity, support case, or contact reason.

The system can generate conversion candidates:

- `client_candidate`: person/company/KP/HOA/unknown entity;
- `contact_candidate`: Telegram user, phone, email, preferred channel;
- `object_candidate`: house, dacha, apartment, cottage settlement, office, warehouse, production site;
- `interest_candidate`: what the person wants, category, item/term, status;
- `opportunity_candidate`: sales/project motion;
- `support_case_candidate`: support, repair, setup, maintenance;
- `contact_reason_candidate`: useful follow-up later;
- `task_candidate`: immediate or delayed action.

Conversion wizard:

1. Choose what the cluster should become: new client, existing client, interest only, opportunity, support case, contact reason, or task.
2. Review candidate fields prefilled from cluster messages, sender metadata, matches, and AI summary.
3. Confirm next step: contact now, snooze/retry, prepare estimate, wait for answer, or close.

Rules:

- Candidates are suggestions until accepted.
- Oleg can accept, edit, reject, or ignore each candidate.
- One cluster may create several CRM records, for example client + contact + object + interest + task.
- A cluster becomes `converted` only after a primary CRM/work entity is created: `client_interest`, `opportunity`, `support_case`, `contact_reason`, or `client + task`.
- Creating only the default `Take into work` task does not mark the cluster as converted.
- Duplicate checks run before creating clients/contacts.

Duplicate checks:

- same Telegram user id;
- same username;
- same phone/email;
- similar display name;
- similar object and interest.

AI extraction should provide `crm_suggestions` in structured output, but the UI still requires confirmation before creating CRM records.

## Catalog Ingestion

Catalog ingestion turns PUR content into auditable operational catalog knowledge.

Pipeline:

```text
raw source
  -> artifact download / page fetch
  -> parsed chunks
  -> extraction run
  -> extracted facts
  -> catalog candidates
  -> catalog evidence
  -> operational catalog rows
  -> classifier version
```

Raw sources are immutable. Extracted facts preserve model/parser output. Catalog candidates normalize and deduplicate those facts before catalog rows are created or updated.

Extractable fact types:

- categories;
- products;
- services;
- brands and models;
- bundles/solutions;
- keywords, aliases, lead phrases, negative phrases;
- attributes and technical parameters;
- prices, offers, and promotions;
- compatibility, replacement, and bundle relations;
- source quotes/evidence.

Candidate creation:

- normalize brand/model/category names;
- group duplicate facts across messages, PDFs, Telegraph pages, and manual inputs;
- compare against existing catalog items/terms/attributes;
- detect conflicting prices/attributes;
- propose action: create, update, merge, expire, or ignore.

Auto-add policy:

- auto-add is enabled by default;
- suitable candidates can create operational catalog rows as `auto_pending`;
- `auto_pending` rows are active in the classifier if settings allow it;
- price/offer candidates default to `needs_review` unless they have explicit validity or TTL;
- broad/noisy terms default to `needs_review`;
- low-confidence or conflicting candidates default to `needs_review`.

Evidence rules:

- Every extracted or manual fact must have evidence.
- Evidence can be a Telegram message, document chunk, Telegraph/external page, or manual note.
- PDF evidence should store page/location when available.
- Catalog Review must show evidence next to each candidate.

Manual catalog addition:

- Manual additions are allowed from Catalog UI, Leads Inbox, and Manual Input.
- Manual additions create `manual_inputs` and `sources` rows.
- Manual additions create catalog candidates before catalog rows unless direct approved add is explicitly allowed.
- If an admin adds a manual catalog fact, default status can be `approved`.
- Non-admin catalog roles are a future expansion.
- Manual evidence note is required by default.

Manual add examples:

- add product/model and category;
- add service or bundle;
- add term/synonym/negative phrase;
- add price/offer with TTL;
- add relation/compatibility;
- create catalog correction from a lead message.

## Storage And Archive Policy

SQLite is the hot operational database. It keeps active catalog, CRM, settings, users, audit log, current jobs, recent messages, and recent evidence immediately queryable.

Bulky historical data is archived instead of deleted:

- monitoring-source messages and captions;
- parsed chunks from documents/pages;
- operational events and job runs;
- AI usage/events and raw usage metadata;
- notification events;
- research matches;
- embeddings when semantic search is enabled later.

Default archive layout:

- local storage first;
- `parquet_zstd` by default because it is compact and still practical to read back;
- `jsonl_zstd` as fallback for emergency/manual inspection;
- one manifest per archive segment;
- one hot pointer per archived entity;
- referenced entities such as `source_messages` keep their identity row as a hot stub and archive only large payload columns.

S3-compatible object storage is not part of the first implementation, but the schema includes `storage_backend = s3_compatible`, bucket/endpoint/prefix settings, and URI fields so the next phase can move archive files without redesigning the database.

Archive jobs must be conservative:

- write archive files;
- write and verify manifest/hash/row counts;
- only then clear eligible hot payload columns or remove rows that are known to have no hot FK dependencies;
- keep searchable pointers/snippets in SQLite;
- record all archive/restore operations in `operational_events` and `audit_log` when user-triggered.

Archive jobs must not break foreign keys. A row referenced by lead, cluster, evaluation, feedback, or CRM tables stays in SQLite as an identity stub even after its full text or metadata is moved to archive.

Research and reclassification can work against the hot DB by default. If the needed time window is archived, they create `archive_restore_jobs`. Automatic restore is configurable; the default is manual confirmation so an exploratory research run cannot silently expand local disk usage.

## Quality And Evaluation

Quality is a product feature, not a one-time test.

Evaluation should cover:

- live lead detection;
- `maybe` handling;
- high-value low-confidence notifications;
- retro/reclassification results;
- lead clustering and split/merge behavior;
- catalog extraction and candidate status;
- notification policy;
- CRM conversion candidates.

Datasets:

- golden set: hand-labeled lead/not-lead/maybe cases;
- feedback regression set: real mistakes promoted from feedback;
- catalog extraction set: PUR source chunks with expected catalog facts;
- notification set: expected immediate/web-only/digest/suppressed behavior;
- clustering set: multi-message examples with expected cluster behavior.

Metrics:

- precision, recall, F1;
- false positives and false negatives;
- `maybe` volume and resolution rate;
- high-value precision;
- retro lead precision;
- notification precision;
- catalog candidate accept/reject/merge rates;
- feedback volume by reason and source;
- quality by source, category, model, prompt, and classifier version.

Rules:

- Prompt/model/catalog changes should be evaluable before rollout.
- Regression cases should be created from meaningful feedback.
- Evaluation runs must store classifier version, catalog hash, prompt hash, settings hash, model, and per-case results.
- Quality dashboard should show trends and recent regressions.
- Quality thresholds are configurable; threshold misses create web warnings, not silent failures.

## Backup, Restore, And Secrets

Backup/recovery covers the operational system, not only the archive layer.

Backed up data:

- SQLite database;
- archive manifests and archive files;
- downloaded artifacts/documents;
- Telegram session files when explicitly enabled;
- runtime config;
- secret manifest/references, never raw secret values unless an explicit local encrypted backup policy is configured.

Backup rules:

- SQLite backup uses a consistent backup/snapshot mechanism.
- Backup files are hashed and verified after write.
- Old backups expire only after newer verified backups exist.
- Backup and restore events are stored in `backup_runs`, `restore_runs`, `operational_events`, and `audit_log` when user-triggered.
- Local backup is first phase; S3-compatible backup uses the same `storage_backend` pattern later.
- Telegram sessions and raw secret values are excluded unless encrypted backup is explicitly configured.

Restore rules:

- Dry-run restore validation is required by default.
- Full restore validates database integrity, required config, archive manifests, session availability, and worker startup readiness.
- Restore must not leak secrets into logs or UI.
- Restore actions are admin-only.

Secret hygiene:

- Secret values are never logged.
- Secret values are never stored in SQLite plaintext.
- UI shows secret display name/status only.
- Telegram session paths, API keys, web session secrets, bootstrap admin credentials, and S3 credentials are referenced through `secret_refs`.
- Rotation, missing secret checks, and failed secret access are audited.

## First Production Scope

There is no separate reduced MVP. The first production target is the full first-phase design in this spec.

Included in first production scope:

- SQLite operational database and migrations;
- PUR channel ingestion with documents and configured external pages;
- catalog extraction, catalog candidates, evidence, manual catalog add, Catalog Review;
- monitored source onboarding, access checks, previews, polling, checkpoints;
- lead detection, clustering, notification policy, `Leads Inbox`, feedback loop;
- CRM memory, conversion candidates, conversion wizard, contact reasons, tasks, support/opportunity basics;
- web UI with bootstrap local admin and Telegram admin accounts;
- settings, audit, operational logs;
- quality/evaluation dashboards and regression sets;
- archive/retention, local backup/restore, and secret hygiene.

Explicit next-phase items that remain outside first production until the spec is changed:

- S3-compatible archive/backup implementation;
- scoped web roles beyond `admin`;
- enabled semantic/vector matching if embeddings remain disabled in settings.

## Web Interface

Default landing screen:

- `Leads Inbox` is the primary working screen.
- `Today` is a secondary overview for reminders, contact reasons, tasks, and operational issues.

### Authentication

Purpose:

- authenticate site users through Telegram;
- allow bootstrap through a built-in local administrator account;
- authorize first-version actions through a single `admin` role.

Requirements:

- login via local admin credentials for bootstrap;
- require password change for the seeded bootstrap admin account;
- login via Telegram authentication flow for Telegram admin accounts;
- verify Telegram auth payload server-side before creating a session;
- map Telegram user id to `web_users.telegram_user_id`;
- deny access for unknown Telegram users;
- allow local admin to add Telegram admin accounts;
- expose admin account management in Settings/Admin screens;
- write login, logout, role change, and denied-access events to `audit_log`.

Role model:

- `admin`: all actions, settings, and user management.

Future roles:

- `catalog_manager`;
- `lead_reviewer`;
- `viewer`;
- other scoped roles if multi-user workflow becomes necessary.

These future roles should remain represented only as an extension path until the first admin-only version is working.

### Today

Purpose:

- give Oleg a compact overview of non-lead work that needs attention.
- avoid competing with `Leads Inbox` as the main screen.

Sections:

- new leads;
- contact reasons;
- tasks due today;
- snoozed items returning today;
- recent support cases;
- catalog candidates requiring attention.

Actions:

- open lead;
- mark contact reason done/dismissed/snoozed;
- create quick note;
- create task;
- open client card.

### Sources

Purpose:

- manage Telegram sources for lead monitoring and catalog ingestion;
- show onboarding, access, polling, sync, parsing, and artifact state;
- make source errors actionable without using Telegram commands.

Views:

- active monitoring sources;
- catalog-ingestion sources, including `@purmaster`;
- draft/checking/preview-ready sources;
- paused/failed sources;
- access issues;
- source logs.

List columns:

- source title;
- source type;
- purpose;
- status;
- priority;
- assigned userbot;
- checkpoint / latest message id;
- last success/error;
- next poll;
- leads found;
- error/access badge.

Actions:

- add Telegram source;
- fetch preview;
- activate;
- pause/resume;
- recheck access;
- change purpose/start mode before activation;
- resync catalog source;
- fetch message range;
- fetch one Telegram link;
- reparse source;
- reset checkpoint with confirmation;
- open logs;
- open access issue;
- mark source outdated/wrong.

Add-source UI:

- accepts `@username`, `t.me/...`, invite link, or message link;
- defaults to purpose `lead_monitoring`;
- defaults to `from_now`;
- shows preview before activation;
- clearly marks historical backfill as retro/web-only unless settings override it.

### Catalog Review

Purpose:

- review catalog candidates and `auto_pending` facts before or after they affect the classifier.

Views:

- new items;
- new terms;
- new attributes/offers;
- noisy terms by false-positive count;
- conflicts and duplicates.
- prices/offers with TTL;
- merge suggestions;
- manual additions awaiting review.

Actions:

- approve;
- reject;
- mute;
- merge;
- edit;
- move category;
- add note.

Candidate card shows:

- proposed action and candidate type;
- normalized value;
- target catalog entity or merge suggestion;
- confidence and status;
- evidence quotes and source links;
- similar existing items/terms;
- classifier impact.

### Catalog

Purpose:

- browse and edit the active catalog.

Features:

- search by product, service, term, brand, model;
- filter by status/category/source;
- item detail with terms, attributes, relations, evidence, feedback history;
- bulk approve/mute/reject.
- manual add for item, service, bundle, term, offer, attribute, relation, lead phrase, and negative phrase.

### Leads Inbox

Purpose:

- review lead clusters as the primary daily workflow.
- quickly decide whether a message requires action, feedback, CRM follow-up, or no action.
- work as a triage pipeline, not a heavy CRM form.

Layout:

- compact cluster queue on the left;
- selected cluster detail card on the right;
- filters for status, source, category, confidence, `auto_pending`, `retro`, and operator issues;
- keyboard-friendly next/previous/decision flow can be added later.

Queue row shows:

- current status and urgency;
- source chat;
- message date/time;
- short AI summary of what the person wants;
- matched category;
- confidence;
- badges: `auto_pending`, `retro`, `maybe`, `needs operator`, `duplicate`;
- message/event count;
- whether the cluster already has feedback, task, client, or contact reason.

Each cluster shows:

- short AI summary;
- source chat and primary message link;
- primary author/sender information when available;
- detection modes represented in the cluster: `live`, `retro`, `manual`, `reclassification`;
- original message date and trigger reason for retro leads;
- primary message text;
- timeline of clustered messages;
- reply-chain and neighboring context;
- AI reason;
- all matched lead events;
- matched category/items/terms;
- whether matches are `approved` or `auto_pending`;
- classifier versions represented in the cluster;
- why messages/events were merged;
- CRM suggestions/candidates;
- previous feedback if any.

Primary actions:

- take into work;
- not lead;
- maybe;
- duplicate;
- snooze;
- correct.

Follow-up actions:

- create task;
- create or link client;
- accept/edit CRM candidate;
- create client interest;
- create opportunity;
- create support case;
- create contact reason;
- add comment;
- create catalog item/term from message.

Correction/detail actions:

- wrong category;
- wrong item;
- wrong product or term;
- term too broad;
- not our topic;
- expert/not customer;
- no buying intent;
- mark `auto_pending` fact wrong;
- merge clusters;
- split from cluster;
- mark message as context only;
- set primary message;
- mark duplicate of another cluster.

Fast `not lead` reasons:

- no buying intent;
- expert/advice, not a customer;
- not our topic;
- wrong product/category;
- wrong product or term;
- term too broad;
- DIY only;
- too cheap/free;
- spam/noise;
- context only;
- wrong merge;
- outdated historical message.

Duplicate is a separate action, not a negative classifier reason.

Commercial outcomes that are not `not_lead` reasons:

- no answer;
- client changed mind;
- too expensive;
- bought elsewhere;
- postponed;
- already solved;
- not our region/object type.

Rules:

- The first decision should be possible in 5-15 seconds.
- Catalog and CRM actions are available from the card, but should not block quick lead triage.
- If a lead is wrong, the UI should encourage narrow feedback: lead reason, matched item, matched term, or category.
- `Not lead` requires a reason.
- `Maybe`, `snooze`, and commercial outcomes do not train the classifier as negative examples by default.
- `auto_pending` matches must be visually clear because feedback on them can immediately improve the classifier.
- `maybe` stays in the web inbox by default and does not trigger Telegram notifications unless the high-value low-confidence exception is enabled and matched.
- The inbox shows one row per `lead_cluster`; raw `lead_events` are visible inside the cluster detail.
- Auto-merge decisions must be visible and correctable.

Lead state model:

- AI detection is historical evidence: `decision`, `confidence`, `detection_mode`, `classifier_version_id`, reason, and matches.
- Cluster status is Oleg's workflow: `new`, `in_work`, `maybe`, `snoozed`, `not_lead`, `duplicate`, `converted`, `closed`.
- Cluster work outcome is the commercial/support result: task, touchpoint, opportunity, support case, client interest, contact reason, or closed without action.

`Take into work` flow:

- set `lead_clusters.cluster_status = in_work`;
- set `lead_clusters.review_status = confirmed`;
- write feedback action `lead_confirmed`;
- create a task "contact about lead" due now;
- store that task in `lead_clusters.primary_task_id`;
- do not automatically create client, opportunity, support case, or client interest.

After `Take into work`, the card offers clarification actions:

- create or link client;
- accept/edit CRM suggestions;
- create client interest;
- create opportunity;
- create support case;
- create contact reason;
- record touchpoint;
- snooze retry/no-response task;
- close without CRM conversion;
- change decision to `not_lead` with a reason.

Reasoning:

- `Take into work` means "this requires human action".
- Creating CRM objects requires clarification, because many Telegram leads will be incomplete or noisy.
- This keeps lead review fast while preserving a path into CRM when the lead is real.

CRM suggestions block:

- proposed contact: Telegram username/display name/phone when known;
- proposed object: house, dacha, apartment, cottage settlement, office, warehouse, production, unknown;
- proposed interest: category, item/term, request text, urgency, budget, quantity;
- proposed opportunity/support/contact reason when the request type is clear;
- next-step suggestion: contact now, ask budget/location, prepare estimate, wait/retry, or close.

The block shows candidates, not committed CRM records. Oleg can accept, edit, reject, or ignore each candidate.

Conversion wizard:

1. Choose what this cluster becomes: new client, existing client, interest only, opportunity, support case, contact reason, or task.
2. Review extracted fields prefilled from the cluster.
3. Confirm next step: contact now, snooze/retry, prepare estimate, wait for answer, or close.

Duplicate protection:

- search by Telegram user id;
- search by username;
- search by phone when present;
- search by similar display name;
- compare existing client objects/interests.

If likely duplicates exist, the wizard should prefer linking to an existing client/contact over creating a new one.

### Lead Detail

Purpose:

- deep review of one lead cluster.

Shows:

- full source context;
- cluster timeline;
- cluster members and roles;
- matched evidence chain;
- item/term statuses at detection time;
- merge/split history;
- suggested catalog edits;
- manual correction controls.

### Clients

Purpose:

- browse the client memory.

Features:

- search by name, Telegram username, phone, object, category, installed asset, old interest;
- filters for active, archived, do-not-contact, has open reason, has due task;
- lightweight list columns: client, object, interests/assets, last touchpoint, next step.

Actions:

- add client;
- add contact;
- add object;
- add interest;
- add installed asset;
- add touchpoint;
- add task;
- archive or mark do-not-contact.

### Client Detail

Purpose:

- show everything useful about one client without forcing a sales-pipeline workflow.

Sections:

- contacts and preferred channels;
- objects;
- interests;
- installed assets;
- open contact reasons;
- opportunities;
- support cases;
- touchpoint history;
- tasks;
- notes;
- related leads and source evidence.

Actions:

- add interest from text;
- add installed equipment;
- create opportunity;
- create support case;
- create contact reason;
- create task;
- mark follow-up done;
- link a lead to this client.

### Contact Reasons

Purpose:

- show why Oleg should contact someone now.

Views:

- new;
- due today;
- snoozed;
- high priority;
- generated from catalog changes;
- generated from support/service dates;
- manual.

Actions:

- accept;
- done;
- dismiss;
- snooze;
- create opportunity;
- create support case;
- create touchpoint;
- create task.

### Research

Purpose:

- test new commercial directions against historical chat demand before adding them to the catalog.

Views:

- hypotheses;
- running scans;
- completed reports;
- strong-intent matches;
- weak-intent/discussion samples;
- conversions into catalog/CRM entities.

Actions:

- create hypothesis;
- add seed/negative terms;
- ask AI to expand terms;
- choose saved-message scan or temporary backfill;
- select sources and history depth;
- run scan;
- review report;
- convert hypothesis into catalog category/item/terms;
- create leads/contact reasons manually from selected matches.

Rules:

- Research is web-first. It should not flood Telegram with historical matches.
- Telegram can receive a summary notification if enabled.
- Research findings should show dates clearly because matches may be old.
- Backfill depth/source scope is configurable per run and must respect rate limits.
- Research backfill must not move normal monitoring checkpoints unless explicitly configured.

### Opportunities

Purpose:

- keep a lightweight view of active commercial movements.

Statuses:

- `new`;
- `qualified`;
- `contacted`;
- `proposal`;
- `won`;
- `lost`;
- `not_lead`;
- `snoozed`.

Rules:

- opportunities are optional;
- a lead, interest, or contact reason can exist without an opportunity;
- assignment fields are hidden until multi-user CRM is enabled.

### Support

Purpose:

- track support/service interactions for existing clients and installed assets.

Views:

- open cases;
- waiting client;
- service due;
- recently resolved.

Actions:

- create support case;
- add resolution;
- create follow-up contact reason;
- update asset service status.

### Tasks

Purpose:

- simple personal reminders for Oleg.

Views:

- today;
- overdue;
- upcoming;
- snoozed;
- done.

Actions:

- create task;
- complete;
- snooze;
- link to client/opportunity/support case/contact reason.

### Storage / Archives

Purpose:

- show hot database size, archive size, retention state, and restore jobs;
- make archive policy visible without turning it into an operator-only hidden config.

Views:

- hot DB usage by table;
- archive segments by period/type/status;
- restore jobs;
- archive verification failures;
- storage backend configuration.

Actions:

- run archive rotation now;
- verify archive segment;
- restore selected period/source/table;
- cancel restore job;
- switch archive policy values;
- configure S3-compatible backend for the next phase.

Rules:

- first implementation stores archives locally;
- S3 settings can exist disabled until the S3 phase;
- destructive cleanup requires successful verification and audit record;
- restoring archived messages should not move monitoring checkpoints.

### Quality / Evaluation

Purpose:

- show whether lead detection, catalog extraction, clustering, notifications, and CRM suggestions are improving;
- make feedback-derived regressions visible.

Views:

- quality dashboard;
- golden datasets;
- feedback regression cases;
- evaluation runs;
- failed cases by reason;
- metrics by source/category/model/prompt/classifier version.

Actions:

- create or edit evaluation case;
- promote feedback into regression case;
- run evaluation;
- compare two runs;
- open failed case in source/lead/catalog context;
- acknowledge threshold warning.

### Backup / Recovery / Secrets

Purpose:

- make backup and restore status visible;
- manage secret references without exposing secret values.

Views:

- backup runs;
- restore runs;
- backup verification failures;
- secret references and health;
- secret rotation history.

Actions:

- run backup now;
- verify backup;
- dry-run restore;
- restore selected backup;
- check secret availability;
- rotate/update secret reference.

Rules:

- secret values are never displayed;
- restore and secret actions are admin-only and audited;
- failed backup/restore/secret checks create operational warnings.

### Manual Input

Purpose:

- allow Oleg/admin to add examples, source links, catalog facts, and CRM memory.

Inputs:

- Telegram link;
- forwarded-message text or exported message block pasted into web;
- raw text;
- catalog note;
- direct catalog item/term/offer/service form;
- client/contact note;
- interest note;
- installed equipment note;
- support note;
- reminder.

Actions:

- save as positive lead example;
- save as negative lead example;
- parse as source;
- create/edit catalog fact;
- create catalog candidate;
- approve manual catalog candidate when allowed;
- attach to existing item/category;
- create client/contact;
- create client interest;
- create installed asset;
- create support case;
- create contact reason;
- create task.

### Settings

Purpose:

- configure ingestion, auto-add, classifier inclusion, notifications, access, expiry, and external fetching.

Required controls:

- auto-add items/terms/attributes;
- catalog candidate thresholds and statuses;
- whether candidates auto-create operational catalog rows;
- manual catalog add defaults for admin;
- manual evidence-note requirement;
- web manual input and forwarded-message import;
- disabled-by-default Telegram forwarding input for future use;
- use `auto_pending`;
- use `needs_review`;
- document/video/photo download switches;
- external link fetching;
- allowed external domains;
- whether `auto_pending` matches are visually marked in Telegram notifications;
- default campaign/offer expiry rules;
- local bootstrap admin account;
- Telegram admin account management;
- future scoped roles enablement;
- feedback reason codes;
- whether `not_lead` requires a reason;
- whether commercial outcomes can affect classifier training;
- whether wrong term/match feedback creates review items or auto-mutates catalog;
- whether expert/advice feedback updates sender profiles;
- authentication/session settings;
- CRM enabled/disabled;
- whether confirmed leads can create client/contact candidates automatically;
- whether lead clusters generate CRM conversion candidates;
- whether CRM candidates require confirmation;
- conversion wizard candidate types and duplicate-check policy;
- what marks a cluster as `converted`;
- whether manual notes auto-create interests;
- whether catalog changes auto-create contact reasons;
- whether `auto_pending` catalog entries can create contact reasons;
- whether assignee fields are visible;
- Telegram userbot accounts: add, pause, disable, check status;
- Telegram worker count and per-session serialization;
- Telegram flood-wait thresholds and observed cooldowns;
- source priority and polling policy;
- source onboarding preview requirement;
- default source purpose and start mode;
- enabled source kinds split by lead monitoring and catalog ingestion;
- source backfill policy and retro/web-only behavior;
- checkpoint reset confirmation policy;
- AI providers, provider accounts, model registry, model capabilities, and credentials references;
- AI agent definitions and per-agent multi-model route policy;
- AI per-provider-model limit table and safety utilization ratio;
- AI/parse parallel job limits;
- AI batching strategy and limits;
- reclassification triggers, windows, scopes, and notification rules;
- retro lead notification styling;
- research default message scope, backfill permissions, and limits;
- research auto-conversion settings;
- embedding enablement, provider, model, and concurrency;
- retention windows by table;
- hot database max size;
- archive format/compression/rotation policy;
- local archive path;
- archive verification and deletion policy;
- archive restore policy for research/reclassification;
- S3-compatible archive backend settings for the next phase;
- quality evaluation enablement;
- golden/regression dataset behavior;
- quality thresholds and run triggers;
- backup schedule, retention, and verification;
- restore dry-run requirement;
- secret masking and rotation audit policy;
- first production scope marker;
- provider policy warning acknowledgement;
- Telegram notification toggles;
- live lead notification confidence thresholds;
- high-value low-confidence notification rules;
- maybe/retro/reclassification notification policies;
- lead clustering enablement, merge window, similarity threshold, and cross-sender policy;
- lead cluster update notification policy;
- Telegram digest times and digest contents;
- notification cooldowns and duplicate suppression windows;
- sync interval;
- max document size.

### Audit

Purpose:

- show who changed what and when.

## Telegram Notification Policy

Telegram is an urgent signal channel. It must not become a duplicate of the web inbox.

Sending a Telegram notification never changes lead state. A notified cluster remains in `Leads Inbox` until Oleg takes an action in the web UI or an explicitly enabled Telegram acknowledgement flow handles it.

Lead notifications are cluster-based:

- the first qualifying event in a cluster can notify Telegram;
- later events in the same cluster update the web card and timeline;
- later events do not notify by default;
- cluster update notifications require explicit setting and meaningful new information.

Immediate Telegram notifications:

- live actionable lead: `decision = lead`, confidence above `lead_notify_min_confidence`, not a duplicate, source not muted;
- high-value low-confidence lead: lower confidence, but category/source/AI reason suggests meaningful commercial value;
- operator action required: `needs_join`, `needs_captcha`, `private_or_no_access`, `banned`, repeated source failure, long flood wait, userbot down, AI/API unavailable, repeated parser failure;
- urgent CRM/task/support item: high/urgent priority contact reason, task, or support case.

High-value low-confidence rule:

- `decision` is `lead` or `maybe`;
- lead confidence is below `lead_notify_min_confidence`;
- lead confidence is at or above `lead_notify_high_value_min_confidence`;
- `commercial_value_score` is at or above `high_value_notify_threshold`;
- `negative_score` is below `high_value_negative_score_max`;
- source and category are not muted;
- notification is not suppressed as a duplicate cluster/update.

High-value positive signals:

- whole object: house, cottage, dacha, apartment renovation, cottage settlement, office, warehouse, production site;
- turnkey or contractor intent: "под ключ", "кто занимается", "кто установит", "посоветуйте подрядчика";
- multiple systems: cameras plus intercom, network, access control, gate/barrier, smart home, power/electric;
- project/survey/estimate/selection language;
- urgency;
- quantity or multiple objects;
- buyer language: price, cost, buy, install, quote;
- B2B/HOA/management-company context;
- priority category/source;
- known client or CRM match.

High-value negative signals:

- expert discussion or advice without buying intent;
- DIY-only request;
- explicitly free/too-cheap intent when it is outside PUR format;
- complaint about equipment bought elsewhere without support request;
- adjacent but non-commercial topic.

Web-only by default:

- `maybe`, except explicitly configured high-value low-confidence notifications;
- catalog candidates and `auto_pending` facts;
- normal contact reasons;
- research matches;
- retro leads;
- reclassification results;
- transient errors that are still inside retry thresholds.

Digest by default:

- new leads count;
- in-work leads count;
- `maybe` count;
- catalog candidates awaiting review;
- source/userbot issues;
- contact reasons and due tasks.

Lead notification content:

- short AI summary of what the person wants;
- source chat;
- author/sender when available;
- message time;
- cluster message/event count when greater than one;
- category;
- matched terms/items;
- confidence;
- commercial value score and high-value signals when relevant;
- `approved`/`auto_pending` fact markers;
- links to `Leads Inbox` and the original Telegram message.

High-value low-confidence notification content must explicitly say that AI is uncertain and human review is needed.

Retro lead notification content, when enabled:

- clear `retro` label;
- original message date;
- trigger reason: catalog change, prompt change, feedback change, manual research, or settings change;
- link to web review.

Deduplication/cooldown rules:

- duplicate Telegram notifications are suppressed by cluster `dedupe_key`;
- cluster update notifications respect `lead_cluster_update_cooldown_minutes` and `lead_cluster_notify_update_min_value_delta`;
- one source or provider failure should not spam Telegram repeatedly;
- suppressed notifications still create `notification_events` rows with `notification_policy = suppressed`.

## Telegram Role

Telegram remains an information channel.

Bot sends:

- immediate live/actionable lead notification;
- daily/periodic status summary;
- digest summaries;
- urgent contact reasons and due-task reminders;
- urgent support follow-up reminders;
- operator-required AI/parser/sync/userbot/access errors;
- links to the web UI.

Bot accepts:

- only minimal operational acknowledgements if explicitly enabled.

Bot does not accept:

- adding monitored chats;
- monitored chat links;
- manual lead/catalog/CRM examples in the first phase;
- changing checkpoints;
- changing catalog/CRM/settings.

Most review and configuration happens in the web UI.

## Classifier Behavior

The classifier should be built from SQLite, not handwritten docs.

Inputs:

- active catalog categories;
- active items;
- active terms;
- active lead intent examples;
- active client interests when generating contact reasons;
- active client assets when generating support/upgrade reasons;
- recent negative feedback patterns;
- settings controlling included statuses.

Each classifier build creates `classifier_versions`, `classifier_snapshot_entries`, and `classifier_version_artifacts`.

Lead detection output must include:

- decision;
- lead confidence;
- commercial value score;
- negative score;
- high-value signals;
- negative signals;
- notification reason when the message should be surfaced despite uncertainty;
- reason;
- matched category;
- matched items;
- matched terms;
- evidence references;
- classifier version.
- clustering hint: `new_request`, `continuation`, `clarification`, `context_only`, or `separate_intent`.
- CRM suggestions: contact, object, interest, opportunity/support/contact-reason hint, and next step.

Catalog extraction output must include structured facts:

```json
{
  "facts": [
    {
      "fact_type": "product",
      "canonical_name": "Dahua Hero A1",
      "category": "video_surveillance",
      "terms": ["hero a1", "wi-fi камера", "поворотная камера"],
      "attributes": [{"name": "connectivity", "value": "Wi-Fi"}],
      "evidence_quote": "...",
      "confidence": 0.86
    }
  ]
}
```

Example AI output:

```json
{
  "decision": "maybe",
  "lead_confidence": 0.52,
  "commercial_value_score": 0.84,
  "negative_score": 0.12,
  "high_value_signals": ["whole_object: house", "turnkey", "installer_needed"],
  "negative_signals": [],
  "notify_reason": "AI is uncertain, but the message looks like a potential project lead",
  "clustering_hint": "new_request",
  "crm_suggestions": {
    "contact": {"telegram_username": "ivan", "display_name": "Иван"},
    "object": {"type": "dacha", "location_text": null},
    "interest": {
      "category": "video_surveillance",
      "text": "Wi-Fi camera for a dacha with mobile viewing"
    },
    "next_step": "Ask for budget, installation location, and whether turnkey installation is needed"
  }
}
```

Commercial value is not the same as lead confidence. It estimates whether the request is worth quick human attention if it is real.

For reclassification output:

- preserve the original live decision;
- store the new decision under the new classifier version;
- create retro lead events and clusters when historical messages become leads;
- mark retro clusters clearly in UI and Telegram;
- keep `maybe` web-only by default.

Retro lead notification copy must include:

- that the message is historical;
- original message date;
- trigger reason: catalog change, prompt change, feedback change, manual research, or settings change;
- link to the web review page.

Contact-reason generation should compare:

- active `client_interests`;
- active `client_assets`;
- new or changed catalog items, terms, offers, attributes;
- seasonal rules and support dates;
- manual reminders.

The result is not a lead notification by default. It creates `contact_reasons` for Oleg's review.

Research behavior:

- starts from a hypothesis and seed/negative terms;
- can scan only already saved messages or perform configured temporary backfill;
- can request restore of archived messages when the selected time window is no longer hot;
- produces reports before creating catalog/CRM entities;
- does not notify every historical match to Telegram;
- can convert selected matches into catalog items, leads, client interests, or contact reasons.

## Feedback Loop

Feedback should update the system at the narrowest useful level.

Primary UI actions:

- `Take into work`: positive lead feedback and task creation.
- `Maybe`: keeps the cluster in web review and does not create negative training data.
- `Not lead`: requires a reason and creates classifier/catalog/clustering feedback.
- `Duplicate`: links to another cluster and suppresses duplicate work/notifications.
- `Snooze`: work-state change only.
- `Correct`: opens detailed correction controls for category, item, term, match, sender, and cluster membership.

Fast `not_lead` reason codes:

- `no_buying_intent`: discussion without buying intent.
- `expert_or_advice`: advice/expert/vendor answer, not a customer request.
- `not_our_topic`: outside PUR scope.
- `wrong_category`: lead may exist, but category is wrong.
- `wrong_product_or_term`: wrong product/service/term caused the match.
- `term_too_broad`: a broad term caused noise.
- `diy_only`: wants to do it themselves and does not need PUR equipment/service.
- `too_cheap_or_free`: explicitly outside PUR commercial format.
- `spam_or_noise`: spam, joke, irrelevant noise.
- `old_irrelevant`: historical message is no longer actionable.
- `context_only`: message belongs in context but is not a lead trigger.
- `wrong_merge`: clustering joined unrelated messages.

Commercial outcomes that must not become negative classifier examples by default:

- no answer;
- client changed mind;
- too expensive;
- bought elsewhere;
- postponed;
- already solved;
- not our region/object type;
- no budget after qualification.

These outcomes belong in `work_outcome`, `opportunities`, `touchpoints`, `tasks`, or CRM notes. They describe sales/support result, not detection quality.

Learning effects:

- If a message is not a lead because the person is giving expert advice, store feedback on the cluster/event and a sender role hint.
- If "камера" creates too much noise, mute/reduce the term, not the entire video category.
- If `Dahua Hero A1` is correct, approve the item and its precise model terms.
- If a price is outdated, expire the offer/attribute, not the product.
- If a contact reason is not useful, dismiss or snooze the reason without deleting the underlying client interest.
- If an old interest becomes relevant because of a new catalog item, create a contact reason rather than mutating the original interest.
- If the wrong term caused a match, attach feedback to `lead_matches` and `catalog_terms`.
- If the wrong category was chosen, store a category correction example.
- If a message is context only, mark the `lead_cluster_member` role and train clustering/context builder.
- If the system merged unrelated messages, write `lead_cluster_actions` and clustering feedback.
- If the person is consistently an expert/vendor, update or review `sender_profiles`.

Correction mode:

- show matched category, items, terms, evidence, and `auto_pending` status;
- allow rejecting/muting one matched term without rejecting the item;
- allow changing category without rejecting the entire lead;
- allow setting a different primary message;
- allow splitting/merging clusters;
- allow marking one message as context only;
- allow adding the message as positive/negative example.

Feedback events do not need to immediately mutate catalog rows in every case. Some actions can create review tasks first. The audit log records any resulting mutation.

## Error Handling

- Sync failures are recorded on sources/extraction runs and surfaced in web UI.
- AI extraction failures do not silently become "no facts".
- AI lead-detection failures do not silently become "no leads".
- Document parse failures keep artifact metadata and error text.
- Duplicate source detection uses `(source_type, origin, external_id)` and content hash.
- Telegram flood wait should pause the specific sync job and record retry time.
- Archive write/verification failures must keep hot rows intact and create visible operational errors.
- Restore failures must leave existing hot data untouched and keep the restore job retryable or cancellable.
- Evaluation failures must not mutate classifier/catalog state; they create quality warnings and per-case results.
- Backup verification failures must keep the backup marked unusable.
- Secret access failures must be surfaced without logging secret values.

## Migration From Current Project

Current files:

- `data/chats.json`
- `data/checkpoints.json`
- `data/leads.json`
- `lead_examples.json`
- `docs/prompts.md`
- `docs/keywords.md`

Migration path:

1. Add SQLite database alongside JSON files.
2. Import existing chats/checkpoints/leads/examples into SQLite.
3. Seed empty CRM tables and the built-in local bootstrap admin user only.
4. Leave Telegram bot/userbot, notification groups, AI providers, tokens, and session files unconfigured until the administrator adds them through web/admin onboarding or an audited manual upload path.
5. Replace JSON lead persistence with SQLite `lead_events` and `lead_clusters`.
6. Add PUR channel sync into the same userbot runtime.
7. Add parser/extractor pipeline.
8. Generate classifier prompt/keyword index from SQLite.
9. Add web UI for catalog/leads/CRM/settings.
10. Deprecate JSON files after stable operation.

## Testing Strategy

Unit tests:

- source identity and duplicate detection;
- source onboarding status transitions;
- source access check result mapping;
- source preview does not move checkpoint;
- artifact download policy;
- document parsing into chunks;
- extracted fact normalization;
- catalog candidate deduplication from multiple extracted facts;
- catalog candidate status policy for low confidence, conflicts, broad terms, prices, and offers;
- manual catalog addition creates source/evidence/candidate;
- catalog status inclusion;
- classifier version creation;
- classifier snapshot entries/artifacts reconstruct included terms, examples, prompt, model config, and settings;
- classifier examples are included in snapshots according to status and weight;
- lead match persistence;
- lead matches reference the exact classifier snapshot entry that caused the match;
- lead cluster creation from one or more lead events;
- automatic cluster merge/split rules;
- cluster member role assignment;
- cluster update notification suppression;
- feedback event handling;
- `not_lead` feedback requires reason code;
- commercial work outcomes do not become negative classifier feedback;
- wrong term feedback targets `lead_matches` / `catalog_terms`;
- expert/advice feedback can update `sender_profiles`;
- CRM conversion candidate creation from lead cluster suggestions;
- CRM duplicate detection by Telegram id, username, phone, name, and object/interest similarity;
- cluster `converted` status rules;
- manual client/contact/interest/asset creation;
- contact reason generation from catalog changes;
- contact reason generation from catalog offer TTL, expiry, and price changes;
- task and touchpoint persistence.
- archive segment manifest generation and hash verification;
- archive pointer and hot-stub creation after payload archival;
- archived `source_messages` keep identity rows and valid foreign keys;
- archive restore job scope selection;
- embedding rows stay disabled/inactive when semantic search is off.
- evaluation dataset/case/run/result persistence;
- quality metric snapshot calculation;
- backup manifest/hash verification;
- session backup remains disabled unless encrypted secret backup policy is configured;
- secret references never expose secret values;
- Telegram notification policy selection: immediate, digest, web-only, suppressed;
- notification deduplication and cooldown key generation;
- `maybe` and retro leads stay web-only by default.
- high-value `maybe` notifications only fire through the explicit high-value exception.
- commercial value scoring stays independent from lead confidence;
- high-value low-confidence notification rule respects positive/negative thresholds.
- scheduler job scopes, idempotency keys, leases, and before/after checkpoints route work correctly.
- settings revisions preserve old/new values and setting hashes.

Integration tests:

- process archived `@purmaster` corpus into catalog candidates;
- same product from message, PDF, and Telegraph becomes one candidate with multiple evidence rows;
- manual catalog item added by admin can become approved with manual evidence;
- unknown Telegram user cannot access web UI until added by bootstrap/admin user;
- local bootstrap admin can add Telegram admin accounts;
- noisy broad term becomes `needs_review` instead of active high-weight term;
- add public Telegram group through web onboarding: draft -> checking_access -> preview_ready -> active;
- inaccessible/private/captcha source creates `access_issue` and operator notification policy;
- new source defaults to `from_now`;
- historical backfill creates retro/web-only lead events by default;
- manual Telegram link creates source and example;
- manual forwarded-message import works through the web UI while Telegram forwarding input stays disabled by default;
- `auto_pending` term triggers lead and stores `lead_matches`;
- several same-sender messages in a short window produce one `lead_cluster`;
- cross-sender similar messages require manual merge by default;
- split/merge actions preserve original `source_messages` and `lead_events`;
- feedback `term_too_broad` changes future classifier behavior;
- `not_lead -> wrong_product_or_term` creates narrow match/catalog feedback without rejecting whole category;
- `commercial_no_answer`/`commercial_too_expensive` updates work outcome without weakening classifier examples;
- `expert_or_advice` marks sender as expert/context candidate and suppresses future customer-lead treatment by default;
- `context_only` removes a message from lead trigger role without deleting it from cluster context;
- `Take into work` creates a contact task but no CRM client/opportunity automatically;
- accepting CRM candidates creates client/contact/object/interest records and links them to the source cluster;
- likely duplicate client is linked instead of creating a new client when Oleg confirms the match;
- duplicate message ids across chats do not deduplicate incorrectly;
- `source_message_id` disambiguates duplicate Telegram message ids across chats and classifier runs;
- confirmed lead can be linked to a client and interest;
- new catalog item creates a contact reason for an old matching interest;
- dismissed contact reason does not delete the client interest;
- manual installed asset can create a future support follow-up.
- archived messages can be restored for research without moving monitoring checkpoints;
- archive write failure does not trim hot payloads or delete hot rows;
- local `parquet_zstd` archive round-trips messages, parsed chunks, and AI usage rows.
- archive retention clears payloads but keeps referenced message stubs and FK integrity.
- feedback mistake can be promoted into evaluation regression case;
- evaluation run compares classifier versions without mutating production decisions;
- verified SQLite backup can be dry-run restored;
- secret access failure creates masked operational warning;
- immediate live lead creates `notification_events` but leaves cluster status `new`;
- duplicate/continued lead event does not create repeated Telegram notification inside suppression window;
- repeated access/userbot issue escalates to Telegram only after configured thresholds.
- uncertain high-value cluster creates a clearly marked Telegram notification and remains unconfirmed in `Leads Inbox`;
- high negative score suppresses high-value notification even when commercial signals are present.

Live/smoke tests:

- userbot can read configured channel;
- source preview can read recent text messages without downloading attachments;
- document downloads skip videos and fetch PDFs;
- bot can send notifications;
- web settings persist;
- web setting changes create `settings_revisions` rows;
- bootstrap local admin can log in and is required to change password;
- Telegram login payload is verified and mapped to an added admin user;
- unauthorized Telegram users cannot access the web UI;
- CRM Today screen can load leads, contact reasons, and due tasks from SQLite.
- Storage / Archives screen shows local archive segments, verification status, and restore job status.
- Quality / Evaluation screen shows latest metrics and failed cases.
- Backup / Recovery / Secrets screen shows backup status, restore dry-runs, and masked secret refs.
- Telegram lead notification links open both `Leads Inbox` and the original Telegram message.

## Resolved Configuration Decisions

These policies are not hard-coded. They are settings in the web interface:

- whether `auto_pending` matches are visually marked as lower-confidence in Telegram notifications;
- whether old campaign prices auto-expire when no explicit date is found;
- the default expiry period for campaign prices and offers;
- which external domains besides Telegraph are fetched automatically.
- which Telegram accounts have `admin` access.

The web interface is protected by a built-in bootstrap admin account and Telegram authentication for added admin users.
