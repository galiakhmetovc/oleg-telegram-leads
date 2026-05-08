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
  persist constructor proposals from selected text, add `save + next` success
  telemetry, bulk review actions, and review verdict/tag aggregates in
  Analytics.
- Live analytics scalability: move live candidate lookup, filters, sorting,
  pagination, and high-cardinality aggregates into SQL instead of loading all
  completed Telegram enrichments into Python.
- Scoring quality calibration from review labels: add hard veto/caps for clear
  noise such as sale/equipment-only/DIY, reduce vendor-only overheating,
  separate direct PUR leads from research/value questions, and add negative
  eval cases for vendor sale, ordinary HVAC, ordinary intercom, PoE/UPS purchase,
  and equipment-only requests.
- Telegram ingestion idempotency follow-up: make source-message insert/claim and
  enrichment job creation one transactional operation so duplicate Telegram
  deliveries cannot leave orphan queued jobs.
- Notification outbox batching follow-up: claim only sendable rows or release
  non-due rows back to pending in the same flush cycle, so partial batches do
  not sit in `sending` until stale-claim timeout.
- Source cursor safety: update source `last_message_id` with monotonic
  `greatest(existing, incoming)` semantics and regression-test out-of-order live
  message callbacks.
- Frontend modularization: split the large app shell/settings/analytics/runtime
  surfaces into feature modules and shared evidence/highlight components.

## Later

- Telegram ingestion.
- Lead review workflow.
- Classifier/evaluation loop.
- Authentication and roles.
- Production deployment runbook.
