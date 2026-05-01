# Catalog LLM Trace And Prompt Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Current implementation status is summarized in `docs/README.md`. This plan is
the target for full prompt registry, AI trace, and catalog rebuild auditability;
only parts of it are implemented today.

**Goal:** Make catalog construction manually controllable first, then AI-assisted and observable: Oleg must be able to edit the catalog directly before any AI processing, and every later catalog LLM call must expose the full prompt, provider request, provider response, parsed output, token/context usage, selected model profile, retries, and downstream catalog changes.

**Architecture:** Start with a manual catalog editor over the canonical SQLite catalog tables. Then add raw ingest visibility, prompt registry, AI trace persistence, and AI extraction as an explicit action whose output lands as editable candidates/diffs, not as silent catalog changes. Operator edits and approvals become feedback for prompt improvement and evaluation.

**Domain model note:** The catalog is a general knowledge base for interpreting requests, not a sales-only catalog. It can store sellable products, services, support topics, problems, constraints, exclusions, pricing facts, availability facts, and operational actions. Existing internal names like `catalog_items` and `catalog_offers` remain for compatibility, but UI, prompts, and review flows should speak in terms of entities, terms, request signals, exclusions, conditions, and actions.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy Core, Alembic, SQLite, existing worker scheduler, existing AI registry/model profiles, Material Web frontend.

---

## Scope

This plan intentionally starts with **catalog building**. Lead LLM arbitration, CRM prompts, OCR prompts, and notification prompts should reuse the same prompt/trace layer later, but they are not the first delivery target.

The first product-visible result must be a **manual catalog editor**. AI processing comes after that, because AI output must be reviewed, corrected, accepted, rejected, and used as feedback for prompt/model improvement.

The second product-visible result must be a single end-to-end catalog ingestion trace:

1. What was received from catalog ingest, especially a Telegram channel/message/document chunk.
2. Which provider, provider account, model, model profile, route, prompt version, and rendered prompt were used.
3. What the LLM returned, both raw provider response and parsed structured output.
4. What changed in the catalog: extracted facts, created/updated candidates, candidate statuses, evidence links, and classifier snapshot changes.

Must deliver first:

- Manual CRUD for catalog entities, terms/synonyms, conditions/actions, request signals, exclusions, categories, and evidence/source refs.
- Manual catalog changes must immediately rebuild or invalidate the classifier snapshot explicitly, with a visible action.
- Full LLM request/response visibility for `catalog_extraction`.
- Admin-managed prompt versions for `catalog_extraction`.
- Model/profile/prompt comparison for catalog extraction.
- Safe application path from extracted facts to candidates.
- Review/edit flow where AI results become editable candidates/diffs before promotion into the canonical catalog.
- Feedback records from manual edits/rejections that can be attached to prompt versions and evaluation cases.
- Snapshot hygiene fix so `negative_phrase` and generic commercial words do not create positive fuzzy matches.

Must not do first:

- Replace all lead detection with LLM.
- Rewrite scheduler/resource routing.
- Build a separate AI execution path outside the existing worker/runtime stack.

---

## File Structure

Create:

- `src/pur_leads/services/catalog_editor.py`
  Manual CRUD service for canonical catalog entities and explicit snapshot rebuilds.
- `migrations/versions/0023_prompt_registry_and_catalog_ai_traces.py`
  Adds prompt registry tables and trace/linking columns.
- `src/pur_leads/models/prompts.py`
  SQLAlchemy table definitions for prompt families and versions.
- `src/pur_leads/services/prompts.py`
  Prompt CRUD, activation, rendering, hashing, and seed defaults.
- `src/pur_leads/services/ai_traces.py`
  AI run/output persistence helpers for full request/response traces.
- `src/pur_leads/web/routes_prompts.py`
  Prompt management API.
- `tests/test_prompt_service.py`
  Prompt versioning/rendering/hash behavior.
- `tests/test_ai_trace_service.py`
  Full request/response trace persistence.
- `tests/test_web_prompt_routes.py`
  Prompt API coverage.
- `tests/test_catalog_editor_service.py`
  Manual catalog CRUD, evidence links, and snapshot rebuild coverage.

Modify:

- `src/pur_leads/models/ai.py`
  Add prompt trace fields to `ai_runs` / `ai_run_outputs` if missing.
- `src/pur_leads/models/catalog.py`
  Link `extraction_runs` to AI run/output, prompt version/hash, selected route/profile/account/model, context metrics.
- `src/pur_leads/models/__init__.py`
  Import prompt metadata for table creation/migrations if needed.
- `src/pur_leads/db/migrations.py`
  No behavior change expected; migration tests should discover new revision.
- `src/pur_leads/integrations/ai/chat.py`
  Extend `AiChatCompletion` with redacted `raw_request_json`.
- `src/pur_leads/integrations/ai/zai_client.py`
  Return full provider payload with secret headers redacted.
- `src/pur_leads/integrations/catalog/llm_extractor.py`
  Replace hard-coded prompt with prompt registry rendering; record prompt hash/version and trace IDs.
