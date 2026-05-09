# Backlog

## Near Term

- Define the first v2 workflow.
- Import or reference confirmed lead examples safely.
- Add initial database migration.
- Add API contract for the first workflow.
- Add the first operator screen.
- Batch enrichment optimization, deferred until explicitly resumed:
  resumable cache by `message_id + text_hash + config_hash`, duplicate-text
  cache by `text_hash`, sharded process runner, compressed `.jsonl.zst` output,
  1/2/4 process benchmarks with thread caps, configured anchor-based Yargy
  gating, and only then careful word/lemma caching if tests prove it does not
  reduce full enrichment quality.
- Review workflow polish, remaining after the first queue pass:
  add constructor preview/re-enrichment after save, add `save + next` success
  telemetry, bulk review actions, and review verdict/tag aggregates in
  Analytics. Constructor flows for dictionary/fact/domain-signal/noise targets
  already write PostgreSQL NLP revisions.
- Scoring quality calibration from review labels: continue reducing
  vendor-only overheating, refine the split between direct PUR leads and
  research/value questions, and grow the negative eval set. Hard noise score
  caps and first negative regressions for vendor sale, ordinary HVAC, ordinary
  intercom, PoE/UPS purchase, equipment-only requests, and DSS parking software
  license text are in place.
- Telegram ingestion transactional completeness: close the remaining rare crash
  window between creating a blocked enrichment job and saving the source message,
  either with a combined repository unit of work or stale blocked-task cleanup.
- Frontend modularization: continue splitting the large app shell/settings/
  analytics/runtime surfaces into feature modules and shared evidence/highlight
  components. Analytics types, candidate evidence rendering, and the Review
  constructor have already been extracted into `frontend/src/analytics/`.
  Runtime logs, system status, and project documentation pages have been
  extracted into `frontend/src/runtime/RuntimePages.tsx`. Remaining large
  surfaces are mostly the app shell, Testing/enrichment view, and Settings
  Center.

## Later

- Telegram ingestion.
- Lead review workflow.
- Classifier/evaluation loop.
- Authentication and roles.
- Production deployment runbook.
