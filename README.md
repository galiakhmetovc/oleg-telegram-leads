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