- `src/pur_leads/services/catalog_candidates.py`
  Store AI trace links and context metrics in extraction runs; keep AI outputs as editable candidates/diffs until explicitly promoted.
- `src/pur_leads/workers/runtime.py`
  Pass job/run identity into catalog extraction trace and persist links on success/failure.
- `src/pur_leads/services/classifier_snapshots.py`
  Keep negative phrases out of positive fuzzy keyword entries.
- `src/pur_leads/integrations/leads/fuzzy_classifier.py`
  Respect negative snapshot entries and ignore generic commercial stop terms as positive matches.
- `src/pur_leads/web/routes_operations.py`
  Add trace detail endpoints or extend extraction-run detail.
- `src/pur_leads/web/routes_catalog.py`
  Add manual catalog CRUD endpoints and surface extraction trace links from candidates/facts.
- `src/pur_leads/web/routes_pages.py`
  Add `/prompts` page and trace detail entry points.
- `src/pur_leads/web/static/app.js`
  Render prompt list/editor and AI trace request/response panels.
- `src/pur_leads/web/static/app.css`
  Add compact trace/prompt UI styling using existing Material Web conventions.
- `tests/test_llm_catalog_extractor.py`
  Update extractor tests for prompt registry and trace metadata.
- `tests/test_catalog_runtime_handlers.py`
  Assert extraction runs link to AI traces on success/failure.
- `tests/test_classifier_snapshot_service.py`
  Assert negative phrases are not emitted as positive keyword entries.
- `tests/test_fuzzy_catalog_classifier.py`
  Regression test for seller listing / `стоимость` false positive.
- `tests/test_web_operations_routes.py`
  Assert full AI trace details are visible through API.
- `tests/test_web_catalog_routes.py`
  Assert manual catalog CRUD and candidates/facts trace references.
- `tests/test_web_pages.py`
  Assert `/prompts` page is admin-protected and rendered.
- `docs/superpowers/specs/2026-04-28-pur-catalog-source-of-truth-design.md`
  Update the main spec with prompt management, full LLM trace requirements, and catalog-first rollout.

---

## Data Model

The first UI workflow is not “AI logs” in isolation. It is **Catalog Ingest Trace**:

```text
Telegram channel/document chunk
  -> extraction run
  -> AI run/output
  -> raw request/prompt/model/profile
  -> raw response/parsed facts
  -> extracted_facts
  -> catalog_candidates/catalog_candidate_facts
  -> classifier snapshot entries, when rebuilt
```

Every table change below exists to make that chain clickable and auditable.

### Manual Catalog Editor

Manual editor is the first layer and writes to the canonical catalog tables directly:

- `catalog_categories`
- `catalog_items`
- `catalog_terms`
- `catalog_offers`
- `catalog_attributes`
- `catalog_relations`
- `catalog_evidence`
- `catalog_versions`
- `classifier_versions`
- `classifier_snapshot_entries`

Manual editor must support:

- create/edit/archive product/service/solution items;
- create/edit/archive terms and synonyms;
- create/edit/archive lead phrases;
- create/edit/archive negative phrases;
- create/edit/archive offers/prices;
- attach evidence from manual text, Telegram links, documents, or external pages;
- add an operator note explaining why the catalog changed;
- explicitly rebuild classifier snapshot after changes;
- show which snapshot version is currently active.

AI extraction must not write directly to these canonical tables. AI writes candidates/facts/diffs. Human review promotes those into the manual catalog tables. Manual corrections to AI candidates are stored as feedback:

```json
{
  "feedback_type": "catalog_ai_correction",
  "prompt_version_id": "...",
  "ai_run_output_id": "...",
  "original_candidate_json": {},
  "corrected_catalog_entity_json": {},
  "operator_reason": "wrong generic term / better synonym / not PUR-related"
}
```

This feedback later drives prompt edits and evaluation cases.

### Prompt Registry

Add `ai_prompts`:

- `id`
- `prompt_key`, unique, for example `catalog_extraction`
- `display_name`
- `task_type`, for example `catalog_extraction`
- `description`
- `status`: `active`, `archived`
- `default_output_schema_json`
- `metadata_json`
- `created_at`, `updated_at`

Add `ai_prompt_versions`:

- `id`
- `ai_prompt_id`
- `version_number`
- `version_label`, for example `catalog-extraction-v2`
- `status`: `draft`, `active`, `archived`
- `system_template`
- `user_template`
- `output_schema_json`
- `render_settings_json`
- `prompt_hash`
- `change_note`
- `created_by`
- `created_at`, `activated_at`

Rules:

- One active version per `prompt_key`.
- Activating a version archives the previously active version for the same prompt.
- `prompt_hash` must be computed from templates, schema, and render settings.
- Prompt rendering must store both rendered messages and source prompt version metadata in the AI trace.

### AI Trace

Use existing `ai_runs` and `ai_run_outputs` as the canonical trace tables. Add only missing fields:

