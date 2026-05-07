# PUR Leads v2

Fresh implementation branch for the next version of PUR Leads.

The previous codebase is historical reference only. Active development happens
in this repository layout:

- `backend/` - FastAPI service, SQLAlchemy/Alembic, PostgreSQL only.
- `frontend/` - React + Vite + TypeScript operator UI.
- `docker-compose.yml` - local container stack for PostgreSQL, backend, and frontend.
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

Checks:

```bash
cd backend && uv run --extra dev pytest -q
cd frontend && npm test && npm run build
docker compose config
```
