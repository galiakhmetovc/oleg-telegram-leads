# PUR Leads

Greenfield implementation for PUR catalog source-of-truth, Telegram lead detection, and lightweight CRM.

The current source of truth is `docs/superpowers/specs/2026-04-28-pur-catalog-source-of-truth-design.md`.

## Development

```bash
uv sync --extra dev
uv run --extra dev pytest -q
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
uv run --extra dev mypy src
```

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

## Bootstrap Admin

On first start the app creates the built-in `admin` account and writes its temporary password to `./data/bootstrap-admin-password.txt` by default. After login the admin must set a new password; the temporary password file is then removed and is not regenerated on later restarts.
