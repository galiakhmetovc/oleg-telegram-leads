# End-To-End Lead Traceability Design

Date: 2026-05-01

Current implementation status is maintained in `docs/README.md`. This document
describes the target traceability model for explaining a lead from the web UI
back to the exact Telegram message, raw ingest artifact, catalog knowledge,
AI/rule decision, notification, and operator feedback.

## Goal

PUR Leads must be an auditable knowledge and lead-detection product, not only a
Telegram parser. For every operational lead, an administrator must be able to
answer:

1. What raw fact entered the system?
2. How was it normalized, indexed, and interpreted?
3. Which catalog knowledge, rules, prompt, model, and model profile were used?
4. What did the AI provider or deterministic classifier return?
5. Why did the system decide to create or update a lead?
6. What notification was sent to Telegram?
7. What did the operator change afterward, and how should that feedback improve
   the system?

The product-visible result is a `Trace` tab on every lead. The trace must show a
clickable chain from the lead card to the original Telegram message and every
important intermediate decision. The internal trace model should be compatible
with OpenTelemetry concepts, while Postgres remains the durable product audit
store.

## Product Principle

Every user-visible conclusion must answer: "Which source fact caused this?"

Traceability is not the same as log collection. Logs explain what a process did.
The trace graph explains why a user-facing product object exists and which facts,
versions, settings, and human actions shaped it.

## Trace Path

The canonical path for an operational Telegram lead is:

```text
lead_cluster
  -> lead_event
  -> source_message
  -> telegram_raw_export_run
  -> raw JSONL/parquet row and Telethon metadata
  -> normalized text / features / context
  -> catalog snapshot and matched catalog facts
  -> rule or AI decision record
  -> notification attempt and Telegram notification message
  -> feedback events and learning effects
```

Some leads will not have every node. For example, a manually added lead may not
have a `telegram_raw_export_run`, and a rule-only lead may not have an AI call.
The trace UI must show missing stages explicitly as "not used" rather than hide
them.

## Trace Nodes

### Lead Cluster

The cluster is the operator work item:

- cluster id, status, review status, work outcome;
- category, summary, confidence, commercial value;
- merge strategy and merge/split history;
- primary event and all member events;
- current assignee fields when role expansion is added later.

### Lead Event

The event is the detection fact:

- source message id;
- decision: `lead`, `maybe`, `not_lead`, or future values;
- detection mode: `fuzzy`, `llm`, `hybrid`, `manual`, `retro`, or configured
  route key;
- confidence and scoring fields;
- classifier version, catalog hash, prompt hash, model, settings hash;
- reason and notify reason;
- whether the event was retroactive.

### Source Message

The source message is the operational hot record:

- monitored source id and source purpose;
- Telegram `chat_id` / source identity;
- Telegram `message_id`;
- sender id and sender name;
- message date and fetched date;
- raw text, caption, normalized text;
- reply/thread identity;
- Telegram URL where possible;
- media metadata and artifact references.

### Raw Ingest

The raw ingest stage proves what was actually fetched:

- `telegram_raw_export_run.id`;
- source ref, source kind, username/title;
- userbot/account resource used for acquisition when available;
- configured acquisition range: from beginning, recent days, from message,
  since checkpoint, or explicit date;
- media policy and size limits;
- paths to `result.json`, `messages.jsonl`, `attachments.jsonl`,
  `messages_raw.parquet`, `attachments_raw.parquet`, and `manifest.json`;
- raw Telethon metadata for the message and attachment rows;
- skipped-media metadata when a file was not downloaded.

The trace must identify the raw row by a stable key:

```text
raw_export_run_id + telegram_message_id + attachment_id/chunk_id when needed
```

### Data Preparation

The preparation layer explains how raw text became searchable evidence:

- clean text;
- language;
- tokens, lemmas, POS tags, and token map;
- detected URLs, phones, prices, usernames, and quality signals;
- neighboring messages and explicit replies used as context;
- FTS document id and Chroma document id when a search/index hit contributed to
  the decision;
- artifact chunk ids for documents or external pages.

### Catalog And Knowledge

The trace must show the exact catalog knowledge used at detection time:

- classifier version and catalog hash;
- matched catalog item, term, offer, category, or exclusion;
- match type, matched text, score, weight, and status snapshot;
- whether the matched fact was approved, auto-pending, archived, or rejected at
  detection time;
- evidence chain for each matched catalog fact;
- snapshot entries that were available but ignored because they were negative,
  too generic, or below threshold.

The trace must distinguish:

- operational catalog truth used by lead detection;
- review-only analytics candidates;
- AI-suggested knowledge not yet approved;
- manual corrections.

### AI And Rule Decisions

Every AI or deterministic decision that can affect a lead must be visible:

- decision type and entity id;
- task/agent key;
- provider account resource;
- model and model profile;
- prompt version and prompt hash;
- rendered system and user prompt;
- request JSON with secrets redacted;
- response JSON and raw provider response;
- parsed structured output;
- token usage and context-window usage when available;
- retries, timeout policy, fallback route, and circuit breaker state;
- final decision, confidence, and reason.

For rule-only paths, the same UI area must show rule inputs and outputs:

- normalized candidate text;
- catalog snapshot rows considered;
- scores, thresholds, and rejection reasons;
- deterministic output JSON.

### Telegram Notification

If the lead produced a Telegram alert, the trace must show:

- notification route name;
- bot resource used;
- notification group id/title;
- notification status;
- Telegram notification message id;
- rendered notification text;
- delivery attempts, errors, and retry information.

If no notification was sent, the trace must show why:

- review-only mode;
- retro lead;
- muted source;
- low confidence;
- route disabled;
- delivery failure.

### Feedback And Learning

Operator feedback is part of the trace, not a side note:

- feedback target: cluster, event, match, term, sender, message, or catalog fact;
- action: confirmed, rejected, maybe, ignored, corrected, converted, etc.;
- reason code and comment;
- feedback scope: classifier, catalog, clustering, CRM outcome, source quality,
  manual example, or none;
- learning effect: positive example, negative example, match correction, term
  review, sender role hint, cluster training, source quality signal, or no
  classifier learning;
- linked evaluation case when feedback is promoted to a regression dataset.

## Data Model

The current schema already has many traceable entities:

- `lead_clusters`;
- `lead_events`;
- `lead_matches`;
- `feedback_events`;
- `decision_records`;
- `source_messages`;
- `telegram_raw_export_runs`;
- catalog tables and evidence tables;
- notification/job/audit tables;
- JSONL/parquet artifacts.

The missing product layer is a unified trace graph. The persisted product graph
should use OpenTelemetry-compatible names where practical:

### `trace_spans`

```text
id
trace_id
span_id
parent_span_id
span_name
span_kind
entity_type
entity_id
status
started_at
finished_at
duration_ms
actor
summary
attributes_json
```

Examples of `span_name`:

- `lead.cluster.created`;
- `lead.event.detected`;
- `message.ingested`;
- `message.normalized`;
- `catalog.snapshot.matched`;
- `ai.request.completed`;
- `rule.decision.completed`;
- `notification.sent`;
- `feedback.recorded`.

### `trace_span_events`

```text
id
trace_id
span_id
event_name
occurred_at
attributes_json
```

Examples:

- `retry.scheduled`;
- `rate_limit.hit`;
- `llm.response.parsed`;
- `notification.delivery_failed`;
- `operator.feedback_recorded`.

### `trace_span_links`

```text
id
trace_id
span_id
linked_trace_id
linked_span_id
relation_type
linked_entity_type
linked_entity_id
metadata_json
created_at
```

Examples of `relation_type`:

- `primary_event`;
- `source_message`;
- `raw_export`;
- `normalized_from`;
- `context_message`;
- `matched_catalog_fact`;
- `used_prompt`;
- `produced_decision`;
- `sent_notification`;
- `operator_feedback`;
- `created_evaluation_case`.

The trace layer must not replace domain tables or external OTel export. It links
domain records and artifacts into a product-visible explanation graph and can be
exported later to an OpenTelemetry Collector / Jaeger-compatible backend.

Do not store full raw texts, prompts, responses, documents, tokens, or secrets in
span attributes. Store stable IDs, hashes, and artifact references. Full product
evidence remains in domain tables and artifact storage with admin access checks.

## Trace Identity

Use one durable `trace_id` per product decision chain.

For operational leads:

```text
trace_id = lead_cluster.trace_id
```

If the first detection happens before the cluster exists, create a temporary
trace id at lead-event creation and attach it to the cluster when the event is
assigned.

For review-only analytics, use:

```text
trace_id = raw_export_run_id + stage_name + candidate_id
```

Review-only traces can later be promoted into an operational lead trace if a
candidate is accepted.

## Web UI

Every lead detail view must include a `Trace` tab with these sections:

1. Summary - compact reason why the lead exists.
2. Source - original Telegram message, sender, date, source, context, and link.
3. Ingest - raw export run, range/media policy, raw artifact paths, parquet row.
4. Preparation - normalization, features, search/index hits, artifact chunks.
5. Knowledge - catalog snapshot, matches, terms, evidence, status snapshots.
6. Decision - rule/AI inputs, prompt, response, parsed output, scoring, retries.
7. Notification - route, bot, group, rendered message, delivery status.
8. Feedback - operator actions, reason codes, learning effects, evaluation cases.

The UI must support:

- copy stable IDs;
- open related artifact preview;
- open raw JSON/parquet preview around the row;
- compare prompt/response side by side;
- show redacted request JSON by default, with secrets never exposed;
- mark missing stages as "not used" or "not available";
- export trace bundle as JSON for debugging or external review.

## API

Add read-only trace endpoints first:

```text
GET /api/leads/{cluster_id}/trace
GET /api/trace/{trace_id}
GET /api/trace/{trace_id}/bundle
```

`/api/leads/{cluster_id}/trace` returns a product-shaped payload for the UI.
`/api/trace/{trace_id}` returns normalized graph nodes and links.
`/api/trace/{trace_id}/bundle` returns a debug artifact with all linked domain
records and selected artifact previews, subject to size limits.

## Storage And Artifacts

The trace graph should point to artifacts; it should not duplicate full raw files
in SQLite. Store:

- stable path references;
- artifact ids;
- row keys;
- short previews;
- hashes when available;
- extracted metadata needed for UI filtering.

Raw files, parquet files, JSONL traces, FTS databases, and Chroma directories
remain in the artifact layer and are exposed through the existing `/artifacts`
screen.

## Error Handling

Trace collection must be best-effort but never silent:

- if a trace node cannot be written, record an audit/error event;
- lead creation must not fail solely because the optional trace graph write
  failed;
- AI/notification failures must still create trace events with `status=failed`;
- missing artifact files must render as broken references, not crash the UI;
- deleted or archived data must show archive pointers when available.

## Security

Trace data can contain sensitive messages and provider requests. Requirements:

- no secret tokens, API keys, session strings, or authorization headers in trace
  payloads;
- raw request JSON must be redacted before persistence;
- private correspondence and uploaded documents must carry source/privacy flags;
- trace bundle export must require admin access;
- future roles must allow separating "can view lead" from "can view raw prompt
  and raw message".

## Implementation Order

1. Add the trace graph tables and repository/service helpers.
2. Backfill trace links for existing lead clusters from existing domain tables.
3. Add `/api/leads/{cluster_id}/trace` and render the lead detail `Trace` tab.
4. Link current `decision_records`, `lead_matches`, `source_messages`, and
   `telegram_raw_export_runs`.
5. Link notification attempts and feedback events.
6. Route every future AI call through shared AI trace persistence and link those
   runs into the trace graph.
7. Add trace bundle export.

The first useful slice is intentionally narrow: open one existing lead and see
the path from `lead_cluster` to `lead_event`, `source_message`, catalog matches,
decision record, and original Telegram URL. Raw ingest/parquet, notification,
AI, and feedback sections can appear as linked panels as they are wired.

## Acceptance Criteria

- From a lead card, an admin can open one trace page without using SSH.
- The trace page shows the original Telegram message and link.
- The trace page shows every lead event in the cluster.
- The trace page shows every match that caused the lead decision.
- The trace page shows classifier/catalog/prompt/model metadata when available.
- The trace page shows a clear "not used" state for AI when a rule-only
  classifier created the lead.
- The trace page shows notification status or why no notification was sent.
- The trace page shows feedback and learning effect history.
- The trace API is covered by tests using at least one rule-only lead and one
  AI-assisted/review-only decision trace.
