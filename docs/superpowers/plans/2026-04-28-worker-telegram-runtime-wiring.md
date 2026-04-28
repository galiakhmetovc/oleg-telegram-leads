# Worker Telegram Runtime Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make CLI workers use the canonical Telegram job handlers and add a bounded continuous polling command for deployment/runtime use.

**Architecture:** Keep one worker runtime path. The CLI builds one combined registry from catalog, lead, and Telegram handlers. Until a real Telethon client is configured, Telegram jobs fail through the handler path with a visible configuration error instead of being treated as unsupported. `worker run` loops over `WorkerRuntime.run_once` with a configurable sleep and optional max-iterations for tests.

**Tech Stack:** Python 3.12, asyncio, existing scheduler/runtime, pytest.

---

### Task 1: Telegram Handler Wiring

**Files:**
- Modify: `src/pur_leads/cli.py`
- Test: `tests/test_cli.py`

- [x] Write a failing test proving `worker once` routes `check_source_access` through a Telegram handler and fails with `telegram client is not configured`.
- [x] Run `uv run --extra dev pytest tests/test_cli.py::test_cli_worker_once_routes_telegram_jobs_through_canonical_registry -q` and verify expected failure.
- [x] Add an unconfigured Telegram client port implementation and use `build_telegram_handler_registry` in the CLI handler builder.
- [x] Run `uv run --extra dev pytest tests/test_cli.py::test_cli_worker_once_routes_telegram_jobs_through_canonical_registry -q` and verify it passes.
- [x] Commit as `feat: wire telegram handlers into cli worker`.

### Task 2: Continuous Worker Command

**Files:**
- Modify: `src/pur_leads/cli.py`
- Test: `tests/test_cli.py`

- [x] Write a failing test for `pur-leads worker run --poll-interval-seconds 0 --max-iterations 2`.
- [x] Run `uv run --extra dev pytest tests/test_cli.py::test_cli_worker_run_supports_bounded_polling_loop -q` and verify expected failure.
- [x] Implement `worker run` around the same `WorkerRuntime` and registry used by `worker once`.
- [x] Run `uv run --extra dev pytest tests/test_cli.py -q` and verify it passes.
- [x] Commit as `feat: add worker run loop`.

### Task 3: Full Verification And Deploy

- [x] Run `uv run --extra dev ruff check`.
- [x] Run `uv run --extra dev ruff format --check`.
- [x] Run `uv run --extra dev mypy src`.
- [x] Run `uv run --extra dev pytest -q`.
- [x] Run `docker compose config >/tmp/oleg-telegram-leads-compose.out && wc -l /tmp/oleg-telegram-leads-compose.out`.
- [ ] Push `main`.
- [ ] SSH to `teamd-ams1`, pull fast-forward, rebuild web, run migrations if needed, restart `web`, and verify `/health`.
