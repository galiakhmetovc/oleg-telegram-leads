# Artifacts UI And Production Deployment

This document describes the artifact visibility layer and the current production deployment procedure.

For the full documentation map and implementation audit, start with
`docs/README.md`.

## Artifact Visibility

The web UI exposes a protected `Artifacts` section at `/artifacts`.

Purpose:

- show every generated pipeline file that can explain what happened during ingest, parsing, indexing, candidate discovery, and LLM arbitration;
- make raw files and derived artifacts inspectable from the product UI instead of requiring SSH;
- preserve auditability for prompts, model responses, Parquet outputs, SQLite search indexes, Chroma files, and raw Telegram exports.

Access:

- page: `GET /artifacts`;
- API list: `GET /api/artifacts`;
- API detail: `GET /api/artifacts/{artifact_id}`;
- all routes require the existing admin session;
- unauthenticated API access returns `401`;
- unauthenticated page access redirects to `/login`.

## Inventory Sources

The inventory is generated from `telegram_raw_export_runs`.

Explicit raw export paths:

- `output_dir`;
- `result_json_path`;
- `messages_jsonl_path`;
- `attachments_jsonl_path`;
- `messages_parquet_path`;
- `attachments_parquet_path`;
- `manifest_path`.

Metadata paths:

- the service recursively scans `metadata_json`;
- a metadata value is treated as a path when its key ends with `_path`, `_paths`, or `.path`;
- each top-level metadata key becomes the artifact stage, for example `eda`, `text_normalization`, `fts_index`, `chroma_index`, `lead_candidate_discovery`, `lead_candidate_llm_arbitration`.

Filesystem discovery:

- any existing directory artifact is scanned for files;
- discovered files are added with `metadata_json.source = "filesystem_discovery"`;
- registered paths are deduplicated, so explicitly recorded files are not shown twice;
- this catches Chroma internals such as `chroma.sqlite3`, HNSW `*.bin` files, and `index_metadata.pickle`.

Source badges in the UI:

- `raw export run` means the path came from a first-class column in `telegram_raw_export_runs`;
- `metadata запуска` means the path came from `metadata_json`;
- `найдено на диске` means the file was discovered inside a registered artifact directory.

## Preview Behavior

The detail panel opens a safe preview. It must not load huge files fully unless they are already under the configured preview cap.

Preview limits:

- list API default limit: `500`;
- list API hard cap: `2000`;
- discovery per root: `2000` files;
- discovery global cap per inventory call: `10000` files;
- text preview hard cap: `2_000_000` characters;
- directory preview: first `200` child names;
- JSONL parsed records: first `20` records;
- Parquet preview: first `20` rows and first `30` columns;
- SQLite preview: first `50` tables and first `20` sample rows.

Supported previews:

- `json`: pretty-printed JSON when the visible fragment is complete;
- `jsonl`: raw fragment plus parsed first records in a compact table;
- `txt`, `csv`, `md`, `log`: raw text fragment;
- `directory`: child file names;
- `parquet`: row count, row groups, schema, and sample rows through PyArrow;
- `sqlite`, `sqlite3`, `db`: table list, row counts, and sample rows through read-only SQLite URI;
- other binary files are listed with metadata but do not get a content preview.

## UI Shape

The screen follows the `Resources` layout:

- summary metrics at top;
- filters by query, stage, kind, and existence;
- dense artifact list;
- right-side detail inspector;
- source, stage, kind, size, modified time, and metadata visible without leaving the page.

This is intentionally an operational UI, not a marketing page.

## Production Server

Current production server:

- SSH host alias: `teamd-ams1`;
- public IP: `31.130.128.89`;
- repository path: `/var/lib/teamd/workspaces/agents/default/projects/oleg-telegram-leads`;
- web URL: `http://31.130.128.89:8000`;
- Docker Compose service: `web`;
- container name: `oleg-telegram-leads-web-1`;
- production database inside the container: `/app/data/pur-leads.sqlite3`;
- host database path: `data/pur-leads.sqlite3`.

The local/dev server `64.188.58.5` is not production.

## Production Deploy Procedure

Do not deploy by leaving `uv run pur-leads web` in the foreground. Production is Docker Compose on `teamd-ams1`.

Recommended procedure:

1. Verify the target:

   ```bash
   ssh teamd-ams1 'hostname; hostname -I'
   ssh teamd-ams1 'cd /var/lib/teamd/workspaces/agents/default/projects/oleg-telegram-leads && docker compose ps --all'
   ```

