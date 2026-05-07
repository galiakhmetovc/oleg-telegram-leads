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

Runtime NLP behavior is configured under `backend/config/nlp`.

- `pipeline.yaml` controls enabled stages.
- `signals.yaml` defines domain signals shown to the operator.
- `facts.yaml` defines structured fact extraction.

Yargy rules are externalized as YAML. Two rule forms are currently supported:

- `phrases`: exact case-insensitive token phrases for simple stable wording.
- `patterns`: token predicates for Russian morphology, currently `normalized`
  and `caseless`.

Example:

```yaml
patterns:
  - tokens:
      - normalized: "умный"
      - normalized: "дом"
```

Use `patterns` for Russian domain language that appears in different cases or
forms, for example `умный дом`, `умного дома`, and `умному дому`.

## Settings Center

The first settings UI slice exposes the active dev NLP configuration through
FastAPI:

- `GET /api/v1/settings` returns editable NLP/domain settings and read-only
  runtime settings.
- `PUT /api/v1/settings/nlp` validates and saves NLP settings back to
  `backend/config/nlp/*.yaml`.
- `POST /api/v1/settings/nlp/preview` runs a draft configuration against a text
  without saving it.

In dev mode, YAML files are the active source of truth for NLP settings. Celery
loads the config per job, so saved YAML changes apply to the next enrichment job.
Runtime settings such as database URL, Redis URL, CORS, and config paths are
visible but read-only because they come from environment configuration and may
require process/container restart.

The API contract is intentionally storage-neutral: later PostgreSQL-backed
config revisions can replace YAML persistence without changing the frontend
shape.

## Frontend

The frontend package lives in `frontend/src`.

- `App.tsx` is the first operator workspace shell.
- `main.tsx` mounts React.
- `styles.css` holds application-level layout styles.

The first operator screen provides:

- text input for arbitrary text;
- live backend progress with stage names and percentages;
- annotated source text after completion;
- structured result tabs for overview, entities, facts, domain signals, tokens,
  syntax, and pipeline trace.

## Legacy Reference

The v1 codebase remains available through git history and the old worktree at:

`/home/admin/AI-AGENT/data/projects/oleg-telegram-leads`

Production-confirmed lead examples are kept as ignored local artifacts under:

`artifacts/prod-lead-messages/2026-05-07`