- `ai_runs.prompt_version_id`
- `ai_runs.prompt_key`
- `ai_runs.prompt_version`
- `ai_runs.prompt_hash`
- `ai_run_outputs.prompt_version_id`
- `ai_run_outputs.prompt_key`
- `ai_run_outputs.prompt_version`
- `ai_run_outputs.prompt_hash`
- `ai_run_outputs.context_window_tokens`
- `ai_run_outputs.context_fill_ratio`
- `ai_run_outputs.retry_count`
- `ai_run_outputs.error_type`
- `ai_run_outputs.provider_request_id`

`ai_run_outputs.raw_request_json` must contain:

- provider endpoint path, not full secret URL if it contains credentials;
- model;
- messages exactly as sent;
- temperature;
- max_tokens;
- response_format;
- thinking/reasoning settings;
- stream flag;
- provider options;
- redacted headers, for example `Authorization: Bearer ***`.

`ai_run_outputs.raw_response_json` must contain:

- raw provider JSON on success;
- raw provider error JSON on failure when available;
- HTTP status code and retry-after metadata when available.

### Catalog Links

Extend `extraction_runs`:

- `ai_run_id`
- `ai_run_output_id`
- `ai_provider_account_id`
- `ai_model_id`
- `ai_model_profile_id`
- `ai_agent_route_id`
- `prompt_version_id`
- `prompt_hash`
- `context_window_tokens`
- `context_fill_ratio`

This lets a user open a catalog extraction run and immediately see:

- which prompt was used;
- which provider/account/model/profile/route was used;
- full request and response;
- parsed facts;
- created/updated catalog candidates;
- token and context-window usage.

---

## Task 1: Manual Catalog Editor Foundation

**Files:**

- Create: `src/pur_leads/services/catalog_editor.py`
- Modify: `src/pur_leads/web/routes_catalog.py`
- Modify: `src/pur_leads/web/routes_pages.py`
- Modify: `src/pur_leads/web/static/app.js`
- Modify: `src/pur_leads/web/static/app.css`
- Create: `tests/test_catalog_editor_service.py`
- Modify: `tests/test_web_catalog_routes.py`
- Modify: `tests/test_web_pages.py`

- [ ] **Step 1: Write failing service tests for manual catalog CRUD**

Cover:

- create item with category, terms, attributes, and evidence;
- edit item name/description/category/status;
- add/remove terms and synonyms;
- add lead phrase and negative phrase as terms with clear `term_type`;
- add offer/price with status and optional TTL metadata;
- archive item/term/offer without deleting history;
- every manual change writes audit log.

- [ ] **Step 2: Implement `CatalogEditorService`**

Service methods:

```python
create_item(...)
update_item(...)
archive_item(...)
create_term(...)
update_term(...)
archive_term(...)
create_offer(...)
update_offer(...)
archive_offer(...)
attach_evidence(...)
rebuild_classifier_snapshot(...)
```

Rules:

- Manual writes use `created_by="admin"` or current actor.
- Manual entities default to `status="approved"`.
- `negative_phrase` terms must be stored as negative evidence and must not become positive fuzzy matches.
- Manual editor must not enqueue AI jobs.

- [ ] **Step 3: Add API endpoints**

Add admin-only endpoints:

```text
GET /api/catalog/items
POST /api/catalog/items
GET /api/catalog/items/{item_id}
PATCH /api/catalog/items/{item_id}
DELETE /api/catalog/items/{item_id}

POST /api/catalog/items/{item_id}/terms
PATCH /api/catalog/terms/{term_id}
DELETE /api/catalog/terms/{term_id}

POST /api/catalog/items/{item_id}/offers
PATCH /api/catalog/offers/{offer_id}
DELETE /api/catalog/offers/{offer_id}

POST /api/catalog/evidence
POST /api/catalog/snapshots/rebuild
GET /api/catalog/snapshots/latest
```

- [ ] **Step 4: Add UI before candidate review**

Catalog page tabs:

```text
Каталог | Кандидаты AI | Сырой ввод | Примеры лидов
```

The default tab must be `Каталог`.

Manual editor UI:

- table/list of catalog items;
- right-side editor;
- terms/synonyms section;
- offers section;
- evidence section;
- explicit button `Пересобрать снапшот`;
- snapshot status block.

- [ ] **Step 5: Keep current manual input but rename its meaning**

Current `Ручной ввод` is not catalog editing. Move it under `Сырой ввод` and make copy clear:

```text
Сырой ввод сохраняет материал для каталога или примеры. Он не меняет каталог сам по себе.
```

Default `auto_extract` must be off while we are in raw-ingest-first mode.

- [ ] **Step 6: Run manual catalog tests**

Run:

```bash
TMPDIR=$PWD/output/pytest-tmp uv run pytest tests/test_catalog_editor_service.py tests/test_web_catalog_routes.py tests/test_web_pages.py -q --basetemp=$PWD/output/pytest-manual-catalog-editor
```

Expected: pass.

---

## Task 2: Prompt Registry Migration

**Files:**

- Create: `migrations/versions/0023_prompt_registry_and_catalog_ai_traces.py`
- Create: `src/pur_leads/models/prompts.py`
- Modify: `src/pur_leads/models/ai.py`
- Modify: `src/pur_leads/models/catalog.py`
- Modify: `tests/test_db_migrations.py`

