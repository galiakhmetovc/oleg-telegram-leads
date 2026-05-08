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
- файл site-конфига должен быть читаем service user Caddy, например
  `root:caddy 640`
- хостовый firewall должен пропускать внешний порт:
  `sudo ufw allow 19443/tcp comment 'PUR Leads v2 dev UI'`

The first workflow uses the backend API to create text enrichment jobs, a Celery
worker to run the NLP pipeline, Redis as the broker, PostgreSQL for persisted
job state, and SSE for progress updates.

The operator UI also includes a Settings Center. It shows editable NLP/domain
settings from PostgreSQL config revisions and read-only runtime settings from
the backend environment. Draft NLP settings can be previewed on text before
saving. Rule editing separates exact phrases from lemmatized phrases; new
lemmatized phrases are built from operator-entered text by the backend and show
both the original input and generated lemmas. Exact phrases use literal
lowercased matching for technical spellings such as `Wi-Fi`, `220v`, and
abbreviations; lemmatized phrases use normalized Yargy tokens. A Help tab in the
UI explains the matching modes. `backend/config/nlp` is only the bootstrap
default when the database has no active NLP config revision yet.

The enrichment result now includes `lead_assessment`: an explainable PUR lead
verdict with score, temperature, solution areas, customer segments, review lane,
positive reasons, and noise signals. The Overview tab shows dictionary entities,
facts, domain signals, the exact score arithmetic, and category/lane matches in
operator-facing labels. Evidence rows and calculation rows link to separate
settings detail pages through hash deeplinks like
`#/settings/aliases/devices/electric_curtain`, while keeping the current input
text in the SPA context. Scoring thresholds, weights, review lanes, and taxonomy
mappings are edited through the same PostgreSQL-backed Settings Center.

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

## Batch Analytics

Lead candidates from a completed batch run can be imported into PostgreSQL for
the web analytics tab. The import reads the compact `lead-candidates.jsonl`
file and the batch summary, not the full enrichment dump:

```bash
cd backend
PUR_DATABASE_URL='postgresql+psycopg://pur_leads:pur_leads_dev_password@127.0.0.1:55433/pur_leads_v2' \
uv run python -m app.cli.import_analytics \
  --summary ../artifacts/designer-channel/runs/2026-05-07-full-8workers/full-enrichment.summary.json \
  --lead-candidates ../artifacts/designer-channel/runs/2026-05-07-full-8workers/lead-candidates.jsonl \
  --name designer-channel-2026-05-07-full-8workers
```

The UI tab `Аналитика` shows imported runs, high-level KPIs, score buckets, top
signals/reasons/segments, review lanes, and a candidate table filtered by score,
temperature, signal, reason, solution area, customer segment, review lane, and
text. Review lanes are configured in `lead_scoring.review_lanes` and stored in
PostgreSQL NLP config revisions; YAML is only the bootstrap default.

Checks:

```bash
cd backend && uv run pytest -q
cd backend && uv run pytest --runslow tests/test_enrichment_pipeline.py::test_enriches_text_with_configured_domain_signal -q
cd frontend && npm test && npm run build
docker compose config
```
