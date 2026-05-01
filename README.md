# PUR Leads

Greenfield implementation for PUR catalog source-of-truth, Telegram lead detection, and lightweight CRM.

Start with `docs/README.md` for the current documentation map and implementation
status. The full target design remains in
`docs/superpowers/specs/2026-04-28-pur-catalog-source-of-truth-design.md`.

Operational notes:

- Documentation map and implementation audit: `docs/README.md`.
- Artifact visibility and production deployment runbook: `docs/operations/artifacts-and-production.md`.
- Current production host: `teamd-ams1` / `31.130.128.89`.
- Production web URL: `http://31.130.128.89:8000`.

## Development

```bash
uv sync --extra dev
npm install
npm run build:assets
uv run --extra dev pytest -q
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
uv run --extra dev mypy src
```

## Web Assets

The web UI uses Material Web (`@material/web`) as the component system for auth
and onboarding screens. The app serves a local ESM bundle from
`/static/vendor/material-web.js`; it is built from
`src/pur_leads/web/assets/material-web.js`.

```bash
npm install
npm run build:assets
```

Do not mix Bootstrap into this UI slice. `app.css` should stay responsible for
layout, spacing, and product-specific composition around Material Web
components.

## CLI

```bash
uv run --extra dev pur-leads db upgrade
uv run --extra dev pur-leads settings list
uv run --extra dev pur-leads settings set telegram_worker_count 1
uv run --extra dev pur-leads worker once
uv run --extra dev pur-leads web
```

## Docker

```bash
docker compose run --rm web db upgrade
docker compose up web
docker compose run --rm worker
```

Production runs through Docker Compose on `teamd-ams1`. Do not treat a local
`uv run pur-leads web` process as production. The target production database is
Postgres via `PUR_DATABASE_URL`; `PUR_DATABASE_PATH` is a temporary SQLite
fallback for local development/tests and generated artifact previews. Before any
production restart, take a database backup and check whether the worker is
intentionally stopped.
See `docs/operations/artifacts-and-production.md`.

For fast iteration on a running server, use the dev override. It mounts
`src/`, `migrations/`, and `alembic.ini` into the existing image, so normal
Python/CSS/JS changes do not require a Docker rebuild:

```bash
scripts/deploy-dev.sh
```

Rebuild the image when dependencies, the Dockerfile, or the Material Web vendor
bundle change.

## Artifacts UI

Authenticated admins can inspect generated pipeline artifacts at `/artifacts`.
The screen lists raw Telegram exports, stage metadata outputs, discovered files
inside artifact directories, and previews JSON/JSONL, Parquet, SQLite, and text
artifacts without requiring SSH. The API routes are:

```text
GET /api/artifacts
GET /api/artifacts/{artifact_id}
```

The inventory is derived from `telegram_raw_export_runs`, `metadata_json` path
fields, and bounded filesystem discovery under registered artifact directories.
See `docs/operations/artifacts-and-production.md` for limits and operational
behavior.

## Bootstrap Admin

On first start the app creates the built-in `admin` account and writes its temporary password to `./data/bootstrap-admin-password.txt` by default. After login the admin must set a new password; the temporary password file is then removed and is not regenerated on later restarts.

After the password is changed, incomplete installations open `/onboarding`. The onboarding page validates and stores the Telegram bot token, discovers the notification group through bot updates, configures Z.AI as the LLM provider, supports interactive Telethon userbot login, and keeps raw secrets in local file-backed `secret_refs` instead of returning them through the UI.
