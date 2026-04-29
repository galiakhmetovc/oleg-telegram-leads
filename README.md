# PUR Leads

Greenfield implementation for PUR catalog source-of-truth, Telegram lead detection, and lightweight CRM.

The current source of truth is `docs/superpowers/specs/2026-04-28-pur-catalog-source-of-truth-design.md`.

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

For fast iteration on a running server, use the dev override. It mounts
`src/`, `migrations/`, and `alembic.ini` into the existing image, so normal
Python/CSS/JS changes do not require a Docker rebuild:

```bash
scripts/deploy-dev.sh
```

Rebuild the image when dependencies, the Dockerfile, or the Material Web vendor
bundle change.

## Bootstrap Admin

On first start the app creates the built-in `admin` account and writes its temporary password to `./data/bootstrap-admin-password.txt` by default. After login the admin must set a new password; the temporary password file is then removed and is not regenerated on later restarts.

After the password is changed, incomplete installations open `/onboarding`. The onboarding page validates and stores the Telegram bot token, discovers the notification group through bot updates, configures Z.AI as the LLM provider, supports interactive Telethon userbot login, and keeps raw secrets in local file-backed `secret_refs` instead of returning them through the UI.
