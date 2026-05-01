# Continuous Telegram Ingest And Chat Analytics Layer

Date: 2026-04-30

Status: target design, based on the earlier Chat Analyzer v2.1 plan,
`chat-analytics`, `tg_analyzer`, and `tg_fetcher` references. Current
implemented/not-implemented status is tracked in `docs/README.md`.

## Goal

Build the canonical raw Telegram knowledge layer for PUR.

The system must continuously read configured Telegram sources through userbot accounts, preserve every readable message, and turn the message stream into reproducible analytical layers: canonical raw rows, normalized text, POS-tagged tokens, per-message features, threads, entities, search indexes, QA pairs, topic summaries, and knowledge artifacts.

Catalog extraction, lead detection, CRM follow-up reasons, and "ask your chat" are downstream consumers of this layer. The ingest layer itself must not silently decide that a message is a catalog fact or a lead.

Catalog inputs are source-agnostic. Channels, chats, private correspondence, manual uploads, external pages, and documents all become evidence packets before catalog extraction. The catalog-facing plan is documented in `docs/superpowers/plans/2026-04-30-source-agnostic-catalog-ingest-plan.md`.

## Core Principles

- Nothing is lost, everything is marked. All readable messages are stored. Filtering is done in reports, indexes, classifiers, and UI views, not by deleting raw input.
- One responsibility per stage. Telegram read, raw storage, normalization, feature extraction, entity resolution, topic modeling, catalog extraction, and lead detection are separate concerns.
- SQLite is the hot operational store. Parquet with Zstandard compression is the compact analytical/archive layer.
- Telegram is read through the canonical Telegram client/runtime layer. Live monitoring uses `poll_monitored_source`; explicit reusable history acquisition uses `export_telegram_raw`. Both share the same source configuration, userbot assignment, scheduler, audit, raw export writer, and canonical row model.
- LLM is used only where rules/NLP are insufficient and only through configured providers, model profiles, prompt versions, and trace logging.
- Every LLM stage has a deterministic fallback or a clear `needs_human` state.
- Human-in-the-loop is mandatory at critical quality gates: data quality, entity resolution below high confidence, topic merging/renaming, final knowledge report, and catalog promotion.
- All thresholds, languages, model choices, prompt versions, and retention policies are configured in web settings or config tables, not hard-coded.
- Incremental processing is first-class. Every stage must be able to process only new messages since the last checkpoint or dirty window.
- Safety and auditability are product requirements: PII flags, optional anonymization for exports, prompt/response traces, config hashes, schema versions, and reproducible stage runs.

## Reference Sources

The design imports ideas from earlier work:

- `chat-analytics`: parquet-first analytical pipeline, canonical message schema, data quality metrics, thread/knowledge extraction.
- `tg_analyzer`: batch LLM analysis, strict JSON output, message link validation, discussion merge, quality/practical-value scoring.
- `tg_fetcher`: continuous/incremental modes, progress tracking, reactions/comments extraction, versioned schema, observability.

The product does not reuse these as separate services. Their useful decisions are folded into the current SQLite-backed worker/runtime architecture.

## Storage Model

### Hot SQLite Layer

SQLite remains the source of truth for the running application:

- source configuration and checkpoints;
- `source_messages` canonical Telegram message identity;
- scheduler jobs and runs;
- lead/catalog/CRM state;
- FTS5/search indexes;
- audit and AI traces;
- operator review status.

The first implementation may store normalized/enriched fields directly in existing or new SQLite tables. Larger analytical snapshots can be materialized into parquet.

### Parquet Analytical Layer

Parquet is the compact immutable/append-only analytical archive:

```text
data/archive/telegram_messages/
  source_id=<monitored_source_id>/
  year=2026/
  month=04/
  day=30/
  part-000001.parquet
```

Default format:

- `parquet_zstd`;
- schema version stored in metadata and archive manifest;
- partitioned by source and date;
- readable back through DuckDB, pyarrow, or a restore job.

