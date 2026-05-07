# PUR Leads v2

Fresh implementation branch for the next version of PUR Leads.

The previous codebase is historical reference only. Active development happens
in this repository layout:

- `backend/` - FastAPI service, SQLAlchemy/Alembic, PostgreSQL only.
- `frontend/` - React + Vite + TypeScript operator UI.
- `docker-compose.yml` - local container stack for PostgreSQL, Redis, backend,
  worker, and frontend.
- `docs/` - architecture and durable decisions.
- `state/` - current work and backlog.
- `artifacts/` - ignored local exports and evidence, including production lead examples.

## Local Development

```bash
docker compose up --build
```

Services:

- backend: `http://localhost:8000`
- frontend: `http://localhost:5173`
- postgres: `127.0.0.1:55433`
- redis: `127.0.0.1:6379`
- caddy dev access: `https://secclaw.qlbc.ru:19443`

## Внешний Dev-Доступ

Caddy на хосте прокидывает dev-интерфейс наружу через:

`https://secclaw.qlbc.ru:19443/`

Маршрутизация:

- `/` -> Vite dev server на `127.0.0.1:5173`
- `/api/*` -> FastAPI на `127.0.0.1:8000`
- SSE endpoint `/api/v1/enrichments/{job_id}/events` проходит через тот же
  Caddy route; в reverse proxy включен streaming-friendly `flush_interval -1`.

Caddy-конфигурация находится вне репозитория:

- `/etc/caddy/sites/53-pur-leads-v2-dev.conf`
- импорт подключен из `/etc/caddy/Caddyfile`

The first workflow uses the backend API to create text enrichment jobs, a Celery
worker to run the NLP pipeline, Redis as the broker, PostgreSQL for persisted
job state, and SSE for progress updates.

The operator UI also includes a Settings Center. It shows editable NLP/domain
settings from PostgreSQL config revisions and read-only runtime settings from
the backend environment. Draft NLP settings can be previewed on text before
saving. Rule editing separates exact phrases from lemmatized phrases; new
lemmatized phrases are built from operator-entered text by the backend and show
both the original input and generated lemmas. A Help tab in the UI explains the
matching modes. `backend/config/nlp` is only the bootstrap default when the
database has no active NLP config revision yet.

The enrichment result now includes `lead_assessment`: an explainable PUR lead
verdict with score, temperature, solution areas, customer segments, positive
reasons, and noise signals. Scoring thresholds, weights, and taxonomy mappings
are edited through the same PostgreSQL-backed Settings Center.

## Batch Enrichment

Local exports can be enriched without creating one API/Celery job per message:

```bash
cd backend
uv run python -m app.cli.batch_enrich \
  --input ../artifacts/designer-channel/messages.jsonl \
  --output ../artifacts/designer-channel/full-enrichment.jsonl \
  --summary ../artifacts/designer-channel/full-enrichment.summary.json \
  --progress-interval 1000
```

The batch output is JSONL with `message_id`, `text`, and full
`TextEnrichmentResult` under `result`. `artifacts/` is ignored by git.

Checks:

```bash
cd backend && uv run pytest -q
cd backend && uv run pytest --runslow tests/test_enrichment_pipeline.py::test_enriches_text_with_configured_domain_signal -q
cd frontend && npm test && npm run build
docker compose config
```
