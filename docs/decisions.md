# Decisions

## 2026-05-07: Fresh v2 Codebase

PUR Leads v1 is historical reference only. V2 starts from a clean scaffold rather
than extending the old source tree.

## 2026-05-07: Core Stack

Use PostgreSQL, FastAPI, React, and Docker Compose as the base stack.

Rationale:

- PostgreSQL is the production database from day one.
- FastAPI gives a small, typed Python API surface.
- React + Vite + TypeScript gives a focused frontend toolchain.
- Docker Compose keeps local service wiring explicit and reproducible.

## 2026-05-07: Project Working Rules

Use root `AGENTS.md` as the mandatory working rules file for PUR Leads v2.

Rationale:

- Chat history is not a durable source of truth.
- Future agent sessions need one predictable place for project rules.
- Process rules, architecture rules, verification rules, and Definition of Done
  should be versioned with the project.

## 2026-05-07: Dev Containers Do Not Bake Source

In development mode, Docker images provide runtime tools and dependency layers only.
Backend and frontend source code is mounted from the host through bind volumes.

Rationale:

- The project is currently in active local development.
- Source changes should be visible without rebuilding images.
- Production image design is a separate future decision.

## 2026-05-07: Architecture Principles

Build v2 around Hexagonal Architecture / Ports and Adapters with explicit use
cases, domain boundaries, dependency inversion, repositories as ports, and clear
separation between API schemas, domain objects, DB models, and frontend types.

Apply GRASP, SOLID, DDD tactical patterns where useful, Dependency Injection,
Repository + Unit of Work, and testability by design.

Rationale:

- PUR Leads will contain substantial business behavior around Telegram data,
  lead review, NLP classification, evals, and operator workflows.
- Keeping framework and infrastructure dependencies outside the domain makes the
  system easier to test and change.
- Adult boundaries are cheaper to establish now than retrofit later.

## 2026-05-07: Frontend Product Direction

Build a working operator interface, not a landing page. Use Google Material
Design through MUI for the React UI.

Rationale:

- The product is an operational tool.
- Operators need dense, predictable screens: tables, filters, lists, forms,
  statuses, and review flows.
- Marketing-style hero sections and decorative UI do not serve the workflow.

## 2026-05-07: Verification Policy

All behavior-affecting changes are business logic and must be verified with a
method appropriate to risk. Tests are valuable when they protect real behavior;
do not write tests only for coverage theater.

Rationale:

- Backend, frontend, migrations, imports, classification, UI flow, and Docker
  wiring can all affect user-visible behavior.
- Verification may be unit, integration, API, UI smoke, manual, or another
  reproducible check depending on the change.

## 2026-05-07: Production-Derived Data

Production lead exports may be committed when they are useful for development,
evals, or regressions. Before committing production-derived data, explicitly
inspect what is being added and avoid accidental large dumps, secrets, tokens, or
irrelevant sensitive data.

Use `artifacts/` for local temporary exports and `datasets/` for small
versioned datasets when data should live in git.

Rationale:

- Real lead examples are important for NLP/eval quality.
- Data should be intentionally curated when it becomes part of the repository.

## 2026-05-07: Externalized Domain Configuration

Domain rules, signal definitions, dictionaries, thresholds, weights, enabled NLP
pipeline stages, UI labels for domain types, and provider-specific settings
should not be hardcoded in application code.

Rationale:

- PUR Leads will evolve through NLP experiments and domain feedback.
- Changing signal definitions should not require editing application mechanics.
- Configuration and rule files make behavior reviewable and reproducible.

## 2026-05-07: Enrichment Jobs Use Worker Queue From The Start

Use a separate Celery worker with Redis as the broker for text enrichment jobs.
FastAPI creates jobs, exposes snapshots, and streams progress through SSE.
PostgreSQL stores jobs, progress events, and final results.

Rationale:

- NLP enrichment is CPU-heavy enough to keep out of the API request path.
- The frontend needs detailed backend progress, including current stage and
  percentage.
- Persisted job state makes snapshots and page recovery possible.
- Starting with the worker boundary avoids replacing the execution model after
  the UI contract is built.

## 2026-05-07: Host Caddy Exposes Dev UI

Expose the v2 dev web interface through the existing host Caddy service at
`https://secclaw.qlbc.ru:19443/`.

Routing:

- `/` proxies to the Vite dev server on `127.0.0.1:5173`.
- `/api/*` proxies to FastAPI on `127.0.0.1:8000`.
- SSE uses the same `/api/*` route and requires streaming-friendly proxying.

Rationale:

- The user can review the interface without opening a browser from the agent
  environment.
- Backend and frontend remain in Docker Compose dev mode with localhost-bound
  ports.
- Caddy is an external ingress concern and stays outside the repository.
- The host firewall must explicitly allow `19443/tcp`; otherwise local checks
  from the host can pass while external browsers time out.

## 2026-05-07: Settings Center Stores NLP Settings In PostgreSQL

Expose all current NLP/domain settings in the operator UI and allow editing them
through FastAPI. Persist editable NLP/domain settings as PostgreSQL revisions in
`nlp_config_revisions`. Keep `backend/config/nlp` YAML files as bootstrap
defaults only, used when the database has no active revision yet. Keep runtime/env
settings read-only.

Rationale:

- Settings are product data and must survive through the operational database,
  not through mutable files.
- Revision rows make future diff, audit, rollback, and publication workflows
  natural.
- YAML remains useful as versioned bootstrap defaults and reviewable seed data,
  but it is not the active editable store.
- Runtime settings affect process wiring and secrets; showing them read-only is
  safer until auth, audit, and restart procedures exist.

