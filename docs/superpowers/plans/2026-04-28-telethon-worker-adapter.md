# Telethon Worker Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the canonical Telegram worker handlers to a real Telethon userbot client when API credentials and an active userbot account are configured.

**Architecture:** Add a Telethon-backed implementation of `TelegramClientPort`, selected by CLI worker setup when `TELEGRAM_API_ID`/`TELEGRAM_API_HASH` and a default active userbot account exist. Keep the unconfigured client as an explicit fallback. Docker gets a long-running `worker` service using the same `worker run` CLI command.

**Tech Stack:** Python 3.12, Telethon 1.43.x, asyncio, existing worker runtime, pytest.

---

### Task 1: Telethon Client Adapter

**Files:**
- Create: `src/pur_leads/integrations/telegram/telethon_client.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Test: `tests/test_telethon_client_adapter.py`

- [x] Write failing adapter tests with a fake low-level Telethon client for source resolution, preview fetch, batch fetch, and authorization failure.
- [x] Run `uv run --extra dev pytest tests/test_telethon_client_adapter.py -q` and verify expected failures.
- [x] Add Telethon dependency pinned to the current 1.x major and implement the adapter without requiring live Telegram in tests.
- [x] Run `uv run --extra dev pytest tests/test_telethon_client_adapter.py -q` and verify it passes.
- [x] Commit as `feat: add telethon telegram client adapter`.

### Task 2: CLI Runtime Selection

**Files:**
- Modify: `src/pur_leads/cli.py`
- Test: `tests/test_cli.py`

- [x] Write failing tests proving CLI uses `TelethonTelegramClient` when env credentials and a default userbot exist, and keeps the explicit fallback otherwise.
- [x] Run `uv run --extra dev pytest tests/test_cli.py -q` and verify expected failures.
- [x] Implement credential loading from `PUR_TELEGRAM_API_ID`/`PUR_TELEGRAM_API_HASH` and legacy `TELEGRAM_API_ID`/`TELEGRAM_API_HASH`.
- [x] Run `uv run --extra dev pytest tests/test_cli.py -q` and verify it passes.
- [x] Commit as `feat: select telethon client for worker`.

### Task 3: Docker Worker Service

**Files:**
- Modify: `docker-compose.yml`
- Test: compose config verification

- [x] Update the `worker` service to run `worker run`, restart unless stopped, pass Telegram API env vars, and mount sessions.
- [x] Run `docker compose config >/tmp/oleg-telegram-leads-compose.out && wc -l /tmp/oleg-telegram-leads-compose.out`.
- [x] Commit as `chore: run worker service continuously`.

### Task 4: Full Verification And Deploy

- [x] Run `uv run --extra dev ruff check`.
- [x] Run `uv run --extra dev ruff format --check`.
- [x] Run `uv run --extra dev mypy src`.
- [x] Run `uv run --extra dev pytest -q`.
- [x] Run `docker compose config >/tmp/oleg-telegram-leads-compose.out && wc -l /tmp/oleg-telegram-leads-compose.out`.
- [ ] Push `main`.
- [ ] SSH to `teamd-ams1`, pull fast-forward, rebuild web/worker, run migrations if needed, restart `web` and `worker`, then verify `/health` and `docker compose ps worker`.
