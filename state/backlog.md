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

## Later

- Telegram ingestion.
- Lead review workflow.
- Classifier/evaluation loop.
- Authentication and roles.
- Production deployment runbook.