- [ ] **Step 1: Write failing migration test**

Add assertions that a fresh upgraded DB contains:

```python
"ai_prompts",
"ai_prompt_versions",
```

Also assert required columns exist on:

```python
ai_runs.prompt_hash
ai_run_outputs.raw_request_json
ai_run_outputs.context_fill_ratio
extraction_runs.ai_run_id
extraction_runs.prompt_hash
```

- [ ] **Step 2: Run migration test**

Run:

```bash
TMPDIR=$PWD/output/pytest-tmp uv run pytest tests/test_db_migrations.py -q --basetemp=$PWD/output/pytest-db-migrations
```

Expected: fail on missing tables/columns.

- [ ] **Step 3: Add SQLAlchemy model definitions**

Create `src/pur_leads/models/prompts.py` with `metadata`, `ai_prompts_table`, and `ai_prompt_versions_table`.

Update existing model definitions with trace columns.

- [ ] **Step 4: Add Alembic revision**

Create revision `0023_prompt_registry_and_catalog_ai_traces`, `down_revision = "0022_catalog_quality_reviews"`.

Use batch alter for SQLite table changes.

- [ ] **Step 5: Run migration test again**

Run:

```bash
TMPDIR=$PWD/output/pytest-tmp uv run pytest tests/test_db_migrations.py -q --basetemp=$PWD/output/pytest-db-migrations
```

Expected: pass.

---

## Task 3: Catalog Ingest Trace API Shape

**Files:**

- Modify: `src/pur_leads/web/routes_catalog.py`
- Modify: `src/pur_leads/web/routes_operations.py`
- Create or modify: `tests/test_catalog_ingest_trace_routes.py`

- [ ] **Step 1: Write failing API test for the first visible workflow**

Create a fixture with:

- one catalog source from Telegram;
- one parsed chunk;
- one extraction run;
- one AI run/output;
- one raw request with rendered prompt;
- one raw response;
- one extracted fact;
- one catalog candidate;
- one classifier snapshot entry.

Add endpoint:

```text
GET /api/catalog/ingest-traces/{extraction_run_id}
```

Expected response shape:

```json
{
  "ingest_input": {
    "source": {},
    "artifact": null,
    "chunk": {
      "id": "...",
      "text": "...",
      "token_estimate": 123
    },
    "telegram": {
      "channel": "purmaster",
      "message_id": 39,
      "message_url": "https://t.me/purmaster/39"
    }
  },
  "llm_request": {
    "provider": "zai",
    "provider_account": "Default Z.AI account",
    "model": "GLM-5.1",
    "model_profile": "catalog-primary-strong",
    "route": "catalog_extractor / primary",
    "prompt_version": "catalog-extraction-v2",
    "prompt_hash": "...",
    "context_window_tokens": 128000,
    "context_fill_ratio": 0.31,
    "raw_request_json": {}
  },
  "llm_response": {
    "status": "succeeded",
    "raw_response_json": {},
    "parsed_output_json": {},
    "token_usage": {}
  },
  "catalog_effect": {
    "extracted_facts": [],
    "catalog_candidates": [],
    "candidate_fact_links": [],
    "classifier_snapshot": {
      "version": 22,
      "entries_created": []
    }
  }
}
```

- [ ] **Step 2: Implement read-only trace assembler**

Do not create new behavior yet. Build the endpoint by joining existing and new trace tables.

This gives the UI and future debugging one canonical object: “what happened to this catalog ingest item?”

- [ ] **Step 3: Run route test**

Run:

```bash
TMPDIR=$PWD/output/pytest-tmp uv run pytest tests/test_catalog_ingest_trace_routes.py -q --basetemp=$PWD/output/pytest-catalog-ingest-trace
```

Expected: pass after Tasks 2, 4, and 5 provide the missing prompt/trace persistence fields.

---

## Task 4: Prompt Service And Default Catalog Prompt

**Files:**

- Create: `src/pur_leads/services/prompts.py`
- Create: `tests/test_prompt_service.py`
- Modify: `src/pur_leads/app.py` or startup/bootstrap path if defaults are seeded there

- [ ] **Step 1: Write prompt service tests**

Cover:

- creates default `catalog_extraction` prompt if missing;
- one active prompt version per prompt key;
- rendering returns messages and metadata;
- hash changes when templates/schema/settings change;
- render refuses inactive/archived prompt unless explicitly requested by version id.

- [ ] **Step 2: Define default catalog extraction prompt**

Move the hard-coded prompt from `LlmCatalogExtractor._prompt_messages()` into the prompt registry as version `catalog-extraction-v2`.

The prompt must explicitly instruct:

- extract only PUR-relevant smart-home/security/equipment catalog facts;
- do not treat generic price words as products/services/lead phrases;
- `negative_phrase` means negative classifier evidence, not a product or positive signal;
- distinguish buyer-demand phrases from seller-listing phrases;
- return strict JSON only.