## 2026-05-07: PUR Lead Assessment Is Deterministic And Explainable

Detect potential PUR clients with a deterministic lead assessment layer instead
of an LLM. The layer consumes extracted domain signals and facts, applies
PostgreSQL-backed scoring settings, and returns `lead_assessment` with a score,
temperature, solution areas, customer segments, reasons, and noise signals.

Rationale:

- The current task needs explainable classification that can be edited from the
  Settings Center and verified against known lead examples.
- Business meaning belongs in PostgreSQL config revisions: thresholds, weights,
  taxonomy mappings, and noise definitions are product settings, not code.
- A deterministic layer gives a stable baseline for future evals; ML/LLM
  classifiers can be added later once we have enough labeled examples and known
  failure modes.
- Noise signals must be first-class so equipment-only/DIY/sale posts can be
  explained as non-leads rather than silently missed.

## 2026-05-07: Smart-Home Market Terms Live In Alias Catalogs

Keep domain signals as semantic categories and move market spellings into
separate PostgreSQL-backed alias catalogs: `vendors`, `protocols`, `devices`,
and `software`. Each alias row stores canonical name, alias type, written
variants, and links to signal/fact types. Bootstrap YAML files seed a curated
first pass for common РФ/СНГ smart-home platforms, protocols, devices, software,
and security/leak/power/climate brands.

Rationale:

- Vendor and device spellings change faster than the semantic taxonomy; mixing
  them directly into signal rules makes settings hard to audit and edit.
- Operators need to see and edit human spellings such as `Aqara/Акара`,
  `Zigbee/Зигби`, `Home Assistant/Хоум Ассистант`, and `Neptun/Нептун/Нептуп`
  without changing code.
- Exact alias matching is deterministic and cheap, while linked signal/fact
  types keep lead scoring explainable.
- The curated bootstrap pass is intentionally broad but not final; production
  review and eval data should continue extending these catalogs.

## 2026-05-08: Rule Groups Are Editable Configuration Metadata

Domain signal and fact rules may carry a `group` display folder. The group is
stored in PostgreSQL-backed NLP config revisions and in bootstrap YAML defaults,
then rendered by the Settings Center as grouped accordions.

Rationale:

- The PUR domain signal list is already too large for one flat editor.
- Grouping must be part of editable configuration, not hardcoded frontend logic.
- `group` is navigation metadata only: it does not change extraction, confidence,
  scoring, review lanes, or analytics semantics.
- Russian group labels are acceptable because they are operator-facing folder
  names, while stable scoring/filter keys remain English `type` values.

## 2026-05-07: Yargy Parsers Share Morphology Resources

Compile Yargy parsers once per `RussianTextEnricher` instance and share one
Yargy `MorphTokenizer` across signal, fact, and alias parsers.

Rationale:

- Creating a parser per configured rule with its own default `MorphTokenizer`
  also creates many `pymorphy2` analyzers.
- With broad PUR settings this made ordinary tests and batch runs allocate
  multiple GB of RSS and could kill unrelated terminal/tmux sessions under
  memory pressure.
- Shared tokenizer state keeps `normalized` semantic matching available while
  making default backend tests safe to run by default.

## 2026-05-07: Rule Matching Has Two Operator Modes

Expose only two rule matching modes to operators and API clients: exact phrases
and lemmatized phrases. Exact phrases are literal lowercased text matches with
word-like boundaries; lemmatized phrases are stored as Yargy `normalized` tokens.
Do not use `caseless` as a new persisted/operator-facing rule predicate.

Rationale:

- The user-facing distinction must stay understandable: exact spelling versus
  semantic Russian word forms.
- Technical tokens such as `Wi-Fi`, `220v`, `Z-Wave`, abbreviations, and product
  names are exact spellings and should not depend on Yargy tokenization.
- Old `caseless` documents are not supported by v2. They should be replaced by
  a fresh PostgreSQL config revision or reseeded from current bootstrap YAML
  instead of hidden compatibility code.

## 2026-05-07: Analytics Starts In PostgreSQL

Store imported batch analytics in PostgreSQL first: runs, candidate lead
messages, and precomputed aggregates. Do not introduce ClickHouse until the
product needs a raw analytical warehouse over all messages, all spans, many
historical runs, or ad-hoc OLAP workloads that PostgreSQL cannot serve well.

Rationale:

- The immediate UI workflow reviews roughly tens of thousands of candidates per
  run, filters them, and compares aggregate counts.
- PostgreSQL is already the operational source of truth and keeps migrations,
  backup, deployment, and local dev simpler while the product workflow is still
  changing.
- Precomputed aggregates avoid scanning the 3+ GB full enrichment dump on every
  page load.
- A later ClickHouse slice should receive stable export/import contracts from
  this boundary instead of becoming another active source of truth too early.

## 2026-05-08: Analytics Review Lanes Are Configured

Add review lanes as a configurable product layer over imported analytics
candidates. A lane is not a hardcoded Python heuristic: it lives in
`lead_scoring.review_lanes` inside the PostgreSQL-backed NLP config revision and
matches already extracted signal, fact, reason, solution-area, customer-segment,
intent, and noise arrays.

Rationale:

- The current candidate set is intentionally broad, so operators need review
  queues such as direct PUR leads, project context, domain interest, generic
  demand, and noise.
- Threshold-only filtering loses confirmed positives and does not explain why a
  candidate should be reviewed first.
- Keeping lane definitions in config preserves the project rule that domain
  logic remains externalized and editable.
- Persisting the assigned lane during analytics import makes the UI filters and
  aggregates cheap in PostgreSQL.