Parquet is not a replacement for SQLite. It is used for:

- "ask your chat" batch/RAG experiments;
- retro research;
- rebuilding search/vector indexes;
- compact archive and restore;
- large analytical reports without loading hot SQLite payload columns.

### Search Layer

Search starts with SQLite FTS5:

- raw/clean text indexed by message and thread;
- Russian wildcard/stemming normalization for common morphology, for example `пылесоса -> пылесос*`;
- rarity-weighted scoring so frequent commercial words such as `стоимость`, `куплю`, `продам` do not dominate rare product/entity terms;
- direct message links and source references in every answer.

Vector/semantic search is designed in but optional initially:

- local Russian/multilingual embeddings are preferred for cost and privacy;
- vector indexes are rebuildable from SQLite/parquet;
- vector search supplements FTS, it does not replace exact matching.

## Runtime Ingest Behavior

Telegram reading has two explicit job types:

- `poll_monitored_source`: continuous live/catchup polling for active sources.
- `export_telegram_raw`: operator-requested raw history acquisition for building a reusable JSON/JSONL/parquet source of truth before AI/NLP stages.

Source start modes:

- `from_now`: live monitoring starts from current/latest known message.
- `recent_days`: explicit historical window.
- `from_message`: starts after a specific public Telegram message id.
- `from_beginning`: explicit full backfill from the earliest available history.

Raw export range modes:

- `source_start`: derive the range from the source start mode.
- `from_beginning`: fetch from the earliest readable message.
- `recent_days`: fetch messages newer than `now - N days`.
- `since_date`: fetch messages newer than an explicit timestamp.
- `from_message`: include a specific message id and newer messages.
- `after_message`: fetch messages after a specific message id.
- `since_checkpoint`: fetch only messages after the source checkpoint. If no checkpoint exists, skip instead of unexpectedly exporting everything.
- `from_now`: no historical raw export; useful only as a live-monitoring start mode.

Raw export media policy:

- `media.enabled`: download no media unless explicitly enabled.
- `media.types`: allowed media classes, for example `document`, `photo`, `video`, `audio`, `other`.
- `media.max_file_size_bytes`: hard per-file limit. Files over the limit are preserved as metadata with `raw_export_download.status = skipped` and `skip_reason = file_too_large`.
- Videos are not downloaded by default. They are downloaded only if the policy explicitly allows `video`.
- Every download/skip/error decision is written into `media_metadata_json.raw_export_download` and therefore into JSON, JSONL, parquet, and SQLite canonical rows.

`poll_monitored_source` has two runtime phases:

- `catchup`: history/backlog is still being drained. Use bounded larger batches and schedule the next poll quickly when the batch is full.
- `live`: backlog appears drained. Use the configured source poll interval.

Required behavior:

- keep one canonical checkpoint per source;
- persist each bounded batch before scheduling more work;
- deduplicate by `(monitored_source_id, telegram_message_id)`;
- query existing messages only for the current batch IDs, not for the whole source history;
- update `next_poll_at`, `last_success_at`, `last_error`, and result summary after every poll;
- record fetched, inserted, duplicate, text/media/document/url counts;
- enqueue downstream jobs only when the relevant source settings are enabled.
- `export_telegram_raw` must not enqueue AI, catalog extraction, lead classification, OCR, or external fetch jobs. Downstream processing starts only after an explicit later stage/job.
- `export_telegram_raw` updates the checkpoint only after fetched messages are safely written, so later `since_checkpoint` exports can be incremental.

Downstream jobs may include document download, external page fetch, local parse, OCR, text normalization, analytics materialization, catalog extraction, lead classification, and search index rebuild. These are downstream processing jobs, not alternate Telegram read paths.

## Pipeline Stages

Every stage accepts the previous stage output and does not mutate raw input.

### Stage 0. Ingest: Raw To Canonical

Purpose: transform Telegram input into a validated canonical message layer while preserving the original raw structure.

Inputs:

