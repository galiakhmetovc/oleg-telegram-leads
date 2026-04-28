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
- The web interface uses Telegram authentication and role-based permissions.
- Approval rights, `auto_pending` notification styling, campaign expiry, and external fetch domains are configurable in the web interface.
- CRM is included as a lightweight client-memory layer, not a heavy sales pipeline.
- CRM starts empty. Clients, interests, assets, and notes can be created manually or from confirmed leads.
- Oleg is the only active CRM user at first, but tables include ownership/assignee fields for future expansion.
- A central CRM job is generating reasons to contact existing or previously interested clients when catalog changes create a useful follow-up opportunity.
- Runtime work is processed by a continuous job loop, not a single monolithic polling cycle.
- Start with one Telegram userbot session and one Telegram worker. Additional userbot sessions are a future configurable expansion through the web UI.
- Telegram-read jobs are serialized per userbot session. AI and parse jobs can run in parallel with configurable limits.
- Logging and audit are first-class requirements for source sync, access issues, AI calls, parser runs, catalog changes, CRM changes, and notifications.

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

- The provider config must distinguish Coding Plan from regular API platform / enterprise usage.
- The UI should surface the policy warning when using Coding Plan credentials for this application.
- AI scheduler must track model usage, token usage, errors, and provider throttling.
- PromptBuilder must record prompt token estimates and actual response usage.
- Parallel AI job limits are configurable and should be conservative by default until real usage is measured.

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
- The schema allows adding more userbot accounts later through the web UI.
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
- `assigned_userbot_account_id`
- `priority`: `low`, `normal`, `high`
- `status`: `active`, `paused`, `needs_join`, `needs_captcha`, `private_or_no_access`, `flood_wait`, `banned`, `read_error`, `disabled`
- `lead_detection_enabled`
- `catalog_ingestion_enabled`
- `phase_enabled`
- `start_mode`: `from_now`, `from_message`, `recent_limit`, `recent_days`
- `start_message_id`
- `checkpoint_message_id`
- `checkpoint_date`
- `last_success_at`
- `last_error_at`
- `last_error`
- `created_at`
- `updated_at`

Rules:

- First implementation enables public groups/supergroups.
- Other source kinds are represented in the schema but can be hidden or marked "later" in UI.
- Chats are added from the web interface, not through Telegram commands.

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
- `job_type`: `poll_monitored_source`, `check_source_access`, `fetch_message_context`, `classify_message_batch`, `sync_pur_channel`, `download_artifact`, `parse_artifact`, `extract_catalog_facts`, `generate_contact_reasons`, `send_notifications`
- `status`: `queued`, `running`, `succeeded`, `failed`, `paused`, `cancelled`
- `priority`: `low`, `normal`, `high`
- `run_after_at`
- `locked_by`
- `locked_at`
- `attempt_count`
- `max_attempts`
- `payload_json`
- `last_error`
- `created_at`
- `updated_at`

Rules:

- Telegram jobs are serialized per `userbot_account_id`.
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
- `provider_config_id`
- `model`
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

### `notification_events`

Stores outbound Telegram/web notifications.

Key fields:

- `id`
- `notification_type`: `lead`, `task`, `contact_reason`, `access_issue`, `ai_error`, `sync_error`, `digest`
- `target_channel`: `telegram`, `web`, `email`, `none`
- `target_ref`
- `entity_type`
- `entity_id`
- `status`: `queued`, `sent`, `failed`, `suppressed`
- `priority`: `low`, `normal`, `high`, `urgent`
- `payload_summary`
- `error`
- `sent_at`
- `created_at`

Purpose:

- Audit what was sent to Telegram and why.
- Avoid duplicate urgent notifications.
- Support notification cooldowns and digests.

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

### `ai_provider_configs`

Stores model provider settings.

Key fields:

- `id`
- `provider`: `zai`, `openai_compatible`, `other`
- `base_url`
- `auth_secret_ref`
- `plan_type`: `coding_lite`, `coding_pro`, `coding_max`, `api_platform`, `enterprise`, `unknown`
- `default_model`
- `enabled`
- `max_parallel_calls`
- `request_timeout_seconds`
- `notes`
- `created_at`
- `updated_at`

Rules:

- Secret values are referenced, not stored in plaintext.
- For z.ai Coding Plan, the UI must show a usage-policy warning if the plan is used outside officially supported coding tools.

### `ai_model_limits`

Stores known and configured model limits.

Key fields:

- `id`
- `provider_config_id`
- `model`
- `context_window_tokens`
- `max_output_tokens`
- `supports_structured_output`
- `supports_thinking`
- `supports_tools`
- `default_temperature`
- `quota_multiplier_json`
- `source_url`
- `verified_at`
- `notes`

Purpose:

- Make model limits visible and editable in the web UI.
- Allow prompt builder to estimate token budget and choose fallback strategies.

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
- `token_estimate`
- `parser_name`
- `parser_version`
- `created_at`

FTS:

- Create FTS5 index over `text`.

### `extraction_runs`

Stores extraction jobs.

Key fields:

- `id`
- `run_type`: `channel_sync`, `document_parse`, `catalog_extraction`, `manual_example_parse`
- `model`
- `prompt_version`
- `catalog_version_id`
- `started_at`
- `finished_at`
- `status`
- `error`
- `stats_json`

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
- `entity_type`: `category`, `item`, `term`, `attribute`, `relation`, `offer`
- `entity_id`
- `source_id`
- `artifact_id`
- `chunk_id`
- `quote`
- `confidence`
- `created_at`

Purpose:

- Every fact should answer: "where did this come from?"
- UI can show source proof next to catalog changes.

### `manual_inputs`

Stores manual additions from Oleg/admin before they are processed.

Key fields:

- `id`
- `input_type`: `telegram_link`, `forwarded_message`, `manual_text`, `catalog_note`, `lead_example`
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

### `classifier_versions`

Stores snapshots of catalog state used by lead detection.

Key fields:

- `id`
- `version`
- `created_at`
- `created_by`
- `included_statuses_json`
- `catalog_hash`
- `prompt_hash`
- `keyword_index_hash`
- `settings_hash`
- `notes`

Rule:

- Every lead event records the classifier version used.

### `lead_events`

Stores detected leads.

Key fields:

- `id`
- `source_id`
- `chat_id`
- `message_id`
- `message_url`
- `sender_id`
- `sender_name`
- `message_text`
- `detected_at`
- `classifier_version_id`
- `decision`: `lead`, `not_lead`, `maybe`
- `confidence`
- `reason`
- `status`: `new`, `reviewed`, `closed`, `ignored`
- `created_at`

Uniqueness:

- `(chat_id, message_id, classifier_version_id)` for audit.
- Operational dedup can use `(chat_id, message_id)` for notification suppression.

### `lead_matches`

Stores why a lead matched.

Key fields:

- `id`
- `lead_event_id`
- `catalog_item_id`
- `catalog_term_id`
- `category_id`
- `source_id`
- `match_type`: `term`, `semantic`, `category`, `manual_example`, `llm_reason`
- `matched_text`
- `score`
- `item_status_at_detection`
- `term_status_at_detection`
- `created_at`

This table is required because `auto_pending` is active immediately. Feedback needs to target exact match causes.

### `feedback_events`

Stores all Oleg/admin feedback.

Key fields:

- `id`
- `target_type`: `lead`, `lead_match`, `catalog_item`, `catalog_term`, `category`, `source`, `manual_input`, `client`, `contact`, `client_object`, `client_interest`, `client_asset`, `opportunity`, `support_case`, `contact_reason`, `task`
- `target_id`
- `action`
- `reason_code`
- `comment`
- `created_by`
- `created_at`
- `metadata_json`

Initial action set:

- `lead_confirmed`
- `not_lead`
- `maybe`
- `wrong_category`
- `wrong_item`
- `approve_item`
- `reject_item`
- `mute_item`
- `approve_term`
- `reject_term`
- `mute_term`
- `term_too_broad`
- `expert_not_customer`
- `no_buying_intent`
- `not_our_topic`
- `source_outdated`
- `source_wrong`
- `manual_positive_example`
- `manual_negative_example`
- `create_client`
- `create_interest`
- `create_asset`
- `contact_reason_done`
- `contact_reason_dismissed`
- `contact_reason_snoozed`
- `support_needed`
- `support_done`

The UI can expose a small button set at first while the DB supports richer feedback.

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

- `owner_user_id` and `assignee_user_id` are stored now but hidden in the first UI because only Oleg uses CRM initially.
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
- Oleg can create an opportunity from a lead, client interest, contact reason, or manual note.
- The first UI should not expose complex team assignment even though fields exist.

### `support_cases`

Stores support and service interactions.

Key fields:

- `id`
- `client_id`
- `client_object_id`
- `client_asset_id`
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
- `catalog_attribute_id`
- `source_id`
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

### `settings`

Stores configurable behavior.

Key settings:

- `auto_add_catalog_items = true`
- `auto_add_terms = true`
- `auto_add_attributes = true`
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
- `notify_ai_errors = true`
- `telegram_notify_auto_pending_confidence = true`
- `telegram_auto_pending_label = "auto_pending"`
- `auto_expire_campaign_prices = true`
- `default_campaign_price_ttl_days = 30`
- `default_offer_ttl_days = 30`
- `approval_roles_json = ["owner", "admin", "catalog_manager"]`
- `lead_review_roles_json = ["owner", "admin", "catalog_manager", "lead_reviewer"]`
- `manual_input_roles_json = ["owner", "admin", "catalog_manager", "lead_reviewer"]`
- `telegram_auth_enabled = true`
- `crm_enabled = true`
- `crm_auto_create_client_from_confirmed_lead = false`
- `crm_auto_create_interest_from_manual_note = true`
- `crm_auto_create_contact_reasons = true`
- `crm_contact_reasons_include_auto_pending_catalog = true`
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
- `ai_max_parallel_calls = 2`
- `ai_parse_max_parallel_jobs = 2`
- `ai_default_provider_config_id = null`
- `ai_default_model = "glm-4.5-air"`
- `ai_provider_policy_warning_enabled = true`

Settings are editable in the web interface and versioned through `audit_log`.

### `web_users`

Stores users allowed into the web interface.

Key fields:

- `id`
- `telegram_user_id`
- `telegram_username`
- `display_name`
- `role`: `owner`, `admin`, `catalog_manager`, `lead_reviewer`, `viewer`
- `status`: `active`, `disabled`, `pending`
- `created_at`
- `updated_at`
- `last_login_at`

Rules:

- Oleg is seeded as an `owner` or `admin`.
- Additional approvers are configured in the web UI by users whose role is listed in `approval_roles_json`.
- Disabled users cannot log in even if Telegram authentication succeeds.

### `web_auth_sessions`

Stores web sessions created after Telegram login.

Key fields:

- `id`
- `user_id`
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
2. Forward a message to the bot or management group.
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
  -> optional lead_event created as manual example
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

Forwarded messages are stored similarly. If the source chat can be resolved, the userbot fetches the original message to preserve link and metadata.

### Manual Text Flow

Manual text becomes `source_type = manual_text`. It can still create extracted facts, lead examples, CRM notes, client interests, support cases, contact reasons, or feedback.

## Web Interface

### Authentication

Purpose:

- authenticate site users through Telegram;
- authorize actions through local roles stored in SQLite.

Requirements:

- login via Telegram authentication flow;
- verify Telegram auth payload server-side before creating a session;
- map Telegram user id to `web_users.telegram_user_id`;
- deny access for unknown users unless invite/pending-user mode is enabled in settings;
- expose role management in Settings/Admin screens;
- write login, logout, role change, and denied-access events to `audit_log`.

Role model:

- `owner`: all actions, settings, user management.
- `admin`: all operational actions except owner transfer.
- `catalog_manager`: catalog review, source review, manual inputs, lead feedback.
- `lead_reviewer`: lead feedback and manual examples.
- `viewer`: read-only.

### Today

Purpose:

- give Oleg a light daily working screen instead of a heavy CRM dashboard.

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

- show sync status for `@purmaster`;
- show latest message id;
- show downloaded/skipped artifacts;
- show parsing errors;
- open source text and linked evidence.

Actions:

- resync;
- fetch message range;
- fetch one Telegram link;
- reparse source;
- mark source outdated/wrong.

### Catalog Review

Purpose:

- review `auto_pending` facts.

Views:

- new items;
- new terms;
- new attributes/offers;
- noisy terms by false-positive count;
- conflicts and duplicates.

Actions:

- approve;
- reject;
- mute;
- merge;
- edit;
- move category;
- add note.

### Catalog

Purpose:

- browse and edit the active catalog.

Features:

- search by product, service, term, brand, model;
- filter by status/category/source;
- item detail with terms, attributes, relations, evidence, feedback history;
- bulk approve/mute/reject.

### Leads Inbox

Purpose:

- review detected leads.

Each lead shows:

- source chat and message link;
- message text;
- AI reason;
- matched category/items/terms;
- whether matches are `approved` or `auto_pending`;
- classifier version;
- previous feedback if any.

Actions:

- lead;
- not lead;
- maybe;
- wrong category;
- wrong item;
- term too broad;
- not our topic;
- expert/not customer;
- no buying intent;
- add comment;
- create catalog item/term from message.

### Lead Detail

Purpose:

- deep review of one lead.

Shows:

- full source context;
- matched evidence chain;
- item/term statuses at detection time;
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

### Manual Input

Purpose:

- allow Oleg/admin to add examples, source links, catalog facts, and CRM memory.

Inputs:

- Telegram link;
- forwarded message;
- raw text;
- catalog note.
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
- attach to existing item/category.
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
- use `auto_pending`;
- use `needs_review`;
- document/video/photo download switches;
- external link fetching;
- allowed external domains;
- whether `auto_pending` matches are visually marked in Telegram notifications;
- default campaign/offer expiry rules;
- which roles can approve/reject catalog facts;
- which roles can review leads and add manual examples;
- Telegram authentication/session settings;
- CRM enabled/disabled;
- whether confirmed leads can create client/contact candidates automatically;
- whether manual notes auto-create interests;
- whether catalog changes auto-create contact reasons;
- whether `auto_pending` catalog entries can create contact reasons;
- whether assignee fields are visible;
- Telegram userbot accounts: add, pause, disable, check status;
- Telegram worker count and per-session serialization;
- Telegram flood-wait thresholds and observed cooldowns;
- source priority and polling policy;
- AI provider credentials/config references;
- AI model selection and model-limit table;
- AI/parse parallel job limits;
- provider policy warning acknowledgement;
- Telegram notification toggles;
- sync interval;
- max document size.

### Audit

Purpose:

- show who changed what and when.

## Telegram Role

Telegram remains an information channel.

Bot sends:

- new lead notification;
- daily/periodic status summary;
- catalog candidates waiting for review;
- contact reasons and due-task summaries;
- support follow-up reminders;
- AI/parser/sync errors;
- links to the web UI.

Bot accepts:

- only minimal operational acknowledgements if explicitly enabled.

Bot does not accept:

- adding monitored chats;
- monitored chat links;
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

Each classifier build creates `classifier_versions`.

Lead detection output must include:

- decision;
- reason;
- matched category;
- matched items;
- matched terms;
- evidence references;
- classifier version.

Contact-reason generation should compare:

- active `client_interests`;
- active `client_assets`;
- new or changed catalog items, terms, offers, attributes;
- seasonal rules and support dates;
- manual reminders.

The result is not a lead notification by default. It creates `contact_reasons` for Oleg's review.

## Feedback Loop

Feedback should update the system at the narrowest useful level.

Examples:

- If a message is not a lead because the person is an expert giving advice, store feedback on the lead.
- If "камера" creates too much noise, mute/reduce the term, not the entire video category.
- If `Dahua Hero A1` is correct, approve the item and its precise model terms.
- If a price is outdated, expire the offer/attribute, not the product.
- If a contact reason is not useful, dismiss or snooze the reason without deleting the underlying client interest.
- If an old interest becomes relevant because of a new catalog item, create a contact reason rather than mutating the original interest.

Feedback events do not need to immediately mutate catalog rows in every case. Some actions can create review tasks first. The audit log records any resulting mutation.

## Error Handling

- Sync failures are recorded on sources/extraction runs and surfaced in web UI.
- AI extraction failures do not silently become "no facts".
- AI lead-detection failures do not silently become "no leads".
- Document parse failures keep artifact metadata and error text.
- Duplicate source detection uses `(source_type, origin, external_id)` and content hash.
- Telegram flood wait should pause the specific sync job and record retry time.

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
3. Seed empty CRM tables and Oleg's Telegram-authenticated web user.
4. Keep the current Telegram bot/userbot runtime.
5. Replace JSON lead persistence with SQLite.
6. Add PUR channel sync into the same userbot runtime.
7. Add parser/extractor pipeline.
8. Generate classifier prompt/keyword index from SQLite.
9. Add web UI for catalog/leads/CRM/settings.
10. Deprecate JSON files after stable operation.

## Testing Strategy

Unit tests:

- source identity and duplicate detection;
- artifact download policy;
- document parsing into chunks;
- extracted fact normalization;
- catalog status inclusion;
- classifier version creation;
- lead match persistence;
- feedback event handling;
- manual client/contact/interest/asset creation;
- contact reason generation from catalog changes;
- task and touchpoint persistence.

Integration tests:

- process archived `@purmaster` corpus into catalog candidates;
- manual Telegram link creates source and example;
- `auto_pending` term triggers lead and stores `lead_matches`;
- feedback `term_too_broad` changes future classifier behavior;
- duplicate message ids across chats do not deduplicate incorrectly;
- confirmed lead can be linked to a client and interest;
- new catalog item creates a contact reason for an old matching interest;
- dismissed contact reason does not delete the client interest;
- manual installed asset can create a future support follow-up.

Live/smoke tests:

- userbot can read configured channel;
- document downloads skip videos and fetch PDFs;
- bot can send notifications;
- web settings persist;
- Telegram login payload is verified and mapped to a local user;
- unauthorized Telegram users cannot access the web UI;
- CRM Today screen can load leads, contact reasons, and due tasks from SQLite.

## Resolved Configuration Decisions

These policies are not hard-coded. They are settings in the web interface:

- which users/roles besides Oleg can approve or reject catalog facts;
- whether `auto_pending` matches are visually marked as lower-confidence in Telegram notifications;
- whether old campaign prices auto-expire when no explicit date is found;
- the default expiry period for campaign prices and offers;
- which external domains besides Telegraph are fetched automatically.

The web interface itself is protected by Telegram authentication.