Required output schema:

```json
{
  "facts": [
    {
      "fact_type": "product|service|solution|offer|lead_phrase|negative_phrase|term",
      "canonical_name": "string",
      "category": "slug|null",
      "terms": ["string"],
      "attributes": [{"name": "string", "value": "string"}],
      "offer": {"price_text": "string|null", "currency": "RUB|null"},
      "polarity": "positive|negative|neutral",
      "evidence_quote": "short exact quote",
      "confidence": 0.0
    }
  ]
}
```

- [ ] **Step 3: Implement renderer**

Renderer input for catalog extraction:

```python
{
    "source_text": "...",
    "source_id": "...",
    "chunk_id": "...",
    "source_kind": "telegram_channel|document|external_page|manual_text",
    "max_source_chars": 12000,
}
```

Renderer output:

```python
RenderedPrompt(
    prompt_key="catalog_extraction",
    prompt_version_id="...",
    prompt_version="catalog-extraction-v2",
    prompt_hash="...",
    messages=[AiChatMessage(...), AiChatMessage(...)],
    output_schema_json={...},
    render_settings_json={...},
    estimated_prompt_tokens=...
)
```

- [ ] **Step 4: Run service tests**

Run:

```bash
TMPDIR=$PWD/output/pytest-tmp uv run pytest tests/test_prompt_service.py -q --basetemp=$PWD/output/pytest-prompts
```

Expected: pass.

---

## Task 5: Full AI Trace Service

**Files:**

- Create: `src/pur_leads/services/ai_traces.py`
- Create: `tests/test_ai_trace_service.py`
- Modify: `src/pur_leads/integrations/ai/chat.py`
- Modify: `src/pur_leads/integrations/ai/zai_client.py`
- Modify: `tests/test_zai_chat_client.py`

- [ ] **Step 1: Write trace service tests**

Cover:

- `start_run()` creates `ai_runs` with task, agent, job, source/chunk metadata, prompt hash.
- `record_output_started()` creates `ai_run_outputs` with route/model/profile/prompt metadata.
- `finish_output_success()` stores raw request, raw response, parsed output, token usage, context metrics, provider request id.
- `finish_output_failure()` stores raw request, raw error response, error type, retry metadata.
- Secrets are redacted in raw request.

- [ ] **Step 2: Extend AI completion contract**

Add optional fields to `AiChatCompletion`:

```python
raw_request_json: dict[str, Any] | None = None
provider_request_id: str | None = None
```

Keep existing callers working.

- [ ] **Step 3: Return full provider request from Z.AI client**

In `ZaiChatCompletionClient.complete()` store:

- exact payload sent to `/chat/completions`;
- redacted headers;
- timeout config;
- base endpoint path.

Do not store API key.

- [ ] **Step 4: Compute context metrics**

In trace service:

```python
context_fill_ratio = prompt_tokens / context_window_tokens
```

Only compute when both values exist.

- [ ] **Step 5: Run AI trace tests**

Run:

```bash
TMPDIR=$PWD/output/pytest-tmp uv run pytest tests/test_ai_trace_service.py tests/test_zai_chat_client.py -q --basetemp=$PWD/output/pytest-ai-traces
```

Expected: pass.

---

## Task 6: Catalog Extractor Uses Prompt Registry And Trace

**Files:**

- Modify: `src/pur_leads/integrations/catalog/llm_extractor.py`
- Modify: `src/pur_leads/workers/runtime.py`
- Modify: `src/pur_leads/services/catalog_candidates.py`
- Modify: `tests/test_llm_catalog_extractor.py`
- Modify: `tests/test_catalog_runtime_handlers.py`

- [ ] **Step 1: Write failing extractor test**

Assert `LlmCatalogExtractor`:

- calls prompt service instead of hard-coded `_prompt_messages`;
- exposes `last_prompt_hash`, `last_prompt_version_id`, `last_ai_run_id`, `last_ai_run_output_id`;
- stores full request/response trace on success;
- stores full request/error trace when JSON parsing fails or provider fails.

- [ ] **Step 2: Inject prompt service and trace service**

Update constructor:

```python
LlmCatalogExtractor(
    client=...,
    model=...,
    session=...,
    prompt_service=...,
    ai_trace_service=...,
    model_profile_id=...,
    ai_agent_route_id=...,
    ai_provider_account_id=...,
)
```

Keep sensible defaults for tests.

- [ ] **Step 3: Replace hard-coded prompt**

Use active `catalog_extraction` prompt version unless job payload pins `prompt_version_id`.

Job payload may override:

```json
{
  "prompt_version_id": "...",
  "dry_run": true
}
```

- [ ] **Step 4: Persist trace links in extraction run**

When `extract_catalog_facts` finishes, `extraction_runs` must include:

- AI run/output ids;
- prompt hash/version id;
- provider/account/model/profile/route;
- token/context metrics.

- [ ] **Step 5: Run focused catalog tests**

Run:

```bash
TMPDIR=$PWD/output/pytest-tmp uv run pytest tests/test_llm_catalog_extractor.py tests/test_catalog_runtime_handlers.py -q --basetemp=$PWD/output/pytest-catalog-trace
```