- live/backfill Telethon messages from monitored sources;
- optional Telegram Desktop JSON import for offline migration/testing.

Canonical fields:

- `source_message_id`: internal stable ID.
- `monitored_source_id`: configured source identity.
- `telegram_message_id`: Telegram message ID inside the source.
- `chat_id` / `telegram_id`: Telegram source identity when known.
- `message_date_utc`.
- `original_timezone`.
- `sender_id`.
- `sender_display`.
- `canonical_user_id`: optional alias-resolved or anonymized author identity.
- `text`.
- `caption`.
- `raw_text`: text + caption where appropriate.
- `reply_to_message_id`.
- `thread_id`: Telegram grouped media id or reconstructed thread id when available.
- `forwarded_from`.
- `urls_json`: extracted URLs.
- `media_type`.
- `media_metadata_json`.
- `reactions_breakdown_json`.
- `is_edited`.
- `is_service`.
- `message_type`: `text`, `media`, `voice`, `service`, `other`.
- `pii_detected`.
- `extra_json`: original raw Telegram metadata without lossy normalization.
- `fetched_at`.
- `pipeline_version`.
- `schema_version`.

Processing:

- for Telegram chats/channels, fetched batches are first written as a raw export run;
- the raw export run writes Telegram Desktop-compatible JSON plus JSONL files before canonical SQLite rows are created;
- the raw JSON/JSONL files are then materialized to parquet with `zstd` compression;
- canonical SQLite rows keep `archive_pointer_id = raw_export_run_id` and raw export paths in `raw_metadata_json.raw_export`;
- normalize date to UTC while keeping original timezone;
- extract URLs, media metadata, reactions, forwarding metadata, reply metadata;
- optionally anonymize `sender_id`/author fields for exported analytical artifacts;
- detect PII: phone numbers, emails, and other configured patterns;
- validate with typed schema. Pydantic is enough for row-level validation; Pandera or equivalent dataframe validation is recommended when materializing parquet.

Outputs:

- primary raw export run:
  - table: `telegram_raw_export_runs`;
  - output root: `data/raw/telegram/source_id=<id>/dt=YYYY-MM-DD/run_id=<uuid>/`;
  - files: `result.json`, `messages.jsonl`, `attachments.jsonl`, `messages_raw.parquet`, `attachments_raw.parquet`, `manifest.json`;
  - format marker: `tdesktop_compatible_json_v1`;
  - `result.json.messages[].raw_telethon_json` stores the best-effort JSON-safe Telethon payload:
    `message`, `sender`, `chat`, `media`, `document`, `reply_to`, `fwd_from`, `action`, `reactions`, `entities`, `buttons`, `via_bot`;
  - Telethon `datetime` values are stored as ISO strings; raw `bytes` are stored as base64 objects with explicit encoding metadata;
  - compression: parquet `zstd`;
  - AI is not called and no AI jobs are enqueued by this raw stage;
- canonical hot store:
  - SQLite `source_messages` and related raw metadata columns;
  - catalog mirror tables `sources`, `artifacts`, `parsed_chunks` when the source is enabled for catalog ingestion;
- secondary canonical snapshot:
  - CLI: `pur-leads archive catalog-raw [--monitored-source-id <id>]`;
  - output root: `data/archive/catalog_raw/dt=YYYY-MM-DD/run_id=<uuid>/`;
  - purpose: operational snapshot of canonical SQLite tables, not the primary raw source of truth.

Invariants:

- all fields are present with `null` instead of missing keys;
- messages with empty text and service/media messages are preserved;
- raw original metadata is available in `extra_json`;
- JSON fields are serializable and restorable;
- `source_message_id` and `(monitored_source_id, telegram_message_id)` remain stable.

Human validation:

- sample 50-100 raw messages per new source;
- compare Telegram/raw JSON against canonical rows;
- verify message ID, text/caption, reply target, URL extraction, media flags, reactions, and PII flags.

### Stage 1. EDA And Data Quality

