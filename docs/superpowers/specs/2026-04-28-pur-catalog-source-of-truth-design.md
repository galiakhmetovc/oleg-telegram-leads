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

Stores state changes.

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

- manual source links;
- forwarded examples;
- simple commands for status/resync.

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
