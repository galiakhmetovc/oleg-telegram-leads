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
```

Manual examples use the same downstream path:

```text
Oleg link/forward/manual text
  -> manual source or feedback event
  -> optional message fetch
  -> parsed source/chunk
  -> lead example / catalog fact / feedback
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
- `target_type`: `lead`, `lead_match`, `catalog_item`, `catalog_term`, `category`, `source`, `manual_input`
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

The UI can expose a small button set at first while the DB supports richer feedback.

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
- `notify_catalog_candidates = true`
- `notify_leads = true`
- `notify_ai_errors = true`

Settings are editable in the web interface and versioned through `audit_log`.

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
- source to parse;
- unclear / process automatically.

### Forwarded Message Flow

Forwarded messages are stored similarly. If the source chat can be resolved, the userbot fetches the original message to preserve link and metadata.

### Manual Text Flow

Manual text becomes `source_type = manual_text`. It can still create extracted facts, lead examples, or feedback.

## Web Interface

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

### Manual Input

Purpose:

- allow Oleg/admin to add examples and source links.

Inputs:

- Telegram link;
- forwarded message;
- raw text;
- catalog note.

Actions:

- save as positive lead example;
- save as negative lead example;
- parse as source;
- create/edit catalog fact;
- attach to existing item/category.

### Settings

Purpose:

- configure ingestion, auto-add, classifier inclusion, notifications.

Required controls:

- auto-add items/terms/attributes;
- use `auto_pending`;
- use `needs_review`;
- document/video/photo download switches;
- external link fetching;
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

## Feedback Loop

Feedback should update the system at the narrowest useful level.

Examples:

- If a message is not a lead because the person is an expert giving advice, store feedback on the lead.
- If "камера" creates too much noise, mute/reduce the term, not the entire video category.
- If `Dahua Hero A1` is correct, approve the item and its precise model terms.
- If a price is outdated, expire the offer/attribute, not the product.

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
3. Keep the current Telegram bot/userbot runtime.
4. Replace JSON lead persistence with SQLite.
5. Add PUR channel sync into the same userbot runtime.
6. Add parser/extractor pipeline.
7. Generate classifier prompt/keyword index from SQLite.
8. Add web UI for catalog/leads/settings.
9. Deprecate JSON files after stable operation.

## Testing Strategy

Unit tests:

- source identity and duplicate detection;
- artifact download policy;
- document parsing into chunks;
- extracted fact normalization;
- catalog status inclusion;
- classifier version creation;
- lead match persistence;
- feedback event handling.

Integration tests:

- process archived `@purmaster` corpus into catalog candidates;
- manual Telegram link creates source and example;
- `auto_pending` term triggers lead and stores `lead_matches`;
- feedback `term_too_broad` changes future classifier behavior;
- duplicate message ids across chats do not deduplicate incorrectly.

Live/smoke tests:

- userbot can read configured channel;
- document downloads skip videos and fetch PDFs;
- bot can send notifications;
- web settings persist.

## Open Questions

- Which users besides Oleg can approve/reject catalog facts?
- Should `auto_pending` matches be visually marked as lower-confidence in Telegram notifications?
- Should old campaign prices auto-expire after a default period if no explicit date is found?
- Which external domains besides Telegraph should be fetched automatically?