Purpose: decide whether a source is useful and expose data quality before downstream work.

Metrics:

- `total_messages`;
- `unique_authors`;
- `date_min`, `date_max`;
- `has_text_ratio`;
- `has_url_ratio`;
- `has_reactions_ratio`;
- `message_type_distribution`;
- duplicate message IDs;
- future dates;
- PII ratio;
- media/document ratio;
- reply ratio;
- service message ratio.

Rules:

- `has_text_ratio < 0.1`: warn "low knowledge density".
- `unique_authors == 1`: warn "not a dialogue"; still useful for catalog/channel content.
- invalid dates or duplicate identities require operator-visible warnings.

Output:

- `reports/eda_summary.json`;
- UI source health panel;
- auditable quality gate record.

Human decision:

- `go`;
- `go_with_warnings`;
- `pause_source`;
- `needs_mapping_or_settings`.

### Stage 2. Text Normalization

Purpose: prepare text for search, NLP, and downstream extraction without deleting messages.

Fields:

- `raw_text`;
- `clean_text`: lowercased, whitespace-normalized, URLs masked as `[URL]`;
- `tokens_json`;
- `lemmas_json`;
- `pos_tags_json`;
- `token_map_json`: token -> lemma/POS/original span.

Language defaults:

- Russian: `pymorphy3`.
- English: spaCy small/medium model.
- POS tags are converted to Universal POS tags: `NOUN`, `PROPN`, `VERB`, `ADJ`, etc.

Invariants:

- all messages with text have `tokens_json`, `lemmas_json`, and `pos_tags_json`;
- `tokens`, `lemmas`, and `pos_tags` have equal lengths;
- if tokenization fails, fields become empty arrays and the message is not removed.

Human validation:

- review short replies, slang, transliteration, model names, product names, and technical terms.

### Stage 3. Per-Message Enrichment

Purpose: add interpretable signals to every message.

Features:

- `detected_lang`;
- `has_code`;
- `has_log`;
- `is_question_like`;
- `is_solution_like`;
- `is_thanks_like`;
- `is_problem_like`;
- `is_bot`;
- `canonical_user_id`;
- `has_noun_term`: at least one `NOUN` or `PROPN`;
- `technical_language_score`: share of `NOUN/PROPN` tokens;
- `url_count`;
- `reaction_count`;
- `has_document`;
- `has_external_link`.

Output:

- `data/processed/features.parquet` when materialized;
- SQLite feature table or columns for hot queries.

### Stage 4. Aggregated Stats

Purpose: build aggregate views for analysis and quality tuning.

Artifacts:

- n-grams, 1-3 grams;
- TF-IDF statistics;
- URL domain/category summary;
- reaction summary;
- author activity and answer/solution share;
- daily/hourly/monthly activity distributions.

Outputs:

- `reports/ngrams.json`;
- `data/enriched/url_data.json`;
- `reports/reaction_summary.json`;
- source statistics in the web UI.

Human validation:

- review top n-grams;
- update stop words, URL categories, and author aliases.

### Stage 5. Entity Extraction And Grouping

Purpose: extract and normalize domain entities using NLP signals and conservative resolution.

Candidate POS patterns:

- `[NOUN]`;
- `[NOUN NOUN]`;
- `[ADJ NOUN]`;
- `[PROPN+]`;
- configured product/model patterns.

Normalization:

- lowercase;
- punctuation normalization;
- transliteration pairs such as `смарттерм <-> smartterm`;
- configured aliases from catalog/operator feedback.

Grouping confidence:

- `exact`: high confidence;
- `translit`: medium confidence;
- `fuzzy` with Damerau-Levenshtein <= 2: low confidence.

Rules:

- automatic merge is allowed only for high confidence;
- medium and low confidence candidates stay separate until human review;
- review candidates must include evidence context and POS pattern.

Review artifact shape:

```csv
group_id,candidate_1,candidate_2,similarity_score,method,pos_pattern,example_context,action_status
```

