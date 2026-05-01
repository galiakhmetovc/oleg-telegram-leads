# Source-Agnostic Catalog Ingest Plan

Date: 2026-04-30

Current implementation status is summarized in `docs/README.md`. This plan
describes the evidence/catalog direction and includes both implemented slices
and pending product work.

## Goal

Catalog input is not limited to `@purmaster` or public Telegram sources.

The system must treat any useful material as evidence: channel posts, group messages, private correspondence, forwarded message links, manually uploaded documents, pasted text, external pages, and documents received from clients or employees. Every input becomes traceable source material first. Catalog entries are created only through explicit extraction/review flows.

## Core Idea

The primary unit is not "Telegram channel". The primary unit is an evidence packet:

```text
evidence packet
  -> raw source
  -> optional artifact file
  -> parsed chunks
  -> search / analytics / entity extraction
  -> catalog candidates
  -> human review
  -> operational catalog rows
```

Telegram is only one transport for evidence packets.

## Input Types

Initial supported inputs:

- Telegram channel post, for example `@purmaster`.
- Telegram public group message.
- Telegram private group or DM visible to a configured Oleg/userbot account.
- Telegram message link pasted manually.
- Forwarded Telegram message or manually added example.
- Document attached to any Telegram message.
- Document uploaded manually through the web UI.
- Pasted text/manual note from Oleg.
- External page URL, for example Telegraph or vendor page.

Future supported inputs:

- Email attachments.
- CRM file attachments.
- Cloud drive links.
- Imported historical dumps.

## Evidence Graph

Every input is stored as a graph, not as a flat file.

Example: PUR channel post with attached PDF:

```text
monitored_source(@purmaster)
  -> source_message(telegram_message_id=123)
    -> raw_source(type=telegram_message)
    -> artifact(type=document, file=catalog.pdf)
      -> parsed_chunk(page=1)
      -> parsed_chunk(page=2)
```

Example: private chat with client and attached quote:

```text
monitored_source(private_chat_with_client)
  -> source_message(telegram_message_id=456)
    -> conversation_context(before/after/reply chain)
    -> artifact(type=document, file=quote.xlsx)
      -> parsed_chunk(sheet=prices)
      -> parsed_chunk(sheet=notes)
```

Example: manual upload:

```text
manual_upload
  -> raw_source(type=manual_document)
  -> artifact(type=document, file=manual_price.pdf)
    -> parsed_chunk(...)
```

The same parser, OCR, extraction, review, and evidence-linking pipeline works for all three.

## Source Scope

Not every extracted fact is allowed to become global catalog knowledge.

Each raw source/evidence packet has a scope:

- `global_catalog_candidate`: can become global PUR catalog knowledge after review.
- `catalog_reference`: useful context, but requires review before global use.
- `client_specific`: belongs to one client/contact/case and should feed CRM/support, not global catalog by default.
- `employee_internal`: internal knowledge; can be used for support/ops, but global promotion requires approval.
- `lead_example`: used to improve lead detection, not catalog facts by default.
- `do_not_extract`: stored for traceability/search only.

Default scope by source:

- `@purmaster`: `global_catalog_candidate`.
- Public vendor/product pages: `catalog_reference`.
- Public groups used for leads: `lead_example` or `catalog_reference`, depending on source purpose.
- Oleg private/client correspondence: `client_specific` by default.
- Employee/internal chats: `employee_internal` by default.
- Manual upload: selected by admin at upload time.

This prevents a private client quote, one-off discount, or internal discussion from silently becoming global catalog truth.

## Document Handling

Documents are first-class evidence regardless of where they came from.

Document pipeline:

```text
document discovered
  -> download/store artifact
  -> detect file type
  -> local parse when possible
  -> OCR when local parse is empty/low quality and OCR is enabled
  -> parsed chunks
  -> quality score
  -> search index
  -> optional catalog extraction
```

Rules:

- Video and audio are skipped by default.
- PDF/DOC/DOCX/XLS/XLSX/CSV/TXT are document candidates.
- Scanned PDFs/images need OCR, initially through configured OCR route such as `GLM-OCR`.
- The parsed text never loses the parent relation to the Telegram message/manual upload/external URL.
- Parser result stores status: `parsed`, `ocr_needed`, `ocr_done`, `parse_failed`, `unsupported`, `empty`.
- Extraction from documents is disabled or `needs_review` when source scope is private/client/internal.