Expected: pass.

---

## Task 7: First UI: Catalog Ingest Trace Viewer

**Files:**

- Modify: `src/pur_leads/web/routes_pages.py`
- Modify: `src/pur_leads/web/static/app.js`
- Modify: `src/pur_leads/web/static/app.css`
- Modify: `tests/test_web_pages.py`
- Create or modify: `tests/test_web_catalog_routes.py`

- [ ] **Step 1: Add trace entry points**

From catalog source/chunk/extraction run/candidate screens, expose one action:

```text
Открыть трассу ингеста
```

- [ ] **Step 2: Render four sections exactly in this order**

1. **Что получили из ингеста**
   - Telegram source/channel/message URL.
   - Document/page metadata if present.
   - Chunk text exactly as sent downstream.
   - Token estimate.

2. **Что ушло в LLM**
   - Provider, account, model, model profile.
   - Route/agent role.
   - Prompt version/hash.
   - Rendered system/user messages.
   - Full raw request JSON.
   - Context window and fill ratio.

3. **Что вернулось от LLM**
   - Raw provider response.
   - Parsed JSON.
   - Validation/parsing errors if any.
   - Token usage and latency.

4. **Как это повлияло на каталог**
   - Extracted facts.
   - Created/updated catalog candidates.
   - Candidate statuses.
   - Evidence links.
   - Snapshot version/entries created by rebuild.

- [ ] **Step 3: Keep it inspectable**

Use collapsible panels for large JSON/text blocks. Do not hide content behind summaries only; the full prompt and full response must be accessible in the page.

- [ ] **Step 4: Run UI/page tests**

Run:

```bash
TMPDIR=$PWD/output/pytest-tmp uv run pytest tests/test_web_pages.py tests/test_web_catalog_routes.py -q --basetemp=$PWD/output/pytest-ingest-trace-ui
```

Expected: pass.

---

## Task 8: Operations API For Full LLM Request/Response

**Files:**

- Modify: `src/pur_leads/web/routes_operations.py`
- Modify: `src/pur_leads/web/routes_catalog.py`
- Modify: `tests/test_web_operations_routes.py`
- Modify: `tests/test_web_catalog_routes.py`

- [ ] **Step 1: Write API tests**

Add endpoints:

```text
GET /api/operations/ai-runs
GET /api/operations/ai-runs/{ai_run_id}
GET /api/operations/ai-run-outputs/{output_id}
```

The detail endpoint must return:

- run metadata;
- output metadata;
- full `raw_request_json`;
- full `raw_response_json`;
- parsed output;
- token usage;
- context fill;
- linked `extraction_run`;
- linked facts/candidates when available.

- [ ] **Step 2: Extend extraction run listing**

Existing `/api/operations/extraction-runs` rows should include:

```json
{
  "ai_run_id": "...",
  "ai_run_output_id": "...",
  "prompt_version": "...",
  "prompt_hash": "...",
  "context_fill_ratio": 0.42
}
```

- [ ] **Step 3: Extend catalog candidate detail**

Candidate/fact detail should expose:

- extraction run id;
- AI run/output id;
- prompt version/hash;
- direct trace link id.

- [ ] **Step 4: Run route tests**

Run:

```bash
TMPDIR=$PWD/output/pytest-tmp uv run pytest tests/test_web_operations_routes.py tests/test_web_catalog_routes.py -q --basetemp=$PWD/output/pytest-web-traces
```

Expected: pass.

---

## Task 9: Prompt Management API And UI

**Files:**

- Create: `src/pur_leads/web/routes_prompts.py`
- Modify: `src/pur_leads/web/app.py`
- Modify: `src/pur_leads/web/routes_pages.py`
- Modify: `src/pur_leads/web/static/app.js`
- Modify: `src/pur_leads/web/static/app.css`
- Create: `tests/test_web_prompt_routes.py`
- Modify: `tests/test_web_pages.py`

- [ ] **Step 1: Write prompt API tests**

Endpoints:

```text
GET /api/prompts
GET /api/prompts/{prompt_key}
POST /api/prompts/{prompt_key}/versions
POST /api/prompts/{prompt_key}/versions/{version_id}/activate
PATCH /api/prompts/{prompt_key}/versions/{version_id}
POST /api/prompts/{prompt_key}/render-preview
```

Admin only.

- [ ] **Step 2: Implement API**

Behavior:

- list prompt families and active versions;
- create draft version from active version;
- edit draft only;
- activate version atomically;
- render preview using sample text;
- show prompt hash before activation.

- [ ] **Step 3: Add `/prompts` page**

UI:

- left list of prompt families;
- version table;
- active/draft/archived badges;
- editor for system/user templates;
- JSON schema editor as textarea/pre block for now;
- render preview with sample source text;
- activate button with confirmation.

- [ ] **Step 4: Add trace viewer UI**

In Operations and Catalog detail:

- "Запрос в LLM" panel;
- "Ответ LLM" panel;
- "Распаршенный результат" panel;
- model/profile/prompt/context summary.

