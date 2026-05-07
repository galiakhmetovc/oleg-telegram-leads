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

Checks:

```bash
cd backend && uv run --extra dev pytest -q
cd frontend && npm test && npm run build
docker compose config
```