2. Back up the production SQLite database. The server may not have the `sqlite3` CLI, so use Python:

   ```bash
   DEPLOY_ID=prod-deploy-$(date -u +%Y%m%dT%H%M%SZ)
   ssh teamd-ams1 "cd /var/lib/teamd/workspaces/agents/default/projects/oleg-telegram-leads && DEPLOY_ID=$DEPLOY_ID python3 - <<'PY'
   import os
   import sqlite3
   from pathlib import Path

   backup = Path('backups') / os.environ['DEPLOY_ID'] / 'pur-leads.sqlite3'
   backup.parent.mkdir(parents=True, exist_ok=True)
   src = sqlite3.connect('data/pur-leads.sqlite3')
   dst = sqlite3.connect(str(backup))
   try:
       src.backup(dst)
   finally:
       dst.close()
       src.close()
   PY"
   ```

3. Back up any files that will be overwritten:

   ```bash
   ssh teamd-ams1 "cd /var/lib/teamd/workspaces/agents/default/projects/oleg-telegram-leads && mkdir -p backups/$DEPLOY_ID/files"
   ```

4. Sync only the intended files, or pull from Git when the branch is clean and pushed. For the artifacts UI slice the relevant files are:

   ```text
   src/pur_leads/services/artifact_inventory.py
   src/pur_leads/web/routes_artifacts.py
   src/pur_leads/web/app.py
   src/pur_leads/web/routes_pages.py
   src/pur_leads/web/static/app.js
   src/pur_leads/web/static/app.css
   tests/test_web_artifacts_routes.py
   tests/test_web_pages.py
   ```

5. Build images:

   ```bash
   ssh teamd-ams1 'cd /var/lib/teamd/workspaces/agents/default/projects/oleg-telegram-leads && docker compose build web worker'
   ```

6. Run container smoke checks:

   ```bash
   ssh teamd-ams1 'cd /var/lib/teamd/workspaces/agents/default/projects/oleg-telegram-leads && docker compose run --rm --entrypoint /app/.venv/bin/python web -m compileall -q src'
   ssh teamd-ams1 'cd /var/lib/teamd/workspaces/agents/default/projects/oleg-telegram-leads && docker compose run --rm --entrypoint /app/.venv/bin/python web -c "from pur_leads.web.app import create_app; from pur_leads.services.artifact_inventory import ArtifactInventoryService; print(create_app().title)"'
   ```

7. Recreate web only:

   ```bash
   ssh teamd-ams1 'cd /var/lib/teamd/workspaces/agents/default/projects/oleg-telegram-leads && docker compose up -d --no-deps --force-recreate web'
   ```

8. Verify:

   ```bash
   curl -fsS http://31.130.128.89:8000/health
   curl -i http://31.130.128.89:8000/artifacts
   ssh teamd-ams1 'cd /var/lib/teamd/workspaces/agents/default/projects/oleg-telegram-leads && docker compose logs --tail=80 web'
   ```

Expected:

- `/health` returns `{"status":"ok"}`;
- `/artifacts` redirects to `/login` without a session;
- `/api/artifacts` returns `401` without a session;
- `web` logs show Uvicorn listening on `0.0.0.0:8000`.

## Worker Policy

The production `worker` service may be stopped intentionally.

Do not start it as part of a UI-only deploy unless the operator explicitly wants background processing to resume. Starting the worker can read Telegram sources, process queued jobs, call LLM providers, and send notifications depending on the queue and settings.

For the 2026-04-30 artifacts deployment:

- `web` was rebuilt and recreated;
- `worker` was rebuilt but not started;
- `worker` remained `Exited (143)`.

## Last Verified Production Deployment

Deployment timestamp:

- `2026-04-30T20:45Z`.

Backup created on `teamd-ams1`:

- `backups/prod-deploy-20260430T204531Z/pur-leads.sqlite3`.

Verification results:

- public health: `http://31.130.128.89:8000/health` returned `200 OK`;
- public `/artifacts` returned `303` to `/login`;
- unauthenticated API returned `401`;
- `web` container listened on `0.0.0.0:8000`;
- artifact inventory inside the container read `/app/data/pur-leads.sqlite3` and returned existing artifacts.

## Rollback

Rollback web code:

1. Copy files back from `backups/<deploy-id>/files`.
2. Rebuild the image.
3. Recreate `web`.
4. Verify `/health`.

Rollback database only if the deployment changed data or migrations:

1. Stop `web` and `worker`.
2. Replace `data/pur-leads.sqlite3` from the backup.
3. Start `web`.
4. Verify `/health` and login.

For the artifacts UI deployment no intentional data migration was introduced.