## Conversation Context For Documents

When a document appears in ordinary correspondence, the file alone is often not enough.

For every document attached to a chat/DM message, the system should save a context bundle:

- message text/caption;
- sender;
- source chat;
- reply chain;
- N neighboring messages before and after;
- detected client/contact if known;
- source scope;
- explicit privacy flags;
- link to Telegram message when possible.

Example:

```text
Client: "Вот КП, которое мне прислали, можете подобрать аналог?"
Attachment: competitor_quote.pdf
```

The PDF can be useful for:

- CRM memory;
- competitor/reference analysis;
- lead understanding;
- maybe catalog gaps.

It must not automatically create PUR catalog offers unless Oleg explicitly promotes it.

## Processing Stages

## Current Telegram/Channel Implementation Status

Implemented local analytical path. Stages up to ranking are AI-free; Stage 5.2 is
the first optional LLM enrichment layer and always writes a full trace.

```text
Telegram raw export
  -> messages_raw.parquet / attachments_raw.parquet
  -> telegram-texts: normalized message text parquet
  -> telegram-artifacts: external page + downloaded document text parquet
  -> telegram-fts: SQLite FTS5 over messages + artifact chunks
  -> telegram-chroma: Chroma over messages + artifact chunks
  -> search telegram: merged FTS/Chroma RAG context
```

CLI commands:

```bash
pur-leads analyze telegram-texts \
  --raw-export-run-id <run_id>

pur-leads analyze telegram-artifacts \
  --raw-export-run-id <run_id>

pur-leads analyze telegram-features \
  --raw-export-run-id <run_id>

pur-leads analyze telegram-stats \
  --raw-export-run-id <run_id>

pur-leads analyze telegram-entities \
  --raw-export-run-id <run_id>

pur-leads analyze telegram-entity-ranking \
  --raw-export-run-id <run_id>

pur-leads analyze telegram-entity-enrichment \
  --raw-export-run-id <run_id> \
  --mode auto \
  --model GLM-5.1 \
  --model-profile catalog-strong

pur-leads analyze telegram-fts \
  --raw-export-run-id <run_id>

pur-leads analyze telegram-chroma \
  --raw-export-run-id <run_id> \
  --embedding-profile rubert_tiny2_v1

pur-leads search telegram \
  --raw-export-run-id <run_id> \
  --query "датчик протечки"
```

`telegram-artifacts` currently handles:

- external `http/https` pages found in Telegram text/caption/raw metadata, excluding Telegram message URLs;
- downloaded PDF/text-like documents referenced from `attachments_raw.parquet`;
- parent Telegram identity: `telegram_message_id`, `message_url`, source id, date when available;
- parser/fetch status: `extracted`, `failed`, `missing_file`, `empty_text`;
- normalized text fields compatible with message `texts.parquet`: `clean_text`, tokens, lemmas, POS tags, token map.

Artifact extraction is bounded by settings:

- `external_page_fetch_concurrency`;
- `external_page_fetch_timeout_seconds`, default `600`;
- `external_page_max_bytes`;
- `document_parse_concurrency`;
- `document_parse_timeout_seconds`, default `600`.

`telegram-features` currently implements Stage 3:

- combines message `texts.parquet` and `artifact_texts.parquet`;
- writes `data/processed/telegram_features/.../features.parquet`;
- marks question/offer/solution-like rows;
- extracts prices, phones, email, Telegram usernames, URLs;
- computes basic technical-language and text-quality signals;
- preserves source identity for message/document/page traceability.
- reserves feature-profile fields for future configurable extraction rules:
  `feature_profile_id`, `feature_profile_version`, `feature_profile_applied`;
- does not contain or apply hardcoded domain categories. Future domain-specific
  signals must come from configurable profiles, not from Python constants.

Reserved settings for future profile-driven enrichment:

- `telegram_feature_profiles_enabled`, default `false`;
- `telegram_feature_active_profile_id`, default `null`;
- `telegram_feature_profiles`, default `{}`;
- `telegram_feature_profile_assignment_rules`, default `[]`.

`telegram-stats` currently implements Stage 4:

