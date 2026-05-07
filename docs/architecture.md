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
- React + Vite + TypeScript owns the operator UI.
- Docker Compose owns the local dev stack and service wiring.

## Backend

The backend package lives in `backend/app`.

- `app/main.py` creates the FastAPI application.
- `app/api/health.py` exposes the first health endpoint.
- `app/core/config.py` reads environment-backed settings.
- `app/db/session.py` centralizes SQLAlchemy async engine/session construction.
- `backend/alembic/` is reserved for schema migrations.

## Frontend

The frontend package lives in `frontend/src`.

- `App.tsx` is the first operator workspace shell.
- `main.tsx` mounts React.
- `styles.css` holds application-level layout styles.

## Legacy Reference

The v1 codebase remains available through git history and the old worktree at:

`/home/admin/AI-AGENT/data/projects/oleg-telegram-leads`

Production-confirmed lead examples are kept as ignored local artifacts under:

`artifacts/prod-lead-messages/2026-05-07`
