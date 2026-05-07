# Architecture

PUR Leads v2 starts as a clean containerized web application.

## Dev Mode

Everything currently runs in development mode.

- Docker images provide runtime tools and dependency layers only.
- Application source is mounted from the host through bind volumes.
- Backend Python dependencies are installed into the image from `backend/pyproject.toml`
  and `backend/uv.lock`; backend source is not copied into the image.
- Frontend dependencies are installed into the image from `frontend/package-lock.json`;
  frontend source is not copied into the image.
- Frontend `node_modules` is exposed through the `frontend-node-modules` Docker volume.
- There is no production image, nginx packaging, or baked application source yet.

## Components

- PostgreSQL is the only operational database.
- FastAPI owns the backend HTTP API and database access.
- Celery workers execute background NLP enrichment jobs.
- Redis is the local Celery broker.
- React + Vite + TypeScript owns the operator UI.
- Docker Compose owns the local dev stack and service wiring.
- Host Caddy exposes the dev UI over HTTPS for operator review.

## Caddy Dev Access

External dev access is provided by the host-level Caddy service, not by the
Docker Compose stack.

- Public URL: `https://secclaw.qlbc.ru:19443/`
- Site file: `/etc/caddy/sites/53-pur-leads-v2-dev.conf`
- Main Caddy import: `/etc/caddy/Caddyfile`
- Frontend route: `/` -> `127.0.0.1:5173`
- Backend route: `/api/*` -> `127.0.0.1:8000`
- SSE route: `/api/v1/enrichments/{job_id}/events` is covered by `/api/*`
  and requires proxy streaming to stay enabled.

The Docker services stay bound to localhost in dev mode. Caddy is the only
external ingress for this slice.

## Backend

The backend package lives in `backend/app`.

- `app/main.py` creates the FastAPI application.
- `app/api/health.py` exposes the first health endpoint.
- `app/core/config.py` reads environment-backed settings.
- `app/db/session.py` centralizes SQLAlchemy async engine/session construction.
- `backend/alembic/` is reserved for schema migrations.

The first product slice uses a persisted enrichment job model:

- FastAPI creates enrichment jobs, serves job snapshots, and streams progress
  through Server-Sent Events.
- Celery workers execute the configured NLP pipeline outside the API process.
- PostgreSQL stores jobs, progress events, and final enrichment results.
- Redis is only the Celery broker; durable business state stays in PostgreSQL.
- NLP stages, domain signals, and rule sources are loaded from configuration
  instead of being hardcoded into application code.

## NLP Configuration

Editable NLP behavior is stored in PostgreSQL table `nlp_config_revisions`.
`backend/config/nlp` contains only bootstrap defaults used to seed revision 1
when the database is empty.

- `pipeline` controls enabled stages.
- `signals` defines domain signals shown to the operator.
- `facts` defines structured fact extraction.
- `vendors`, `protocols`, `devices`, and `software` define alias catalogs for
  exact written variants of market terms.
- `lead_scoring` defines PUR lead thresholds, signal/fact weights, solution area
  mappings, customer segment mappings, intent signals, and noise signals.

Yargy rules are externalized as configuration data, but the operator-facing
model is intentionally simpler than Yargy internals:

- Exact phrases: stable token sequences for abbreviations, brands, protocols,
  technical notation, and wording where the exact written form matters.
- Lemmatized phrases: Russian domain phrases entered as normal text and stored
  with both the operator's source text and backend-built lemmas.

Use lemmatized phrases for Russian domain language that appears in different
cases or forms. For example, operator input `умный дом` is stored as lemmas
`умный дом` and can match `умного дома` and `умному дому`. Operator input
`нужна консультация` is stored as lemmas `нужный консультация`.

The persisted config still uses `phrases` and `patterns` as the storage shape
because that is what the rule engine consumes. The web UI does not expose Yargy
predicate names as the product vocabulary.

Exact phrases are matched as lowercased literal text with word-like boundaries,
not through Yargy morphology. This keeps technical variants such as `Wi-Fi`,
`220v`, `Z-Wave`, product names, and abbreviations in the exact matching mode.
Lemmatized phrases use Yargy `normalized` tokens. Documents that still contain
`caseless` are invalid for v2 and must be replaced by a new PostgreSQL config
revision or reseeded from current bootstrap YAML.