Use compact monospace blocks, not huge cards inside cards.

- [ ] **Step 5: Run web tests**

Run:

```bash
TMPDIR=$PWD/output/pytest-tmp uv run pytest tests/test_web_prompt_routes.py tests/test_web_pages.py -q --basetemp=$PWD/output/pytest-prompts-web
```

Expected: pass.

---

## Task 10: Catalog Model/Prompt Evaluation Matrix

**Files:**

- Modify: `src/pur_leads/services/evaluation.py`
- Modify: `src/pur_leads/workers/runtime.py`
- Modify: `src/pur_leads/services/scheduler.py` if new job helpers are needed
- Modify: `src/pur_leads/web/routes_quality.py`
- Modify: `src/pur_leads/web/static/app.js`
- Create or extend: `tests/test_catalog_evaluation_matrix.py`

- [ ] **Step 1: Write evaluation tests**

Create a catalog extraction evaluation job that:

- selects a fixed set of parsed chunks;
- runs selected model profiles and prompt versions;
- stores outputs without applying candidates to the live catalog;
- stores full AI traces for every run;
- records metrics in `evaluation_runs.metrics_json`.

- [ ] **Step 2: Define metrics**

Minimum metrics:

- valid JSON rate;
- schema validation rate;
- fact count;
- supported evidence quote rate;
- duplicate candidate rate;
- generic bad term count;
- negative phrase leakage count;
- latency p50/p95;
- prompt tokens / completion tokens / total tokens;
- context fill ratio;
- retry/error count.

- [ ] **Step 3: Add comparison UI**

Quality page should show rows by:

```text
prompt version + provider account + model + model profile
```

For each row show quality metrics and links to sample traces.

- [ ] **Step 4: Run evaluation tests**

Run:

```bash
TMPDIR=$PWD/output/pytest-tmp uv run pytest tests/test_catalog_evaluation_matrix.py tests/test_web_quality_routes.py -q --basetemp=$PWD/output/pytest-catalog-eval
```

Expected: pass.

---

## Task 11: Snapshot Hygiene And Fuzzy Regression

**Files:**

- Modify: `src/pur_leads/services/classifier_snapshots.py`
- Modify: `src/pur_leads/integrations/leads/fuzzy_classifier.py`
- Modify: `tests/test_classifier_snapshot_service.py`
- Modify: `tests/test_fuzzy_catalog_classifier.py`

- [ ] **Step 1: Write regression test for the toilet false positive**

Input message:

```text
Унитаз-компакт Sanita Luxe Best Luxe с быстросъемным сиденьем микролифт WC.CC/Best/2-DM/TUR.G/S1

Стоимость 10000р

Ногинск. Бетонная ул. 2
@garik_noginsk
```

Given snapshot contains negative candidate:

```json
{
  "candidate_type": "negative_phrase",
  "polarity": "negative",
  "terms": ["дорого", "стоимость"]
}
```

Expected classifier result: `not_lead`, not `maybe`.

- [ ] **Step 2: Prevent negative phrases from positive keyword index**

In `ClassifierSnapshotService`, either:

- emit negative phrase entries as `entry_type="negative_term"` and exclude them from `KEYWORD_ENTRY_TYPES`; or
- keep the same entry type but include polarity and have fuzzy route it to negative matching.

Preferred: explicit `negative_term`, because it makes snapshot auditable.

- [ ] **Step 3: Add generic commercial stoplist**

Stoplist must include at least:

```python
"стоимость", "цена", "руб", "₽", "в наличии", "самовывоз"
```

These words cannot produce positive `maybe` by themselves.

- [ ] **Step 4: Add source mode hook**

Prepare, but do not overbuild:

```json
{
  "lead_policy": "default|marketplace"
}
```

For `marketplace`, seller listing patterns without buyer intent should be `not_lead`.

- [ ] **Step 5: Run fuzzy tests**

Run:

```bash
TMPDIR=$PWD/output/pytest-tmp uv run pytest tests/test_classifier_snapshot_service.py tests/test_fuzzy_catalog_classifier.py -q --basetemp=$PWD/output/pytest-fuzzy
```

Expected: pass.

---

## Task 12: Catalog Rebuild Workflow

**Files:**

- Modify: `src/pur_leads/web/routes_catalog.py`
- Modify: `src/pur_leads/workers/runtime.py`
- Modify: `src/pur_leads/services/scheduler.py`
- Modify: `src/pur_leads/web/static/app.js`
- Create or extend: `tests/test_catalog_rebuild_workflow.py`

- [ ] **Step 1: Write workflow tests**

Add ability to enqueue catalog rebuild over selected sources/chunks:

```json
{
  "source_ids": ["..."],
  "prompt_version_id": "...",
  "route_profile_ids": ["..."],
  "mode": "dry_run|apply",
  "replace_existing_candidates": false
}
```

- [ ] **Step 2: Implement dry-run mode**

Dry-run must:

- call LLM;
- store traces;
- parse facts;
- store evaluation/comparison output;
- not mutate live catalog candidates.

