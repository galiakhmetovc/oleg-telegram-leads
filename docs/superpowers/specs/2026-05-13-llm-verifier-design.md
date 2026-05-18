# LLM Verifier Design

## Goal

Add a local LLM verification layer for Telegram lead messages. The LLM does not replace deterministic extraction, dictionaries, facts, signals, or scoring. It audits the existing result and returns a strict JSON verdict that can support review decisions.

## Boundaries

- Deterministic NLP remains the source of facts, aliases, signals, scores, and review lanes.
- The LLM receives the message, current deterministic result, selected golden examples, and the active taxonomy.
- The LLM may recommend `keep`, `promote`, `demote`, or `manual_review`.
- The LLM may point to missing or suspicious fact/signal types, but it must not create active config.
- Backend validates the response against a schema before storing it.

## Context Pack

Each verification request builds a compact `llm_verification.v1` context pack:

- `message`: source message id, text, chat title, Telegram message id.
- `rule_engine_result`: current verdict, score, temperature, extracted facts, domain signals, reasons, and review lane.
- `available_taxonomy`: active fact types, catalog aliases grouped by `vendors`, `protocols`, `devices`, `software`, and domain signals.
- `golden_examples`: a small balanced sample of relevant lead and not-lead/noise examples.

Golden examples are selected by overlap with detected fact types, signal types, and simple text terms. The pack is intentionally small so local 1B-4B models can follow the task and keep JSON reliable.

## Output Contract

The model must return only JSON matching:

- `verdict`: `lead`, `not_lead`, or `uncertain`.
- `confidence`: number from 0 to 1.
- `recommendation`: `keep`, `promote`, `demote`, or `manual_review`.
- `agrees_with_rule_engine`: boolean.
- `matched_golden_ids`: list of golden ids.
- `missing_fact_types`: list of configured fact types that look missing.
- `suspicious_fact_types`: list of configured fact types that look wrong.
- `missing_signal_types`: list of configured signal types that look missing.
- `evidence`: short text snippets from the message.
- `anti_evidence`: short text snippets against the lead interpretation.

Invalid JSON, schema mismatches, and transport failures are stored as failed verification attempts and do not affect lead status.

## Runtime

The first supported runtime is Ollama-compatible HTTP:

- endpoint defaults to `http://localhost:11434/api/chat`;
- model name comes from settings;
- request uses `format` with JSON Schema and `temperature: 0`;
- response is parsed and validated by the backend.

The application layer depends on an interface so vLLM or llama.cpp can be added later without changing context building or persistence.

## Storage

Store each run in `llm_verifications`:

- source message id;
- enrichment job id used for deterministic result;
- model name;
- schema version;
- status;
- context pack;
- parsed response;
- raw response;
- error;
- timestamps.

This keeps LLM verification auditable and decoupled from message review.

## Initial API

Add `POST /api/v1/llm-verifications/messages/{source_message_id}`.

The endpoint builds the context pack from the latest stored enrichment result for the source message, calls the configured local LLM, stores the run, and returns it.

Add `GET /api/v1/llm-verifications/messages/{source_message_id}` to inspect existing runs.

## Testing

Backend tests cover:

- context pack includes message, deterministic facts/signals, selected golden examples, and active taxonomy;
- valid model JSON is stored as completed;
- invalid model JSON is stored as failed;
- endpoint returns 404 for missing source messages;
- API does not mutate deterministic lead status.