Outputs:

- `data/enriched/entities.parquet`;
- `data/enriched/entity_groups.json`;
- `entity_resolution_candidates.csv`;
- future web entity-resolution queue.

### Stage 6. Thread Reconstruction

Purpose: restore dialogue structure.

Logic:

- build reply trees from `reply_to_message_id`;
- preserve Telegram channel post -> comments relationship when available;
- compute root ID, thread size, depth, participants, date range, time to first reply;
- create neighbor context windows around important messages.

Outputs:

- `data/processed/threads.parquet`;
- SQLite thread/context tables for hot UI and lead/catalog evidence.

### Stage 7. Search, Embeddings, And Vectorizers

Purpose: make the chat askable and make downstream stages reproducible.

Initial search:

- SQLite FTS5;
- Russian stemming/wildcard expansion;
- rarity-weighted score;
- result grouping by thread;
- exact message links.

Optional semantic layer:

- TF-IDF/CountVectorizer with `ngram_range=(1, 2)`;
- local embeddings such as Russian/multilingual small models;
- ChromaDB or another local vector index only after the FTS layer is stable.

Outputs:

- FTS tables;
- `data/models/vectorizers/*.joblib`;
- `data/models/embeddings.npy`;
- `mapping.json`.

Invariant:

- every indexed vector/search row maps back to `source_message_id` and Telegram URL when available.

### Stage 8. Topic Modeling

Purpose: identify discussion and knowledge themes.

Logic:

- NMF or TF-IDF clustering first;
- BERTopic or embedding clustering when embeddings are enabled;
- enrich topics with entities, URLs, problem/solution signals, and representative messages.

Outputs:

- `reports/topics.json`;
- `data/processed/message_topics.parquet`.

Human validation:

- rename, split, and merge topics;
- store operator label decisions for reproducibility.

LLM acceleration:

- optional topic label/description generation from top words and examples;
- fallback label is top 3 words joined.

### Stage 9. QA And FAQ Detection

Purpose: detect questions, candidate answers, and support knowledge.

Logic:

- question: `is_question_like == true`;
- answer: later message in same thread from another author;
- ranking signals:
  - important URL category;
  - reaction threshold;
  - thanks/confirmation from question author;
  - matching entities and topics;
  - expert/known-author score.

Outputs:

- `data/enriched/qa_pairs.json`;
- `reports/faq_draft.json`.

LLM acceleration:

- optional refinement: summarize the solution or return `NO_SOLUTION`;
- fallback is original answer text or top sentence by score.

### Stage 10. Knowledge Synthesis

Purpose: generate actionable knowledge, not just statistics.

Artifacts:

- FAQ: clustered QA into canonical pairs;
- experts: ranked by useful/resolved answers, reactions, URLs, and operator feedback;
- knowledge report:
  - top topics;
  - top entities;
  - problem map;
  - unresolved questions;
  - knowledge gaps;
  - POS-highlighted snippets.

Example highlighted snippet:

```json
{
  "highlighted": "<noun>смарттерм</noun> <noun>сервер</noun>"
}
```

Outputs:

- `reports/faq.json`;
- `reports/experts.json`;
- `reports/knowledge_report.json`;
- `reports/knowledge_gaps.json`;
- `entity_groups.json`;
- `texts.parquet`.

Human-in-the-loop:

- final review is required before using generated knowledge for pre-sales, documentation, or catalog promotion.

### Stage 11. Governance

Every artifact must include:

```json
{
  "pipeline_version": "2.1",
  "config_hash": "sha1(...)",
  "schema_version": "Message_v4"
}
```

Practices:

- incremental stage runs;
- golden standard samples under `tests/gold_standard/`;
- nightly smoke run;
- optional anonymization for exports;
- PII detection in stage 0;
- cloud LLM only when `allow_cloud_llm=true`;
- all LLM calls logged through the product AI trace layer;
- NLP model versions stored in `data/models/nlp/`;
- retention and archive policy controlled by settings.
- product-visible artifact inventory at `/artifacts`, backed by raw export run paths, stage `metadata_json` paths, and bounded filesystem discovery under artifact directories;
- safe previews for JSON/JSONL, Parquet, SQLite, text files, and directory listings.