- [ ] **Step 3: Implement apply mode**

Apply mode must:

- create extracted facts;
- update candidates;
- rebuild classifier snapshot;
- record prompt/model/trace metadata.

- [ ] **Step 4: Add UI action**

Catalog page:

- "Перестроить каталог" action;
- choose sources/chunks;
- choose prompt version;
- choose model profiles;
- choose dry-run/apply;
- show job progress and traces.

- [ ] **Step 5: Run workflow tests**

Run:

```bash
TMPDIR=$PWD/output/pytest-tmp uv run pytest tests/test_catalog_rebuild_workflow.py tests/test_web_catalog_routes.py -q --basetemp=$PWD/output/pytest-catalog-rebuild
```

Expected: pass.

---

## Task 13: Documentation Update

**Files:**

- Modify: `docs/superpowers/specs/2026-04-28-pur-catalog-source-of-truth-design.md`

- [ ] **Step 1: Add prompt management section**

Document:

- prompt families;
- prompt versions;
- draft/active/archive lifecycle;
- prompt hash;
- prompt render preview;
- relation to model profile and route.

- [ ] **Step 2: Add full LLM trace section**

Document:

- what request data is stored;
- what response data is stored;
- secret redaction;
- trace links from catalog candidates, extraction runs, decisions, and jobs.

- [ ] **Step 3: Add catalog-first rollout**

Document order:

1. manual catalog editor;
2. raw catalog ingest visibility;
3. catalog extraction trace;
4. prompt management;
5. catalog model/prompt evaluation;
6. edit/review AI candidates before promotion;
7. apply selected catalog extraction results;
8. rebuild snapshot;
9. then lead LLM arbiter.

- [ ] **Step 4: Verify docs mention fuzzy root cause**

Document the `стоимость` false positive class:

- negative phrase leakage into positive fuzzy index;
- generic commercial terms;
- marketplace seller listing.

---

## Task 14: Verification

- [ ] **Step 1: Run focused test groups**

```bash
TMPDIR=$PWD/output/pytest-tmp uv run pytest \
  tests/test_catalog_editor_service.py \
  tests/test_prompt_service.py \
  tests/test_ai_trace_service.py \
  tests/test_llm_catalog_extractor.py \
  tests/test_catalog_runtime_handlers.py \
  tests/test_web_prompt_routes.py \
  tests/test_web_operations_routes.py \
  tests/test_classifier_snapshot_service.py \
  tests/test_fuzzy_catalog_classifier.py \
  -q \
  --basetemp=$PWD/output/pytest-catalog-trace-suite
```

- [ ] **Step 2: Run static checks**

```bash
uv run ruff check .
uv run ruff format --check .
node --check src/pur_leads/web/static/app.js
git diff --check
```

- [ ] **Step 3: Run full test suite**

```bash
TMPDIR=$PWD/output/pytest-tmp uv run pytest -q --basetemp=$PWD/output/pytest-full
```

- [ ] **Step 4: Manual server smoke after deploy**

On the remote server:

```bash
docker compose ps
docker compose logs --tail=100 worker
```

In UI:

- open Catalog;
- create a manual catalog item with term/evidence;
- rebuild classifier snapshot explicitly;
- run one dry-run catalog extraction;
- open AI trace;
- verify full request/response visible;
- verify prompt version visible;
- verify context fill visible;
- verify no secret token is visible.

---

## First Production Run

After implementation:

1. Create a backup.
2. Manually create a small baseline catalog: 2-3 items, terms, lead phrases, negative phrases, evidence.
3. Rebuild classifier snapshot explicitly.
4. Activate `catalog-extraction-v2`.
5. Run dry-run on a small fixed sample from PUR documents.
6. Compare `GLM-5.1`, `GLM-5`, `GLM-4.7`, `GLM-4.6`, `GLM-4-Plus`.
7. Inspect traces manually.
8. Edit AI candidates and record corrections.
9. Pick the best prompt/model profile for catalog extraction.
10. Run apply mode for PUR catalog sources.
11. Rebuild classifier snapshot.
12. Reprocess recent lead source messages.
13. Check that the Sanita toilet message is `not_lead`.

---

## Acceptance Criteria

- Admin can manually create, edit, archive, and attach evidence to catalog items, terms, offers, lead phrases, and negative phrases without running AI.
- Manual catalog edits can explicitly rebuild the classifier snapshot.
- For every catalog LLM extraction, an admin can open the exact LLM request and response in the web UI.
- Prompt versions are manageable in UI and every extraction references the prompt version/hash used.
- Catalog extraction can be run in dry-run mode for prompt/model comparison.
- AI extraction output remains editable before it changes the canonical catalog.
- Manual corrections to AI output are stored as feedback for prompt/model evaluation.
- Context-window usage is visible per LLM call.
- Negative phrases do not become positive fuzzy terms.
- Generic words like `стоимость` cannot create `maybe` by themselves.
- Current catalog rebuild can be audited from source chunk to LLM trace to extracted fact to catalog candidate to classifier snapshot entry.
