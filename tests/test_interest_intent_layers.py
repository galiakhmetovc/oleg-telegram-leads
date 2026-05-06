"""Configurable intent layers over prepared interest-context data."""

from datetime import UTC, datetime
import json

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import insert

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.interest_context_drafts import (
    interest_core_analysis_matches_table,
    interest_core_analysis_runs_table,
)
from pur_leads.models.telegram_sources import (
    monitored_sources_table,
    telegram_raw_export_runs_table,
)
from pur_leads.services.interest_intent_layers import InterestIntentLayerService


def test_intent_layer_matches_context_pattern_against_stage2_lemmas(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    now = datetime(2026, 5, 6, 8, 0, tzinfo=UTC)
    texts_path = tmp_path / "processed" / "texts.parquet"
    texts_path.parent.mkdir(parents=True)
    pq.write_table(
        pa.Table.from_pylist(
            [
                {
                    "export_run_id": "raw-1",
                    "monitored_source_id": "source-1",
                    "telegram_message_id": 716254,
                    "row_index": 1,
                    "date": now.isoformat(),
                    "message_url": "https://t.me/chat_mila_kolpakova/716254",
                    "raw_text": "Какие домофоны ставите в проекты? Нужен минималистичный.",
                    "clean_text": "какие домофоны ставите в проекты нужен минималистичный",
                    "normalization_lang": "ru",
                    "tokens_json": json.dumps(
                        ["какие", "домофоны", "ставите", "проекты", "нужен"],
                        ensure_ascii=False,
                    ),
                    "lemmas_json": json.dumps(
                        ["какой", "домофон", "ставить", "проект", "нужный"],
                        ensure_ascii=False,
                    ),
                    "pos_tags_json": json.dumps(["ADJ", "NOUN", "VERB", "NOUN", "ADJ"]),
                    "token_map_json": json.dumps([]),
                    "token_count": 5,
                    "has_text": True,
                    "normalization_status": "normalized",
                    "normalization_error": None,
                    "raw_message_json": "{}",
                }
            ]
        ),
        texts_path,
    )
    with session_factory() as session:
        session.execute(
            insert(monitored_sources_table).values(
                id="source-1",
                source_kind="telegram_group",
                telegram_id="-1001",
                username="chat_mila_kolpakova",
                title="Чат дизайнеров",
                invite_link_hash=None,
                input_ref="ChatLeads",
                source_purpose="interest_context_seed",
                interest_context_id="context-1",
                assigned_userbot_account_id=None,
                priority="normal",
                status="active",
                lead_detection_enabled=False,
                catalog_ingestion_enabled=False,
                phase_enabled=True,
                start_mode="from_beginning",
                start_message_id=None,
                start_recent_limit=None,
                start_recent_days=None,
                historical_backfill_policy="none",
                checkpoint_message_id=None,
                checkpoint_date=None,
                last_preview_at=None,
                preview_message_count=None,
                next_poll_at=None,
                poll_interval_seconds=60,
                last_success_at=None,
                last_error_at=None,
                last_error=None,
                added_by="admin",
                activated_by=None,
                activated_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        session.execute(
            insert(telegram_raw_export_runs_table).values(
                id="raw-1",
                monitored_source_id="source-1",
                source_ref="ChatLeads",
                source_kind="telegram_group",
                telegram_id="-1001",
                username="chat_mila_kolpakova",
                title="Чат дизайнеров",
                export_format="telegram_desktop_json",
                output_dir=str(tmp_path),
                result_json_path=str(tmp_path / "result.json"),
                messages_jsonl_path=str(tmp_path / "messages.jsonl"),
                attachments_jsonl_path=str(tmp_path / "attachments.jsonl"),
                messages_parquet_path=str(tmp_path / "messages.parquet"),
                attachments_parquet_path=str(tmp_path / "attachments.parquet"),
                manifest_path=str(tmp_path / "manifest.json"),
                message_count=1,
                attachment_count=0,
                status="succeeded",
                error=None,
                started_at=now,
                finished_at=now,
                metadata_json={
                    "text_normalization": {
                        "texts_parquet_path": str(texts_path),
                    }
                },
                created_at=now,
            )
        )
        session.execute(
            insert(interest_core_analysis_runs_table).values(
                id="broad-1",
                context_id="context-1",
                monitored_source_id="source-1",
                raw_export_run_id="raw-1",
                status="succeeded",
                source_title="Чат дизайнеров",
                message_count=1,
                core_item_count=1,
                matched_message_count=1,
                match_count=1,
                summary_json={"algorithm": "test"},
                created_by="admin",
                started_at=now,
                finished_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        session.execute(
            insert(interest_core_analysis_matches_table).values(
                id="broad-match-1",
                run_id="broad-1",
                context_id="context-1",
                source_message_id="message-1",
                interest_core_item_id="core-1",
                telegram_message_id=716254,
                message_date=now,
                sender_id="user-1",
                message_text="Какие домофоны ставите в проекты? Нужен минималистичный.",
                canonical_name="системы контроля доступа",
                category="безопасность",
                matched_text="проекты",
                match_kind="synonym",
                score=0.82,
                evidence_json={},
                created_at=now,
            )
        )
        service = InterestIntentLayerService(session)
        layer = service.create_layer(
            context_id="context-1",
            name="Домофоны",
            actor="admin",
            include_patterns=[r"\bнужный\b"],
            context_patterns=[r"\bдомофон\b"],
            require_include_match=True,
            require_context_match=True,
            min_score=0.5,
        )

        result = service.run_layer(
            context_id="context-1",
            layer_id=layer.id,
            broad_analysis_run_id="broad-1",
            actor="admin",
        )

        assert result["summary"]["match_count"] == 1
        evidence = result["top_matches"][0]["evidence_json"]
        assert evidence["prepared_text"]["source"] == "text_normalization"
        assert evidence["context_hits"] == [r"\bдомофон\b"]

        filtered_layer = service.create_layer(
            context_id="context-1",
            name="Домофоны без дизайнерского шума",
            actor="admin",
            include_patterns=[r"\bнужный\b"],
            context_patterns=[r"\bдомофон\b"],
            exclude_lemmas=["домофоны"],
            require_include_match=True,
            require_context_match=True,
            min_score=0.5,
        )

        filtered = service.run_layer(
            context_id="context-1",
            layer_id=filtered_layer.id,
            broad_analysis_run_id="broad-1",
            actor="admin",
        )

        assert filtered["summary"]["match_count"] == 0


def test_ai_filter_metadata_excludes_semantic_false_positives_and_boosts_correct(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    now = datetime(2026, 5, 6, 8, 0, tzinfo=UTC)
    texts_path = tmp_path / "processed" / "texts.parquet"
    texts_path.parent.mkdir(parents=True)
    messages = [
        (
            "bad-exact",
            719012,
            "Нужно определить размер ниши для подсветки скалы.",
            ["нужно", "определить", "размер", "ниши", "подсветки", "скалы"],
            ["нужно", "определить", "размер", "ниша", "подсветка", "скала"],
        ),
        (
            "bad-semantic",
            719099,
            "Подскажите, какой размер ниши нужен для подсветки стены?",
            ["подскажите", "какой", "размер", "ниши", "нужен", "подсветки", "стены"],
            ["подсказать", "какой", "размер", "ниша", "нужный", "подсветка", "стена"],
        ),
        (
            "good-protected",
            718839,
            "Где можно заказать систему видеонаблюдения для квартиры?",
            ["где", "можно", "заказать", "систему", "видеонаблюдения", "квартиры"],
            ["где", "можно", "заказать", "система", "видеонаблюдение", "квартира"],
        ),
        (
            "good-semantic",
            718840,
            "Где можно заказать систему видеонаблюдения для квартиры?",
            ["где", "можно", "заказать", "систему", "видеонаблюдения", "квартиры"],
            ["где", "можно", "заказать", "система", "видеонаблюдение", "квартира"],
        ),
    ]
    pq.write_table(
        pa.Table.from_pylist(
            [
                {
                    "export_run_id": "raw-1",
                    "monitored_source_id": "source-1",
                    "telegram_message_id": telegram_message_id,
                    "row_index": index,
                    "date": now.isoformat(),
                    "message_url": f"https://t.me/chat_mila_kolpakova/{telegram_message_id}",
                    "raw_text": text,
                    "clean_text": " ".join(tokens),
                    "normalization_lang": "ru",
                    "tokens_json": json.dumps(tokens, ensure_ascii=False),
                    "lemmas_json": json.dumps(lemmas, ensure_ascii=False),
                    "pos_tags_json": json.dumps(["NOUN"] * len(tokens)),
                    "token_map_json": json.dumps([]),
                    "token_count": len(tokens),
                    "has_text": True,
                    "normalization_status": "normalized",
                    "normalization_error": None,
                    "raw_message_json": "{}",
                }
                for index, (_, telegram_message_id, text, tokens, lemmas) in enumerate(
                    messages, start=1
                )
            ]
        ),
        texts_path,
    )
    with session_factory() as session:
        session.execute(
            insert(monitored_sources_table).values(
                id="source-1",
                source_kind="telegram_group",
                telegram_id="-1001",
                username="chat_mila_kolpakova",
                title="Чат дизайнеров",
                invite_link_hash=None,
                input_ref="ChatLeads",
                source_purpose="interest_context_seed",
                interest_context_id="context-1",
                assigned_userbot_account_id=None,
                priority="normal",
                status="active",
                lead_detection_enabled=False,
                catalog_ingestion_enabled=False,
                phase_enabled=True,
                start_mode="from_beginning",
                start_message_id=None,
                start_recent_limit=None,
                start_recent_days=None,
                historical_backfill_policy="none",
                checkpoint_message_id=None,
                checkpoint_date=None,
                last_preview_at=None,
                preview_message_count=None,
                next_poll_at=None,
                poll_interval_seconds=60,
                last_success_at=None,
                last_error_at=None,
                last_error=None,
                added_by="admin",
                activated_by=None,
                activated_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        session.execute(
            insert(telegram_raw_export_runs_table).values(
                id="raw-1",
                monitored_source_id="source-1",
                source_ref="ChatLeads",
                source_kind="telegram_group",
                telegram_id="-1001",
                username="chat_mila_kolpakova",
                title="Чат дизайнеров",
                export_format="telegram_desktop_json",
                output_dir=str(tmp_path),
                result_json_path=str(tmp_path / "result.json"),
                messages_jsonl_path=str(tmp_path / "messages.jsonl"),
                attachments_jsonl_path=str(tmp_path / "attachments.jsonl"),
                messages_parquet_path=str(tmp_path / "messages.parquet"),
                attachments_parquet_path=str(tmp_path / "attachments.parquet"),
                manifest_path=str(tmp_path / "manifest.json"),
                message_count=len(messages),
                attachment_count=0,
                status="succeeded",
                error=None,
                started_at=now,
                finished_at=now,
                metadata_json={"text_normalization": {"texts_parquet_path": str(texts_path)}},
                created_at=now,
            )
        )
        session.execute(
            insert(interest_core_analysis_runs_table).values(
                id="broad-1",
                context_id="context-1",
                monitored_source_id="source-1",
                raw_export_run_id="raw-1",
                status="succeeded",
                source_title="Чат дизайнеров",
                message_count=len(messages),
                core_item_count=1,
                matched_message_count=len(messages),
                match_count=len(messages),
                summary_json={"algorithm": "test"},
                created_by="admin",
                started_at=now,
                finished_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        session.execute(
            insert(interest_core_analysis_matches_table),
            [
                {
                    "id": f"broad-match-{index}",
                    "run_id": "broad-1",
                    "context_id": "context-1",
                    "source_message_id": source_message_id,
                    "interest_core_item_id": "core-1",
                    "telegram_message_id": telegram_message_id,
                    "message_date": now,
                    "sender_id": "user-1",
                    "message_text": text,
                    "canonical_name": "автоматизация",
                    "category": "автоматизация",
                    "matched_text": "подсветка",
                    "match_kind": "synonym",
                    "score": 0.82,
                    "evidence_json": {},
                    "created_at": now,
                }
                for index, (source_message_id, telegram_message_id, text, _, _) in enumerate(
                    messages, start=1
                )
            ],
        )
        service = InterestIntentLayerService(session)
        layer = service.create_layer(
            context_id="context-1",
            name="AI-фильтр",
            actor="admin",
            include_patterns=["нужно", "нужный", "подскажите", "заказать"],
            context_patterns=["нет такого контекста"],
            exclude_lemmas=["видеонаблюдение"],
            require_include_match=True,
            require_context_match=True,
            min_score=0.95,
            metadata_json={
                "excluded_source_message_ids": ["bad-exact"],
                "operator_semantic_negative_examples": [
                    "Нужно определить размер ниши для подсветки скалы."
                ],
                "operator_semantic_positive_examples": [
                    "Где можно заказать систему видеонаблюдения для квартиры?"
                ],
                "operator_semantic_negative_threshold": 0.55,
                "operator_semantic_positive_margin": 0.03,
                "operator_positive_boost_threshold": 0.55,
                "operator_positive_score_boost": 0.08,
                "positive_source_message_ids": ["good-protected"],
            },
        )

        result = service.run_layer(
            context_id="context-1",
            layer_id=layer.id,
            broad_analysis_run_id="broad-1",
            actor="admin",
        )

        assert result["summary"]["match_count"] == 2
        assert {row["source_message_id"] for row in result["top_matches"]} == {
            "good-protected",
            "good-semantic",
        }
        assert result["summary"]["exclusions"]["total"] == 2
        assert result["summary"]["exclusions"]["semantic_negative"] == 1
        assert result["summary"]["positive_boosted_count"] == 2
        assert all(row["evidence_json"]["positive_boost"] > 0 for row in result["top_matches"])
