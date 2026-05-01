"""LLM entity enrichment registry and resolver behavior."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import insert, select

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.entity_enrichment import (
    canonical_entities_table,
    canonical_entity_aliases_table,
    canonical_merge_candidates_table,
    entity_enrichment_results_table,
    entity_enrichment_runs_table,
)
from pur_leads.models.telegram_sources import (
    monitored_sources_table,
    telegram_raw_export_runs_table,
)
from pur_leads.services.entity_enrichment import (
    EntityEnrichmentDecision,
    EntityEnrichmentService,
)


def test_entity_enrichment_creates_pending_canonical_and_full_trace(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    ranked_path = _write_ranked_entities(
        tmp_path,
        [
            {
                "entity_id": "entity-1",
                "group_id": "group-1",
                "canonical_text": "умный дом",
                "normalized_text": "умный дом",
                "score": 0.88,
                "ranking_status": "promote_candidate",
                "source_refs": ["telegram:purmaster:1"],
            }
        ],
    )

    with session_factory() as session:
        raw_export_run_id = _seed_raw_export_run(session, ranked_path)
        client = ScriptedEntityEnricher(
            [
                EntityEnrichmentDecision(
                    action="propose_new",
                    canonical_name="Система умного дома",
                    entity_type="solution",
                    confidence=0.91,
                    reason="Кандидат описывает самостоятельный класс решений.",
                )
            ]
        )

        result = EntityEnrichmentService(session).write_enrichment(
            raw_export_run_id,
            client=client,
            limit=10,
            provider="zai",
            model="GLM-5.1",
            model_profile="catalog-strong",
        )

        assert result.metrics["processed_entities"] == 1
        canonical = session.execute(select(canonical_entities_table)).mappings().one()
        assert canonical["canonical_name"] == "Система умного дома"
        assert canonical["normalized_name"] == "система умного дома"
        assert canonical["entity_type"] == "solution"
        assert canonical["status"] == "auto_pending"

        alias = session.execute(select(canonical_entity_aliases_table)).mappings().one()
        assert alias["canonical_entity_id"] == canonical["id"]
        assert alias["alias"] == "умный дом"
        assert alias["normalized_alias"] == "умный дом"
        assert alias["evidence_refs_json"] == ["telegram:purmaster:1"]

        enrichment_run = session.execute(select(entity_enrichment_runs_table)).mappings().one()
        assert enrichment_run["provider"] == "zai"
        assert enrichment_run["model"] == "GLM-5.1"
        assert enrichment_run["model_profile"] == "catalog-strong"
        assert enrichment_run["status"] == "succeeded"

        enrichment_result = (
            session.execute(select(entity_enrichment_results_table)).mappings().one()
        )
        assert enrichment_result["run_id"] == enrichment_run["id"]
        assert enrichment_result["ranked_entity_text"] == "умный дом"
        assert enrichment_result["action"] == "propose_new"
        assert enrichment_result["status"] == "created_canonical"
        assert enrichment_result["canonical_entity_id"] == canonical["id"]
        assert "known_canonical_entities" in enrichment_result["prompt_text"]
        assert enrichment_result["request_json"]["model"] == "GLM-5.1"
        assert enrichment_result["response_json"]["content"]["canonical_name"] == (
            "Система умного дома"
        )
        assert enrichment_result["parsed_response_json"]["action"] == "propose_new"
        assert enrichment_result["context_snapshot_json"]["known_canonical_entities"] == []


def test_entity_enrichment_uses_registry_context_for_next_candidate(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    ranked_path = _write_ranked_entities(
        tmp_path,
        [
            {
                "entity_id": "entity-1",
                "group_id": "group-1",
                "canonical_text": "умный дом",
                "normalized_text": "умный дом",
                "score": 0.88,
                "ranking_status": "promote_candidate",
                "source_refs": ["telegram:purmaster:1"],
            },
            {
                "entity_id": "entity-2",
                "group_id": "group-2",
                "canonical_text": "система умного дома",
                "normalized_text": "система умного дома",
                "score": 0.79,
                "ranking_status": "promote_candidate",
                "source_refs": ["telegram:purmaster:2"],
            },
        ],
    )

    with session_factory() as session:
        raw_export_run_id = _seed_raw_export_run(session, ranked_path)
        client = ContextAwareEntityEnricher()

        result = EntityEnrichmentService(session).write_enrichment(
            raw_export_run_id,
            client=client,
            limit=10,
        )

        assert result.metrics["processed_entities"] == 2
        assert session.execute(select(canonical_entities_table)).mappings().all()[0][
            "canonical_name"
        ] == "Система умного дома"
        assert len(session.execute(select(canonical_entities_table)).mappings().all()) == 1
        aliases = session.execute(select(canonical_entity_aliases_table)).mappings().all()
        assert {alias["normalized_alias"] for alias in aliases} == {
            "умный дом",
            "система умного дома",
        }
        results = session.execute(
            select(entity_enrichment_results_table).order_by(
                entity_enrichment_results_table.c.created_at
            )
        ).mappings().all()
        assert results[0]["status"] == "created_canonical"
        assert results[1]["status"] == "attached_to_existing"
        assert results[1]["context_snapshot_json"]["known_canonical_entities"][0][
            "canonical_name"
        ] == "Система умного дома"


def test_entity_enrichment_conflict_goes_to_merge_review(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    ranked_path = _write_ranked_entities(
        tmp_path,
        [
            {
                "entity_id": "entity-1",
                "group_id": "group-1",
                "canonical_text": "умный дом",
                "normalized_text": "умный дом",
                "score": 0.88,
                "ranking_status": "promote_candidate",
                "source_refs": ["telegram:purmaster:1"],
            },
            {
                "entity_id": "entity-2",
                "group_id": "group-2",
                "canonical_text": "система умный дом",
                "normalized_text": "система умный дом",
                "score": 0.79,
                "ranking_status": "promote_candidate",
                "source_refs": ["telegram:purmaster:2"],
            },
        ],
    )

    with session_factory() as session:
        raw_export_run_id = _seed_raw_export_run(session, ranked_path)
        client = ScriptedEntityEnricher(
            [
                EntityEnrichmentDecision(
                    action="propose_new",
                    canonical_name="Система умного дома",
                    entity_type="solution",
                    confidence=0.91,
                    reason="first",
                ),
                EntityEnrichmentDecision(
                    action="propose_new",
                    canonical_name="Системы умного дома",
                    entity_type="solution",
                    confidence=0.72,
                    reason="looks similar but not identical",
                ),
            ]
        )

        result = EntityEnrichmentService(session).write_enrichment(
            raw_export_run_id,
            client=client,
            limit=10,
        )

        assert result.metrics["merge_review_candidates"] == 1
        assert len(session.execute(select(canonical_entities_table)).mappings().all()) == 1
        merge = session.execute(select(canonical_merge_candidates_table)).mappings().one()
        assert merge["status"] == "pending_review"
        assert merge["proposed_name"] == "Системы умного дома"
        assert merge["evidence_json"]["ranked_entity_text"] == "система умный дом"
        result_rows = session.execute(
            select(entity_enrichment_results_table).order_by(
                entity_enrichment_results_table.c.created_at
            )
        ).mappings().all()
        assert result_rows[1]["status"] == "needs_merge_review"


class ScriptedEntityEnricher:
    def __init__(self, decisions: list[EntityEnrichmentDecision]) -> None:
        self.decisions = list(decisions)
        self.calls: list[dict[str, object]] = []

    def enrich(self, request):
        self.calls.append(request.as_jsonable())
        return self.decisions.pop(0)


class ContextAwareEntityEnricher:
    def enrich(self, request):
        if request.context_snapshot["known_canonical_entities"]:
            canonical = request.context_snapshot["known_canonical_entities"][0]
            return EntityEnrichmentDecision(
                action="attach_to_existing",
                canonical_entity_id=canonical["id"],
                canonical_name=canonical["canonical_name"],
                entity_type=canonical["entity_type"],
                confidence=0.86,
                reason="Known canonical was provided in request context.",
            )
        return EntityEnrichmentDecision(
            action="propose_new",
            canonical_name="Система умного дома",
            entity_type="solution",
            confidence=0.91,
            reason="First mention creates canonical registry entry.",
        )


def _seed_raw_export_run(session, ranked_path: Path) -> str:
    now = utc_now()
    monitored_source_id = new_id()
    raw_export_run_id = new_id()
    session.execute(
        insert(monitored_sources_table).values(
            id=monitored_source_id,
            source_kind="telegram_channel",
            telegram_id="-10042",
            username="purmaster",
            title="ПУР",
            invite_link_hash=None,
            input_ref="https://t.me/purmaster",
            source_purpose="catalog_ingestion",
            assigned_userbot_account_id=None,
            priority="normal",
            status="active",
            lead_detection_enabled=False,
            catalog_ingestion_enabled=True,
            phase_enabled=True,
            start_mode="from_beginning",
            start_message_id=None,
            start_recent_limit=None,
            start_recent_days=None,
            historical_backfill_policy="all",
            checkpoint_message_id=None,
            checkpoint_date=None,
            last_preview_at=None,
            preview_message_count=None,
            next_poll_at=None,
            poll_interval_seconds=300,
            last_success_at=None,
            last_error_at=None,
            last_error=None,
            added_by="test",
            activated_by="test",
            activated_at=now,
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        insert(telegram_raw_export_runs_table).values(
            id=raw_export_run_id,
            monitored_source_id=monitored_source_id,
            source_ref="https://t.me/purmaster",
            source_kind="telegram_channel",
            telegram_id="-10042",
            username="purmaster",
            title="ПУР",
            export_format="telethon_jsonl_v1",
            output_dir=str(ranked_path.parent),
            result_json_path=str(ranked_path.parent / "result.json"),
            messages_jsonl_path=str(ranked_path.parent / "messages.jsonl"),
            attachments_jsonl_path=str(ranked_path.parent / "attachments.jsonl"),
            messages_parquet_path=str(ranked_path.parent / "messages.parquet"),
            attachments_parquet_path=str(ranked_path.parent / "attachments.parquet"),
            manifest_path=str(ranked_path.parent / "manifest.json"),
            message_count=2,
            attachment_count=0,
            status="succeeded",
            error=None,
            started_at=datetime(2026, 1, 31, 10, 0, tzinfo=UTC),
            finished_at=datetime(2026, 1, 31, 10, 1, tzinfo=UTC),
            metadata_json={
                "entity_ranking": {
                    "ranked_entities_parquet_path": str(ranked_path),
                    "ranking_policy": "rule_based_v1",
                }
            },
            created_at=now,
        )
    )
    session.commit()
    return raw_export_run_id


def _write_ranked_entities(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    path = tmp_path / "ranked_entities.parquet"
    pylist = []
    for row in rows:
        pylist.append(
            {
                "entity_id": row["entity_id"],
                "group_id": row["group_id"],
                "canonical_text": row["canonical_text"],
                "normalized_text": row["normalized_text"],
                "lemma_text": row["normalized_text"],
                "pos_pattern_json": json.dumps(["ADJ", "NOUN"], ensure_ascii=False),
                "mention_count": 4,
                "source_count": 2,
                "source_refs_json": json.dumps(row["source_refs"], ensure_ascii=False),
                "example_contexts_json": json.dumps(
                    [f"пример: {row['canonical_text']}"], ensure_ascii=False
                ),
                "entity_type_counts_json": json.dumps({"telegram_message": 2}),
                "group_confidence": "high",
                "group_method": "exact",
                "score": row["score"],
                "ranking_status": row["ranking_status"],
                "reasons_json": json.dumps(["test"], ensure_ascii=False),
                "penalties_json": json.dumps([], ensure_ascii=False),
            }
        )
    schema = pa.schema(
        [
            ("entity_id", pa.string()),
            ("group_id", pa.string()),
            ("canonical_text", pa.string()),
            ("normalized_text", pa.string()),
            ("lemma_text", pa.string()),
            ("pos_pattern_json", pa.string()),
            ("mention_count", pa.int64()),
            ("source_count", pa.int64()),
            ("source_refs_json", pa.string()),
            ("example_contexts_json", pa.string()),
            ("entity_type_counts_json", pa.string()),
            ("group_confidence", pa.string()),
            ("group_method", pa.string()),
            ("score", pa.float64()),
            ("ranking_status", pa.string()),
            ("reasons_json", pa.string()),
            ("penalties_json", pa.string()),
        ]
    )
    pq.write_table(pa.Table.from_pylist(pylist, schema=schema), path)
    return path
