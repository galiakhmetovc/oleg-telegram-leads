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
- Scoring quality calibration from review labels: add hard veto/caps for clear
  noise such as sale/equipment-only/DIY, reduce vendor-only overheating,
  separate direct PUR leads from research/value questions, and add negative
  eval cases for vendor sale, ordinary HVAC, ordinary intercom, PoE/UPS purchase,
  and equipment-only requests.
- Telegram ingestion transactional completeness: close the remaining rare crash
  window between creating a blocked enrichment job and saving the source message,
  either with a combined repository unit of work or stale blocked-task cleanup.
- Frontend modularization: split the large app shell/settings/analytics/runtime
  surfaces into feature modules and shared evidence/highlight components.

## Later

- Telegram ingestion.
- Lead review workflow.
- Classifier/evaluation loop.
- Authentication and roles.
- Production deployment runbook.
