# Current State

## Active Work

- Build PUR Leads v2 from a clean scaffold.
- Keep v1 only as reference material.
- Use exported production-confirmed lead messages as seed examples for later design.
- Follow root `AGENTS.md` as the project working rules.
- First product slice: web text enrichment UI with FastAPI snapshots, SSE
  progress, Celery worker execution, PostgreSQL persistence, and configurable
  Natasha/Yargy NLP pipeline.

## Blockers

- Product flows for v2 are not specified yet.

## Next Steps

1. Implement persisted enrichment jobs and events.
2. Implement configurable Natasha/Yargy enrichment pipeline.
3. Add MUI operator UI for input, progress, annotated text, and result tabs.
4. Verify API, worker, SSE, and UI through Docker Compose.