## LLM Policy

Rules and local NLP are first-line mechanisms. LLM is a controlled accelerator.

Expected LLM use:

- topic label generation;
- QA solution refinement;
- knowledge report wording;
- catalog extraction from high-value chunks;
- strong-model validation when the system is idle.

Requirements:

- configured provider account;
- configured model profile;
- configured prompt version;
- full request/response trace;
- token/context usage;
- structured output when supported;
- deterministic fallback or `needs_human`;
- no silent catalog write from raw LLM output.

Target: LLM should touch <= 5% of messages in the full chat analytics pipeline unless the operator explicitly runs a broader analysis.

## Outputs And Product Use

| Artifact | Product use |
| --- | --- |
| `chat_raw.parquet` | Canonical raw analytical source |
| `texts.parquet` | POS/lemma/text analysis source |
| `features.parquet` | Message-level signal source |
| `threads.parquet` | Context, lead clustering, RAG, support analysis |
| `entity_groups.json` | Glossary, catalog aliases, search index |
| `entity_resolution_candidates.csv` | Human review queue |
| `faq.json` | Wiki, support, pre-sales, onboarding |
| `experts.json` | Support routing and confidence signals |
| `knowledge_report.json` | Competency map and knowledge overview |
| `knowledge_gaps.json` | Product backlog and content gaps |
| FTS/vector index | Ask-your-chat, operator search, retro research |

## Success Criteria

- 100K messages are processed through raw ingest and basic normalization in under 1 hour on the target server class.
- No readable Telegram message is dropped by the raw layer.
- Raw SQLite rows round-trip to parquet and back without losing identity, text, reply, URL, media, reaction, or raw metadata.
- POS tags are present for all tokenized text messages and are used in entity extraction, grouping, and visual highlighting.
- No automatic entity merge happens for `confidence != high`.
- FTS search returns exact message links and does not rank generic commercial words above rare domain terms.
- LLM stages have full fallback and full trace.
- Human review of final report takes under 30 minutes for a normal source slice.
- Catalog and lead detection consume this layer, not raw Telegram messages directly.

## Implementation Status Snapshot

Current detailed status is maintained in `docs/README.md`.

Completed first slice:

1. `poll_monitored_source` remains the live/catchup monitoring path.
2. `export_telegram_raw` exists for explicit reusable history acquisition with configurable range and media policy.
3. Raw Telegram export runs are stored as `result.json`, JSONL, `messages_raw.parquet`, `attachments_raw.parquet`, and `manifest.json`.
4. `from_beginning` source start mode exists.
5. Raw export runs can build canonical `source_messages` with `archive_pointer_id` pointing back to the raw run.
6. Automatic catalog AI extraction can be kept disabled while raw/NLP/search stages are rebuilt.
7. Raw ingest/export status, range, checkpoint, and media policy are represented in source/job metadata and visible through source/artifact/operations screens.
8. Stage 1 EDA produces source-level raw metrics and data-quality summary.
9. FTS5 search exists over normalized messages and artifact chunks with Telegram links.
10. Normalization/POS/features are implemented as staged parquet layers.

Implemented beyond the original first slice:

- external-page and document text extraction into `artifact_texts.parquet`;
- Chroma indexing and merged FTS/Chroma search;
- aggregated stats, POS-based entity extraction, entity ranking, and optional entity enrichment with full prompt/response trace;
- Telegram Desktop archive import into the same raw export model;
- product-visible artifact inventory at `/artifacts`.

Still pending from the full v2.1 pipeline:

- standalone `threads.parquet`;
- topic modeling;
- QA/FAQ detection;
- knowledge synthesis reports;
- full source-agnostic evidence UI and promotion workflow.
