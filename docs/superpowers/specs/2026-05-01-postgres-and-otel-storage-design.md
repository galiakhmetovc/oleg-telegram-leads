# Postgres And OTel Storage Design

Date: 2026-05-01

Current implementation status is maintained in `docs/README.md`. This document
records the storage decision made before implementing the full trace/evidence
product layer.

## Decision

PUR Leads is moving from SQLite as the operational database to Postgres.

Postgres becomes the product source of truth for:

- administrators, sessions, resources, secrets references, and settings;
- Telegram sources and hot source messages;
- scheduler jobs, runs, leases, retries, and task state;
- catalog/knowledge entities, candidates, evidence, and snapshots;
- lead clusters, lead events, matches, feedback, CRM, and tasks;
- AI registry metadata, model profiles, AI run metadata, and trace metadata;
- OTel-compatible product trace spans and links.

SQLite remains allowed only for:

- local developer/test fallback while migration is in progress;
- generated artifact databases such as per-run FTS5 search indexes;
- Chroma internal files when Chroma runs embedded;
- reading historical backups until migration cleanup is complete.

SQLite must not remain the production operational database.

## Why Postgres

The current product shape needs concurrent writes from:

- continuous Telegram ingest;
- multiple worker processes;
- parser jobs;
- LLM calls and lease accounting;
- web UI edits;
- lead/CRM actions;
- trace span recording.

SQLite is useful for a single-node prototype, but it is a poor fit for this
runtime profile. Postgres gives proper concurrent writes, row-level locking,
JSONB, stronger transactional behavior, operational tooling, and a path to
future `pgvector` if we decide to simplify the vector stack.

## Jaeger And OTel Storage

Jaeger is a tracing backend, not the product database. According to Jaeger 2.17
documentation:

- built-in storage backends include Elasticsearch/OpenSearch, Cassandra, Badger
  for single-node local storage, Kafka as a buffer, and memory for local use;
- Jaeger states that Cassandra, Elasticsearch, and OpenSearch are the primary
  supported distributed storage backends;
- for large-scale production Jaeger recommends OpenSearch over Cassandra;
- custom backends, including ClickHouse integrations, go through Jaeger's Remote
  Storage API rather than being the default Jaeger storage path;
- Service Performance Monitoring / RED metrics are produced from spans through
  spanmetrics and exported to a Prometheus-compatible metrics store, or computed
  directly from Elasticsearch/OpenSearch by Jaeger Query.

Sources:

- `https://www.jaegertracing.io/docs/2.17/`
- `https://www.jaegertracing.io/docs/2.16/storage/`
- `https://www.jaegertracing.io/docs/2.17/storage/opensearch/`
- `https://www.jaegertracing.io/docs/2.17/operations/monitoring/`
- `https://www.jaegertracing.io/docs/next-release-v2/architecture/spm/`

## Target Observability Stack

First production-compatible target:

```text
Application
  -> OpenTelemetry SDK / OTLP exporter
  -> OpenTelemetry Collector / Jaeger v2 pipeline
  -> Jaeger trace storage: OpenSearch
  -> RED metrics: Prometheus-compatible store
```

Product audit remains in Postgres:

```text
lead_cluster
  -> trace spans/links in Postgres
  -> source message / catalog / AI run / notification / feedback tables
  -> artifact paths for large prompt/response/raw files
```

This split is intentional:

- Jaeger/OpenSearch/Prometheus explain runtime behavior, latency, errors, and
  dependency timing.
- Postgres explains durable product decisions and keeps enough metadata to
  survive trace sampling, retention, and external telemetry outages.

## ClickHouse Position

ClickHouse is not the primary product database.

It may be useful later for:

- high-volume analytics over spans/events;
- long-retention telemetry;
- trace storage through Jaeger's Remote Storage API;
- large feature/quality aggregates.

Do not add ClickHouse to the first Postgres migration unless real telemetry
volume or query latency proves OpenSearch/Prometheus insufficient.

## Migration Direction

Immediate work:

1. Introduce `PUR_DATABASE_URL` and a Postgres-capable SQLAlchemy engine.
2. Keep `PUR_DATABASE_PATH` as a temporary SQLite fallback for local tests.
3. Make Alembic migrations run on Postgres.
4. Replace SQLite-specific runtime locking with Postgres-safe row/advisory locks.
5. Update Docker Compose production to include Postgres and use `PUR_DATABASE_URL`.
6. Reset production domain data after a backup while preserving settings/admin
   bootstrap/resources/secrets as explicitly requested by the operator.

Legacy cleanup:

- rename SQLite-specific settings and UI labels to database-neutral names;
- keep artifact SQLite preview support because FTS/Chroma artifacts still use
  SQLite files;
- replace `backup_sqlite_enabled` with a Postgres-aware backup policy;
- remove production reliance on `data/pur-leads.sqlite3`;
- audit migrations for dialect-specific SQL before enabling Postgres in prod.

## Implementation Slice 2026-05-01

Implemented:

- `PUR_DATABASE_URL` and `create_database_engine()` choose Postgres when
  configured and SQLite only as a fallback.
- CLI and FastAPI app accept/pass `database_url`.
- Docker Compose includes a `postgres` service and points `web`/`worker` at it.
- `psycopg[binary]` is installed for SQLAlchemy Postgres connections.
- AI concurrency leases use `pg_advisory_xact_lock(hashtext(...))` on Postgres
  instead of SQLite `BEGIN IMMEDIATE`.
- Alembic migrations through `0027_postgres_backup_type` have been made
  Postgres-compatible for fresh database creation.
- Alembic version storage is widened on Postgres because repository revision IDs
  are longer than Alembic's default 32-character column.
- Database backup API is now `/api/operations/backups/database`.
  - Postgres backup type: `postgres_pg_dump`.
  - Backup command: `pg_dump --format=custom --no-owner --no-privileges`.
  - Validation command: `pg_restore --list`.
  - Passwords are passed through process environment and are not stored in
    backup manifests.
  - The old `/api/operations/backups/sqlite` route remains only as a compatibility
    alias while UI/test callers migrate.

Still pending:

- production cutover/reset on `teamd-ams1`;
- replacing the `backup_sqlite_enabled` setting name with a database-neutral
  setting;
- moving more test fixtures from direct `create_sqlite_engine()` to the generic
  engine helper where useful;
- first OTel SDK/Collector integration and Jaeger/OpenSearch deployment;
- Postgres-native reset/retention runbooks.

## Acceptance Criteria

- The web app and CLI can start from `PUR_DATABASE_URL`.
- Alembic head can create a fresh Postgres database.
- Worker AI lease acquisition does not execute SQLite `BEGIN IMMEDIATE` on
  Postgres.
- Production docs no longer instruct operators to treat SQLite as the product
  database.
- SQLite remains supported only for tests/local fallback and generated
  analytics artifacts.