- reads Stage 3 `features.parquet`;
- writes `data/enriched/telegram_stats/...`;
- produces `aggregated_stats.json`, `ngrams.json`, `entity_candidates.json`, `url_summary.json`, `source_quality.json`;
- aggregates terms, n-grams, URL domains, source quality, and message/artifact row counts.

`telegram-entities` currently implements Stage 5:

- reads Stage 3 `features.parquet`;
- extracts entity candidates only from POS patterns:
  `[NOUN]`, `[PROPN]`, `[NOUN NOUN]`, `[ADJ NOUN]`, and contiguous `[PROPN+]`;
- normalizes by lemma/lowercase/punctuation cleanup;
- writes `data/enriched/telegram_entities/.../entities.parquet`;
- writes `entity_groups.json` with exact-match groups only;
- writes `entity_resolution_candidates.csv` for transliteration/fuzzy candidates that require manual review;
- uses `auto_merge_policy = exact_only`. Medium/low confidence candidates are never merged automatically.

`telegram-entity-ranking` currently implements Stage 5.1:

- reads Stage 5 `entities.parquet`;
- preserves every raw entity row, but adds `score`, `ranking_status`,
  `reasons_json`, and `penalties_json`;
- writes `data/enriched/telegram_entity_rankings/.../ranked_entities.parquet`;
- writes `ranked_entities.json` with `promote_candidates`, `review_candidates`, and `noise`;
- writes `entity_noise_report.json` with penalty counts and noise samples;
- uses transparent rule-based scoring only. No AI and no domain profiles are applied.

Current ranking policy:

- `promote_candidate` when `score >= 0.65`;
- `review_candidate` when `0.35 <= score < 0.65`;
- `noise` when `score < 0.35`;
- positive signals: POS pattern quality, repeated mentions, multiple source refs, document/artifact mentions;
- penalties: `single_mention`, `single_token_generic`, `too_short`, `stop_term`,
  `low_information`, `mostly_numeric`, `contact_noise`, `navigation_noise`,
  `non_specific_modifier`.

`telegram-entity-enrichment` currently implements Stage 5.2:

- reads Stage 5.1 `ranked_entities.parquet`;
- selects `promote_candidate` and `review_candidate` rows;
- sends one ranked entity at a time to an enrichment client;
- before every request, loads relevant existing canonical entities and aliases from SQLite;
- stores the exact prompt text, request JSON, raw response JSON, parsed response JSON,
  provider, model, model profile, and context snapshot;
- applies the model decision deterministically through a resolver;
- writes canonical entities only as `auto_pending`, never as approved catalog truth.

The persistent memory between LLM requests is the canonical registry, not chat state.
If the first request creates `"Система умного дома"`, the second request receives that
entity in `known_canonical_entities`. The LLM must then either attach to it or explicitly
propose a different entity. If the proposal conflicts fuzzily with an existing canonical
entity, the resolver creates a `canonical_merge_candidates` row instead of duplicating it.

Stage 5.2 tables:

- `canonical_entities`: stable names such as `Система умного дома`, status
  `auto_pending|approved|rejected|merged`;
- `canonical_entity_aliases`: source terms and synonyms such as `умный дом`;
- `entity_enrichment_runs`: one enrichment pass over a ranked parquet;
- `entity_enrichment_results`: one prompt/request/response/decision trace per entity;
- `canonical_merge_candidates`: explicit review queue for possible duplicates.

Allowed enrichment actions:

- `attach_to_existing`: add alias/evidence to an existing canonical entity;
- `propose_new`: create a new `auto_pending` canonical entity when there is no conflict;
- `reject_noise`: keep the trace but do not update the registry;
- `needs_review`: keep the trace for manual review.

CLI modes:

- `--mode auto`: use configured Z.AI when an API key is available, otherwise use the
  deterministic rule-based fallback;
- `--mode llm`: require configured Z.AI and fail if unavailable;
- `--mode rule_based`: do not call external AI; still writes the same trace structure.

FTS/Chroma search results now expose `entity_type`:

- `telegram_message` for message text;
- `telegram_artifact` for document/page chunks, with `artifact_kind`, `artifact_id`, `source_url`, `file_name`, `chunk_index`.

This keeps raw acquisition reusable: a Telegram channel can be downloaded once, and downstream text, document, FTS, Chroma, and later catalog/AI stages can be rebuilt from parquet without rereading Telegram.

### Stage A. Intake

Create or locate a raw source:

- Telegram source/message;
- manual document;
- manual text;
- external page;
- private correspondence item.

Store source identity, origin, scope, owner/context, privacy flags, and raw metadata.

### Stage B. Artifact Collection

For every document:

- store artifact metadata;
- download file if it comes from Telegram;
- record local path, sha256, size, MIME type, original file name;
- skip unsupported media by policy.

### Stage C. Parse And OCR

Run local parsers first.

If parse output is empty or low quality:

- mark `ocr_needed`;
- enqueue OCR only when enabled and routed;
- store OCR result as parser output with provenance.

### Stage D. Chunking

Split text into chunks with metadata:

- page/sheet/section when available;
- token estimate;
- source offsets when available;
- parent artifact/source/message IDs.

### Stage E. Search And Analytics

Index source text and parsed chunks:

- FTS5 first;
- later semantic/vector index;
- source scope and privacy filters applied at query time.

### Stage F. Extraction

Extraction is a controlled action:

- input chunk/context is visible;
- prompt version is visible;
- provider/model/profile/route are visible;
- raw request and response are stored;
- output creates candidates, not silent global catalog writes.

### Stage G. Review And Promotion

Operator reviews candidates:

- approve as global catalog;
- keep as client-specific CRM memory;
- keep as support/internal knowledge;
- reject;
- merge;
- convert into lead example;
- mark as not useful.

## Product Flows

### PUR Channel Flow

```text
@purmaster post/document/link
  -> global_catalog_candidate scope
  -> raw/source/artifact/chunks
  -> search and analytics
  -> catalog candidates
  -> Oleg/admin review
  -> operational catalog
```

### Client Correspondence Flow

```text
client/Oleg chat message + document
  -> client_specific scope
  -> raw/source/artifact/chunks/context bundle
  -> CRM/support memory
  -> optional catalog gap/research candidate
  -> explicit promotion only if approved
```

### Employee/Internal Flow

```text
employee chat/document
  -> employee_internal scope
  -> internal support/ops knowledge
  -> explicit promotion to global catalog only after review
```

### Manual Upload Flow

```text
admin uploads file
  -> selects source scope and optional note
  -> artifact parse/OCR/chunks
  -> search/extraction/review
```

## Web UI Requirements

Add a source-agnostic evidence area:

- `Сырье / Evidence` list with filters by source type, scope, status, date.
- Manual upload action.
- Manual pasted text action.
- Telegram message link import action.
- Document detail page: file metadata, parse/OCR status, chunks, source message/context.
- Candidate extraction action per source/artifact/chunk.
- Scope selector and privacy warning.
- Promotion actions: catalog, CRM memory, lead example, research hypothesis.

The operator must always be able to answer:

- What did we receive?
- From where?
- Is it public, private, client-specific, or internal?
- What text did we extract?
- What prompt/model touched it?
- What candidates were created?
- What changed in the catalog, if anything?

## Settings

Required settings:

- default scope per source purpose/type;
- document download enabled;
- allowed MIME types;
- video/audio skip policy;
- local parser concurrency;
- OCR enabled;
- OCR route/profile;
- external fetch allowed domains;
- private-source extraction default: disabled or candidates-only;
- client-specific-to-global promotion requires explicit confirmation;
- raw/parquet retention policy;
- anonymization/export policy;
- PII detection enabled.

## First Implementation Slice

1. Document this source-agnostic evidence model.
2. Stop treating catalog ingest as channel-only.
3. Keep `poll_monitored_source` as the only Telegram read path.
4. Add/confirm raw source scopes.
5. Show raw Telegram messages and document artifacts in one evidence UI.
6. Let manual uploads create the same raw source/artifact/chunk records as Telegram documents.
7. Parse documents into chunks and search index before AI extraction.
8. Keep AI catalog extraction explicit and candidates-only for private/client/internal scopes.
9. Add audit fields so every catalog candidate points back to source message/document/chunk/context.
10. Only then wire controlled catalog extraction for `@purmaster`.

## Open Decisions

- Which private chats should be allowed as sources at all?
- Should private/client-specific sources be searchable by default, or only visible inside CRM/support context?
- What document types are enabled in the first parse implementation?
- Should manual upload require selecting `global_catalog_candidate`, `client_specific`, or `employee_internal` before saving?
- How strict should PII blocking be before cloud LLM calls?