Alias catalogs are separate from domain signals. Domain signals remain semantic
categories such as `smart_home_platform`, `protocol_gateway`, `leak_protection`,
`lighting_automation`, `climate_automation`, `access_control`, `intercom`,
`video_surveillance`, and `power_backup`. Alias catalogs store written variants:
canonical name, alias type (`vendor`, `protocol`, `device`, `software`, or
`model`), Latin/Cyrillic/transliterated/mistyped spellings, and links to the
semantic signal and fact types emitted when the alias matches. Exact alias
matching lowercases the input text before matching and returns the original
span text in enrichment output.

## Lead Assessment

The `lead_scoring` stage runs after Yargy fact and signal extraction. It does not
contain hardcoded PUR business rules: the code sums configured signal/fact
weights, applies configured thresholds, maps matched signal/fact types to
solution areas and customer segments, and returns explanatory reasons.

`lead_assessment` is part of every new enrichment result when the stage is
enabled:

- `is_lead`: whether the score reaches the configured lead threshold.
- `score`: non-negative deterministic score.
- `temperature`: `none`, `cold`, `warm`, or `hot`.
- `solution_areas` and `customer_segments`: configured taxonomy matches.
- `intent_signals` and `noise_signals`: configured positive/noise categories.
- `reasons`: score contributions with source, key, weight, and matched texts.

Older persisted results without `lead_assessment` remain readable and return the
field as `null`.

## Settings Center

The settings UI exposes the active NLP configuration through FastAPI:

- `GET /api/v1/settings` returns editable NLP/domain settings and read-only
  runtime settings.
- `PUT /api/v1/settings/nlp` validates NLP settings and creates a new active
  PostgreSQL config revision.
- `POST /api/v1/settings/nlp/preview` runs a draft configuration against a text
  without saving it.
- `POST /api/v1/settings/nlp/semantic-pattern` converts operator-entered rule
  text into a lemmatized phrase and returns both `source_text` and lemma tokens.

PostgreSQL table `nlp_config_revisions` is the active source of truth for
editable NLP settings. `backend/config/nlp/*.yaml` is only a bootstrap default:
if the database has no active revision, the backend seeds revision 1 from YAML.
Celery loads the active database revision per job, so saved UI changes apply to
the next enrichment job. Runtime settings such as database URL, Redis URL, CORS,
and config paths are visible but read-only because they come from environment
configuration and may require process/container restart.

Each save creates a new active revision and deactivates the previous one. This
keeps future history/diff/rollback work aligned with the current API shape.
When a new bootstrap document or pipeline stage is introduced, the repository
can create a new active revision by merging missing bootstrap documents/stages
into the current active configuration without overwriting existing edited
signals or facts.

The frontend Settings Center edits exact phrases and lemmatized phrases as
separate lists with add/edit/delete actions. New lemmatized phrases are created
from natural operator input through the backend semantic-pattern endpoint so the
UI can show both the original text and the generated lemmas. The UI also has a
Help page that explains these matching modes. The Settings Center also exposes
the alias catalogs as editable lists for vended platforms, protocols, devices,
and software.

## Frontend

The frontend package lives in `frontend/src`.

- `App.tsx` is the first operator workspace shell.
- `main.tsx` mounts React.
- `styles.css` holds application-level layout styles.

The first operator screen provides:

- text input for arbitrary text;
- live backend progress with stage names and percentages;
- annotated source text after completion;
- PUR lead verdict with score, temperature, reasons, solution areas, customer
  segments, and noise signals;
- structured result tabs for overview, entities, facts, domain signals, tokens,
  syntax, and pipeline trace.

## Legacy Reference

The v1 codebase remains available through git history and the old worktree at:

`/home/admin/AI-AGENT/data/projects/oleg-telegram-leads`

Production-confirmed lead examples are kept as ignored local artifacts under:

`artifacts/prod-lead-messages/2026-05-07`
