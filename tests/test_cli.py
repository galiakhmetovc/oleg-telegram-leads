from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any
import zipfile

import pytest
import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import func
from sqlalchemy import insert
from sqlalchemy import inspect
from sqlalchemy import select
from fastapi.testclient import TestClient

import pur_leads.cli as cli
from pur_leads.cli import _build_ai_model_concurrency_limiter, main
from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.integrations.ai.chat import AiChatCompletion
from pur_leads.integrations.ai.zai_client import AiProviderError
from pur_leads.integrations.telegram.types import (
    ResolvedTelegramSource,
    SourceAccessResult,
    TelegramMessage,
)
from pur_leads.models.audit import operational_events_table
from pur_leads.models.catalog import (
    catalog_candidates_table,
    extraction_runs_table,
    parsed_chunks_table,
)
from pur_leads.models.ai import (
    ai_agent_routes_table,
    ai_agents_table,
    ai_model_limits_table,
    ai_model_profiles_table,
    ai_models_table,
    ai_provider_accounts_table,
    ai_providers_table,
)
from pur_leads.models.evaluation import decision_records_table
from pur_leads.models.entity_enrichment import canonical_entities_table
from pur_leads.models.leads import lead_clusters_table, lead_events_table
from pur_leads.models.telegram_sources import (
    monitored_sources_table,
    source_access_checks_table,
    source_messages_table,
    telegram_raw_export_runs_table,
)
from pur_leads.services.catalog_sources import CatalogSourceService
from pur_leads.services.ai_registry import AiRegistryService
from pur_leads.services.scheduler import SchedulerService
from pur_leads.services.secrets import SecretRefService
from pur_leads.services.settings import SettingsService
from pur_leads.services.telegram_chroma_index import TelegramChromaIndexService
from pur_leads.services.telegram_fts_index import TelegramFtsIndexService
from pur_leads.services.telegram_raw_export import TelegramRawExportService
from pur_leads.services.telegram_sources import TelegramSourceService
from pur_leads.services.telegram_text_normalization import TelegramTextNormalizationService
from pur_leads.services.userbots import UserbotAccountService
from pur_leads.workers.runtime import ParsedArtifact


def test_cli_db_upgrade_creates_database(tmp_path):
    db_path = tmp_path / "cli.db"

    main(["--database-path", str(db_path), "db", "upgrade"])

    tables = set(inspect(create_sqlite_engine(db_path)).get_table_names())
    assert "settings" in tables
    assert "scheduler_jobs" in tables


def test_cli_settings_set_and_list(tmp_path, capsys):
    db_path = tmp_path / "cli.db"
    main(["--database-path", str(db_path), "db", "upgrade"])

    main(["--database-path", str(db_path), "settings", "set", "telegram_worker_count", "2"])
    main(["--database-path", str(db_path), "settings", "list"])

    output = capsys.readouterr().out
    assert "telegram_worker_count=2" in output


def test_cli_import_telegram_desktop_archive_writes_raw_export(tmp_path, capsys):
    db_path = tmp_path / "cli.db"
    archive_path = _write_cli_desktop_archive(tmp_path)

    main(
        [
            "--database-path",
            str(db_path),
            "import",
            "telegram-desktop-archive",
            "--archive-path",
            str(archive_path),
            "--input-ref",
            "https://t.me/chat_mila_kolpakova",
            "--purpose",
            "lead_monitoring",
            "--raw-root",
            str(tmp_path / "raw"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert output["message_count"] == 1
    assert output["created_source_messages"] == 1
    assert Path(output["messages_parquet_path"]).exists()

    engine = create_sqlite_engine(db_path)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        assert session.execute(select(func.count()).select_from(source_messages_table)).scalar_one() == 1
        run = session.execute(select(telegram_raw_export_runs_table)).mappings().one()
        assert run["export_format"] == "telegram_desktop_json_v1"


def test_cli_analyze_telegram_eda_writes_report(tmp_path, capsys):
    db_path = tmp_path / "cli.db"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        source = TelegramSourceService(session).create_draft(
            "https://t.me/purmaster",
            added_by="admin",
            purpose="catalog_ingestion",
            start_mode="from_beginning",
        )
        export = TelegramRawExportService(session, raw_root=tmp_path / "raw").write_export(
            source=source,
            resolved_source=ResolvedTelegramSource(
                input_ref="https://t.me/purmaster",
                source_kind="telegram_channel",
                telegram_id="-10042",
                username="purmaster",
                title="ПУР",
            ),
            messages=[
                TelegramMessage(
                    monitored_source_ref="https://t.me/purmaster",
                    telegram_message_id=1,
                    message_date=datetime(2026, 1, 31, 10, 15, 0, tzinfo=UTC),
                    sender_id="channel-1",
                    sender_display="ПУР",
                    text="Каталог",
                    caption=None,
                    has_media=False,
                    media_metadata_json=None,
                    reply_to_message_id=None,
                    thread_id=None,
                    forward_metadata_json=None,
                    raw_metadata_json={},
                ),
            ],
        )

    main(
        [
            "--database-path",
            str(db_path),
            "analyze",
            "telegram-eda",
            "--raw-export-run-id",
            export.run_id,
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert output["raw_export_run_id"] == export.run_id
    assert output["metrics"]["total_messages"] == 1
    assert output["recommended_decision"] == "go_with_warnings"
    assert Path(output["report_path"]).exists()


def test_cli_analyze_telegram_texts_writes_normalized_parquet(tmp_path, capsys):
    db_path = tmp_path / "cli.db"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        source = TelegramSourceService(session).create_draft(
            "https://t.me/purmaster",
            added_by="admin",
            purpose="catalog_ingestion",
            start_mode="from_beginning",
        )
        export = TelegramRawExportService(session, raw_root=tmp_path / "raw").write_export(
            source=source,
            resolved_source=ResolvedTelegramSource(
                input_ref="https://t.me/purmaster",
                source_kind="telegram_channel",
                telegram_id="-10042",
                username="purmaster",
                title="ПУР",
            ),
            messages=[
                TelegramMessage(
                    monitored_source_ref="https://t.me/purmaster",
                    telegram_message_id=1,
                    message_date=datetime(2026, 1, 31, 10, 15, 0, tzinfo=UTC),
                    sender_id="channel-1",
                    sender_display="ПУР",
                    text="Умный дом",
                    caption=None,
                    has_media=False,
                    media_metadata_json=None,
                    reply_to_message_id=None,
                    thread_id=None,
                    forward_metadata_json=None,
                    raw_metadata_json={},
                )
            ],
        )

    processed_root = tmp_path / "processed"
    main(
        [
            "--database-path",
            str(db_path),
            "analyze",
            "telegram-texts",
            "--raw-export-run-id",
            export.run_id,
            "--processed-root",
            str(processed_root),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert output["raw_export_run_id"] == export.run_id
    assert output["metrics"]["total_messages"] == 1
    assert output["metrics"]["rows_with_text"] == 1
    assert Path(output["texts_parquet_path"]).exists()
    assert Path(output["summary_path"]).exists()


def test_cli_analyze_telegram_artifacts_writes_artifact_texts(tmp_path, capsys):
    db_path = tmp_path / "cli.db"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    document_path = tmp_path / "catalog.txt"
    document_path.write_text("Датчики протечки и реле защиты", encoding="utf-8")
    with session_factory() as session:
        source = TelegramSourceService(session).create_draft(
            "https://t.me/purmaster",
            added_by="admin",
            purpose="catalog_ingestion",
            start_mode="from_beginning",
        )
        export = TelegramRawExportService(session, raw_root=tmp_path / "raw").write_export(
            source=source,
            resolved_source=ResolvedTelegramSource(
                input_ref="https://t.me/purmaster",
                source_kind="telegram_channel",
                telegram_id="-10042",
                username="purmaster",
                title="ПУР",
            ),
            messages=[
                TelegramMessage(
                    monitored_source_ref="https://t.me/purmaster",
                    telegram_message_id=1,
                    message_date=datetime(2026, 1, 31, 10, 15, 0, tzinfo=UTC),
                    sender_id="channel-1",
                    sender_display="ПУР",
                    text="Документ каталога",
                    caption=None,
                    has_media=True,
                    media_metadata_json={
                        "type": "MessageMediaDocument",
                        "document": {
                            "file_name": "catalog.txt",
                            "mime_type": "text/plain",
                            "file_size": document_path.stat().st_size,
                            "downloadable": True,
                        },
                        "raw_export_download": {
                            "status": "downloaded",
                            "local_path": str(document_path),
                        },
                    },
                    reply_to_message_id=None,
                    thread_id=None,
                    forward_metadata_json=None,
                    raw_metadata_json={},
                )
            ],
        )

    main(
        [
            "--database-path",
            str(db_path),
            "analyze",
            "telegram-artifacts",
            "--raw-export-run-id",
            export.run_id,
            "--processed-root",
            str(tmp_path / "processed"),
            "--no-external-pages",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert output["raw_export_run_id"] == export.run_id
    assert output["metrics"]["candidate_documents"] == 1
    assert output["metrics"]["rows_with_text"] == 1
    assert output["metrics"]["document_parse_timeout_seconds"] == 600.0
    assert output["metrics"]["external_fetch_timeout_seconds"] == 600.0
    assert Path(output["texts_parquet_path"]).exists()
    assert Path(output["summary_path"]).exists()


def test_cli_analyze_telegram_features_writes_feature_parquet(tmp_path, capsys):
    db_path = tmp_path / "cli.db"
    export = _write_cli_feature_export(db_path, tmp_path)

    main(
        [
            "--database-path",
            str(db_path),
            "analyze",
            "telegram-texts",
            "--raw-export-run-id",
            export.run_id,
            "--processed-root",
            str(tmp_path / "processed"),
        ]
    )
    capsys.readouterr()

    main(
        [
            "--database-path",
            str(db_path),
            "analyze",
            "telegram-features",
            "--raw-export-run-id",
            export.run_id,
            "--processed-root",
            str(tmp_path / "processed"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert output["raw_export_run_id"] == export.run_id
    assert output["metrics"]["total_rows"] == 1
    assert output["metrics"]["rows_with_price"] == 1
    assert Path(output["features_parquet_path"]).exists()
    assert Path(output["summary_path"]).exists()


def test_cli_analyze_telegram_stats_writes_reports(tmp_path, capsys):
    db_path = tmp_path / "cli.db"
    export = _write_cli_feature_export(db_path, tmp_path)

    main(
        [
            "--database-path",
            str(db_path),
            "analyze",
            "telegram-texts",
            "--raw-export-run-id",
            export.run_id,
            "--processed-root",
            str(tmp_path / "processed"),
        ]
    )
    capsys.readouterr()
    main(
        [
            "--database-path",
            str(db_path),
            "analyze",
            "telegram-features",
            "--raw-export-run-id",
            export.run_id,
            "--processed-root",
            str(tmp_path / "processed"),
        ]
    )
    capsys.readouterr()

    main(
        [
            "--database-path",
            str(db_path),
            "analyze",
            "telegram-stats",
            "--raw-export-run-id",
            export.run_id,
            "--enriched-root",
            str(tmp_path / "enriched"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert output["raw_export_run_id"] == export.run_id
    assert output["metrics"]["total_rows"] == 1
    assert Path(output["summary_path"]).exists()
    assert Path(output["ngrams_path"]).exists()
    assert Path(output["entity_candidates_path"]).exists()


def test_cli_analyze_telegram_entities_writes_entity_artifacts(tmp_path, capsys):
    db_path = tmp_path / "cli.db"
    export = _write_cli_feature_export(db_path, tmp_path)

    main(
        [
            "--database-path",
            str(db_path),
            "analyze",
            "telegram-texts",
            "--raw-export-run-id",
            export.run_id,
            "--processed-root",
            str(tmp_path / "processed"),
        ]
    )
    capsys.readouterr()
    main(
        [
            "--database-path",
            str(db_path),
            "analyze",
            "telegram-features",
            "--raw-export-run-id",
            export.run_id,
            "--processed-root",
            str(tmp_path / "processed"),
        ]
    )
    capsys.readouterr()

    main(
        [
            "--database-path",
            str(db_path),
            "analyze",
            "telegram-entities",
            "--raw-export-run-id",
            export.run_id,
            "--enriched-root",
            str(tmp_path / "enriched"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert output["raw_export_run_id"] == export.run_id
    assert output["metrics"]["entity_rows"] >= 1
    assert Path(output["entities_parquet_path"]).exists()
    assert Path(output["entity_groups_path"]).exists()
    assert Path(output["resolution_candidates_path"]).exists()
    assert Path(output["summary_path"]).exists()


def test_cli_analyze_telegram_entity_ranking_writes_ranked_artifacts(tmp_path, capsys):
    db_path = tmp_path / "cli.db"
    export = _write_cli_feature_export(db_path, tmp_path)

    main(
        [
            "--database-path",
            str(db_path),
            "analyze",
            "telegram-texts",
            "--raw-export-run-id",
            export.run_id,
            "--processed-root",
            str(tmp_path / "processed"),
        ]
    )
    capsys.readouterr()
    main(
        [
            "--database-path",
            str(db_path),
            "analyze",
            "telegram-features",
            "--raw-export-run-id",
            export.run_id,
            "--processed-root",
            str(tmp_path / "processed"),
        ]
    )
    capsys.readouterr()
    main(
        [
            "--database-path",
            str(db_path),
            "analyze",
            "telegram-entities",
            "--raw-export-run-id",
            export.run_id,
            "--enriched-root",
            str(tmp_path / "enriched"),
        ]
    )
    capsys.readouterr()

    main(
        [
            "--database-path",
            str(db_path),
            "analyze",
            "telegram-entity-ranking",
            "--raw-export-run-id",
            export.run_id,
            "--enriched-root",
            str(tmp_path / "enriched"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert output["raw_export_run_id"] == export.run_id
    assert output["metrics"]["ranked_entity_rows"] >= 1
    assert Path(output["ranked_entities_parquet_path"]).exists()
    assert Path(output["ranked_entities_json_path"]).exists()
    assert Path(output["noise_report_path"]).exists()
    assert Path(output["summary_path"]).exists()


def test_cli_analyze_telegram_entity_enrichment_updates_registry(tmp_path, capsys):
    db_path = tmp_path / "cli.db"
    export = _write_cli_feature_export(db_path, tmp_path)

    main(
        [
            "--database-path",
            str(db_path),
            "analyze",
            "telegram-texts",
            "--raw-export-run-id",
            export.run_id,
            "--processed-root",
            str(tmp_path / "processed"),
        ]
    )
    capsys.readouterr()
    main(
        [
            "--database-path",
            str(db_path),
            "analyze",
            "telegram-features",
            "--raw-export-run-id",
            export.run_id,
            "--processed-root",
            str(tmp_path / "processed"),
        ]
    )
    capsys.readouterr()
    main(
        [
            "--database-path",
            str(db_path),
            "analyze",
            "telegram-entities",
            "--raw-export-run-id",
            export.run_id,
            "--enriched-root",
            str(tmp_path / "enriched"),
        ]
    )
    capsys.readouterr()
    main(
        [
            "--database-path",
            str(db_path),
            "analyze",
            "telegram-entity-ranking",
            "--raw-export-run-id",
            export.run_id,
            "--enriched-root",
            str(tmp_path / "enriched"),
        ]
    )
    capsys.readouterr()
    with create_session_factory(create_sqlite_engine(db_path))() as session:
        run = (
            session.execute(
                select(telegram_raw_export_runs_table).where(
                    telegram_raw_export_runs_table.c.id == export.run_id
                )
            )
            .mappings()
            .one()
        )
        ranked_path = Path(run["metadata_json"]["entity_ranking"]["ranked_entities_parquet_path"])
        ranked_table = pq.read_table(ranked_path)
        rows = ranked_table.to_pylist()
        rows[0]["score"] = 0.5
        rows[0]["ranking_status"] = "review_candidate"
        pq.write_table(pa.Table.from_pylist(rows, schema=ranked_table.schema), ranked_path)

    main(
        [
            "--database-path",
            str(db_path),
            "analyze",
            "telegram-entity-enrichment",
            "--raw-export-run-id",
            export.run_id,
            "--limit",
            "10",
            "--mode",
            "rule_based",
            "--provider",
            "zai",
            "--model",
            "GLM-5.1",
            "--model-profile",
            "catalog-strong",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert output["raw_export_run_id"] == export.run_id
    assert output["metrics"]["processed_entities"] >= 1
    assert output["provider"] == "zai"
    assert output["model"] == "GLM-5.1"
    with create_session_factory(create_sqlite_engine(db_path))() as session:
        assert session.execute(select(canonical_entities_table)).mappings().first() is not None


def test_cli_analyze_telegram_chroma_indexes_normalized_texts(tmp_path, capsys):
    db_path = tmp_path / "cli.db"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        source = TelegramSourceService(session).create_draft(
            "https://t.me/purmaster",
            added_by="admin",
            purpose="catalog_ingestion",
            start_mode="from_beginning",
        )
        export = TelegramRawExportService(session, raw_root=tmp_path / "raw").write_export(
            source=source,
            resolved_source=ResolvedTelegramSource(
                input_ref="https://t.me/purmaster",
                source_kind="telegram_channel",
                telegram_id="-10042",
                username="purmaster",
                title="ПУР",
            ),
            messages=[
                TelegramMessage(
                    monitored_source_ref="https://t.me/purmaster",
                    telegram_message_id=1,
                    message_date=datetime(2026, 1, 31, 10, 15, 0, tzinfo=UTC),
                    sender_id="channel-1",
                    sender_display="ПУР",
                    text="Умная камера",
                    caption=None,
                    has_media=False,
                    media_metadata_json=None,
                    reply_to_message_id=None,
                    thread_id=None,
                    forward_metadata_json=None,
                    raw_metadata_json={},
                )
            ],
        )
        TelegramTextNormalizationService(
            session,
            processed_root=tmp_path / "processed",
        ).write_texts(export.run_id)

    main(
        [
            "--database-path",
            str(db_path),
            "analyze",
            "telegram-chroma",
            "--raw-export-run-id",
            export.run_id,
            "--chroma-root",
            str(tmp_path / "chroma"),
            "--embedding-profile",
            "local_hashing_v1",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert output["raw_export_run_id"] == export.run_id
    assert output["collection_name"] == "telegram_texts"
    assert output["metrics"]["indexed_documents"] == 1
    assert Path(output["chroma_path"]).exists()
    assert Path(output["summary_path"]).exists()


def test_cli_analyze_telegram_fts_indexes_normalized_texts(tmp_path, capsys):
    db_path = tmp_path / "cli.db"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        source = TelegramSourceService(session).create_draft(
            "https://t.me/purmaster",
            added_by="admin",
            purpose="catalog_ingestion",
            start_mode="from_beginning",
        )
        export = TelegramRawExportService(session, raw_root=tmp_path / "raw").write_export(
            source=source,
            resolved_source=ResolvedTelegramSource(
                input_ref="https://t.me/purmaster",
                source_kind="telegram_channel",
                telegram_id="-10042",
                username="purmaster",
                title="ПУР",
            ),
            messages=[
                TelegramMessage(
                    monitored_source_ref="https://t.me/purmaster",
                    telegram_message_id=1,
                    message_date=datetime(2026, 1, 31, 10, 15, 0, tzinfo=UTC),
                    sender_id="channel-1",
                    sender_display="ПУР",
                    text="Отдаю пылесос",
                    caption=None,
                    has_media=False,
                    media_metadata_json=None,
                    reply_to_message_id=None,
                    thread_id=None,
                    forward_metadata_json=None,
                    raw_metadata_json={},
                )
            ],
        )
        TelegramTextNormalizationService(
            session,
            processed_root=tmp_path / "processed",
        ).write_texts(export.run_id)

    main(
        [
            "--database-path",
            str(db_path),
            "analyze",
            "telegram-fts",
            "--raw-export-run-id",
            export.run_id,
            "--search-root",
            str(tmp_path / "search"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert output["raw_export_run_id"] == export.run_id
    assert output["metrics"]["indexed_documents"] == 1
    assert Path(output["search_db_path"]).exists()
    assert Path(output["summary_path"]).exists()


def test_cli_analyze_telegram_lead_candidates_writes_review_artifacts(tmp_path, capsys):
    db_path = tmp_path / "cli.db"
    export = _write_cli_lead_candidate_export(db_path, tmp_path)
    engine = create_sqlite_engine(db_path)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        TelegramTextNormalizationService(
            session,
            processed_root=tmp_path / "processed",
        ).write_texts(export.run_id)
        TelegramFtsIndexService(session, search_root=tmp_path / "search").write_index(
            export.run_id
        )

    main(
        [
            "--database-path",
            str(db_path),
            "analyze",
            "telegram-lead-candidates",
            "--raw-export-run-id",
            export.run_id,
            "--output-root",
            str(tmp_path / "lead-candidates"),
            "--limit",
            "5",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert output["raw_export_run_id"] == export.run_id
    assert output["metrics"]["candidate_count"] == 1
    assert Path(output["candidates_json_path"]).exists()


def test_cli_analyze_telegram_lead_candidate_llm_writes_arbitration_artifacts(
    tmp_path, capsys, monkeypatch
):
    db_path = tmp_path / "cli.db"
    export = _write_cli_lead_candidate_export(db_path, tmp_path)
    engine = create_sqlite_engine(db_path)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        TelegramTextNormalizationService(
            session,
            processed_root=tmp_path / "processed",
        ).write_texts(export.run_id)
        TelegramFtsIndexService(session, search_root=tmp_path / "search").write_index(
            export.run_id
        )

    main(
        [
            "--database-path",
            str(db_path),
            "analyze",
            "telegram-lead-candidates",
            "--raw-export-run-id",
            export.run_id,
            "--output-root",
            str(tmp_path / "lead-candidates"),
            "--limit",
            "5",
        ]
    )
    capsys.readouterr()

    monkeypatch.setenv("PUR_ZAI_API_KEY", "zai-secret")
    monkeypatch.setattr("pur_leads.cli.ZaiChatCompletionClient", FakeZaiChatCompletionClient)
    FakeZaiChatCompletionClient.instances.clear()
    main(
        [
            "--database-path",
            str(db_path),
            "analyze",
            "telegram-lead-candidate-llm",
            "--raw-export-run-id",
            export.run_id,
            "--output-root",
            str(tmp_path / "arbitration"),
            "--limit",
            "1",
            "--model",
            "GLM-5.1",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert output["raw_export_run_id"] == export.run_id
    assert output["metrics"]["processed_candidates"] == 1
    assert output["metrics"]["lead_count"] == 1
    assert Path(output["arbitration_json_path"]).exists()
    assert Path(output["traces_jsonl_path"]).exists()
    assert FakeZaiChatCompletionClient.instances[0].kwargs["response_format"] == {
        "type": "json_object"
    }


def test_cli_search_telegram_merges_indexes(tmp_path, capsys):
    db_path = tmp_path / "cli.db"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        source = TelegramSourceService(session).create_draft(
            "https://t.me/purmaster",
            added_by="admin",
            purpose="catalog_ingestion",
            start_mode="from_beginning",
        )
        export = TelegramRawExportService(session, raw_root=tmp_path / "raw").write_export(
            source=source,
            resolved_source=ResolvedTelegramSource(
                input_ref="https://t.me/purmaster",
                source_kind="telegram_channel",
                telegram_id="-10042",
                username="purmaster",
                title="ПУР",
            ),
            messages=[
                TelegramMessage(
                    monitored_source_ref="https://t.me/purmaster",
                    telegram_message_id=1,
                    message_date=datetime(2026, 1, 31, 10, 15, 0, tzinfo=UTC),
                    sender_id="channel-1",
                    sender_display="ПУР",
                    text="Ищу камеру для дома",
                    caption=None,
                    has_media=False,
                    media_metadata_json=None,
                    reply_to_message_id=None,
                    thread_id=None,
                    forward_metadata_json=None,
                    raw_metadata_json={},
                ),
                TelegramMessage(
                    monitored_source_ref="https://t.me/purmaster",
                    telegram_message_id=2,
                    message_date=datetime(2026, 1, 31, 10, 16, 0, tzinfo=UTC),
                    sender_id="channel-1",
                    sender_display="ПУР",
                    text="Dahua Hero A1 Wi-Fi камера подходит",
                    caption=None,
                    has_media=False,
                    media_metadata_json=None,
                    reply_to_message_id=1,
                    thread_id=None,
                    forward_metadata_json=None,
                    raw_metadata_json={},
                ),
            ],
        )
        TelegramTextNormalizationService(
            session,
            processed_root=tmp_path / "processed",
        ).write_texts(export.run_id)
        TelegramFtsIndexService(session, search_root=tmp_path / "search").write_index(export.run_id)
        TelegramChromaIndexService(session, chroma_root=tmp_path / "chroma").write_index(
            export.run_id,
            embedding_profile="local_hashing_v1",
        )

    main(
        [
            "--database-path",
            str(db_path),
            "search",
            "telegram",
            "--raw-export-run-id",
            export.run_id,
            "--query",
            "dahua камера",
            "--search-root",
            str(tmp_path / "search"),
            "--chroma-root",
            str(tmp_path / "chroma"),
            "--embedding-profile",
            "local_hashing_v1",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert output["query_text"] == "dahua камера"
    assert output["results"][0]["message_url"].startswith("https://t.me/purmaster/")
    assert output["groups"][0]["thread_key"] == "1"
    assert output["rag_context"][0]["citation"] == "[1]"
    assert output["metrics"]["merged_results"] == len(output["results"])


def test_cli_ai_model_concurrency_limiter_uses_registry_limits_without_override(tmp_path):
    db_path = tmp_path / "cli.db"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        AiRegistryService(session).bootstrap_defaults(actor="test")
        flash = (
            session.execute(
                select(ai_models_table).where(
                    ai_models_table.c.normalized_model_name == "glm-4.5-flash"
                )
            )
            .mappings()
            .one()
        )
        session.execute(
            ai_model_limits_table.update()
            .where(
                ai_model_limits_table.c.ai_model_id == flash["id"],
                ai_model_limits_table.c.limit_scope == "concurrency",
            )
            .values(raw_limit=7, effective_limit=5)
        )
        session.commit()

        limiter = _build_ai_model_concurrency_limiter(session, worker_name="test-worker")

        assert limiter is not None
        assert limiter.raw_limit_for_model("GLM-4.5-Flash") == 7
        assert limiter.effective_limit_for_model("GLM-4.5-Flash") == 5


def test_cli_worker_once_reports_noop(tmp_path, capsys):
    db_path = tmp_path / "cli.db"
    main(["--database-path", str(db_path), "db", "upgrade"])

    main(["--database-path", str(db_path), "worker", "once"])

    output = capsys.readouterr().out
    assert "no queued jobs" in output


def test_cli_worker_once_upgrades_database_before_running(tmp_path, capsys):
    db_path = tmp_path / "cli.db"

    main(["--database-path", str(db_path), "worker", "once"])

    tables = set(inspect(create_sqlite_engine(db_path)).get_table_names())
    output = capsys.readouterr().out
    assert "settings" in tables
    assert "no queued jobs" in output


@pytest.mark.asyncio
async def test_cli_worker_run_loop_rereads_configured_concurrency_between_batches(monkeypatch):
    class Args:
        concurrency = None
        max_iterations = 2
        poll_interval_seconds = 0

    calls: list[str] = []
    concurrency_values = [1, 2]

    def fake_worker_concurrency(_args):
        return concurrency_values.pop(0) if concurrency_values else 2

    async def fake_worker_run_once(_args, *, worker_name: str):
        calls.append(worker_name)
        return cli.WorkerRunResult(status="idle")

    monkeypatch.setattr(cli, "_worker_concurrency", fake_worker_concurrency)
    monkeypatch.setattr(cli, "_worker_run_once", fake_worker_run_once)

    iterations = await cli._worker_run_loop(Args())

    assert iterations == 3
    assert calls == ["cli-worker-1", "cli-worker-1", "cli-worker-2"]


def test_cli_worker_once_does_not_seed_ai_registry_on_empty_database(tmp_path, capsys):
    db_path = tmp_path / "cli.db"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)

    main(["--database-path", str(db_path), "worker", "once"])

    with create_session_factory(engine)() as session:
        counts = {
            "providers": session.scalar(select(func.count()).select_from(ai_providers_table)),
            "provider_accounts": session.scalar(
                select(func.count()).select_from(ai_provider_accounts_table)
            ),
            "models": session.scalar(select(func.count()).select_from(ai_models_table)),
            "model_profiles": session.scalar(
                select(func.count()).select_from(ai_model_profiles_table)
            ),
            "model_limits": session.scalar(select(func.count()).select_from(ai_model_limits_table)),
            "agents": session.scalar(select(func.count()).select_from(ai_agents_table)),
            "routes": session.scalar(select(func.count()).select_from(ai_agent_routes_table)),
        }
    output = capsys.readouterr().out
    assert "no queued jobs" in output
    assert counts == {
        "providers": 0,
        "provider_accounts": 0,
        "models": 0,
        "model_profiles": 0,
        "model_limits": 0,
        "agents": 0,
        "routes": 0,
    }


def test_cli_worker_once_uses_canonical_handler_registry(tmp_path, capsys):
    db_path = tmp_path / "cli.db"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        job = SchedulerService(session).enqueue(
            job_type="classify_message_batch",
            scope_type="telegram_source",
        )

    main(["--database-path", str(db_path), "worker", "once"])

    with session_factory() as session:
        stored = SchedulerService(session).repository.get(job.id)
        events = session.execute(select(operational_events_table)).mappings().all()
    output = capsys.readouterr().out
    assert stored is not None
    assert "succeeded job" in output
    assert stored.result_summary_json == {
        "message_count": 0,
        "event_count": 0,
        "cluster_count": 0,
    }
    assert events == []


def test_cli_worker_once_uses_builtin_fuzzy_classifier(tmp_path, capsys):
    db_path = tmp_path / "cli.db"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        source_id = _insert_monitored_source(session)
        message_id = _insert_source_message(
            session,
            source_id,
            text="Нужна камера на дачу",
        )
        _insert_candidate(session, canonical_name="Видеонаблюдение", terms=["камера"])
        job = SchedulerService(session).enqueue(
            job_type="classify_message_batch",
            scope_type="telegram_source",
            monitored_source_id=source_id,
            payload_json={"limit": 10},
        )

    main(["--database-path", str(db_path), "worker", "once"])

    with session_factory() as session:
        stored = SchedulerService(session).repository.get(job.id)
        message_status = session.execute(
            select(source_messages_table.c.classification_status).where(
                source_messages_table.c.id == message_id
            )
        ).scalar_one()
        event = session.execute(select(lead_events_table)).mappings().one()
        cluster = session.execute(select(lead_clusters_table)).mappings().one()
    output = capsys.readouterr().out
    assert stored is not None
    assert "succeeded job" in output
    assert stored.result_summary_json == {
        "message_count": 1,
        "event_count": 1,
        "cluster_count": 1,
    }
    assert message_status == "classified"
    assert event["source_message_id"] == message_id
    assert event["decision"] == "lead"
    assert cluster["primary_source_message_id"] == message_id


def test_cli_worker_once_routes_telegram_jobs_through_canonical_registry(tmp_path, capsys):
    db_path = tmp_path / "cli.db"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        source = TelegramSourceService(session).create_draft("@example", added_by="admin")
        job = SchedulerService(session).enqueue(
            job_type="check_source_access",
            scope_type="telegram_source",
            monitored_source_id=source.id,
        )

    main(["--database-path", str(db_path), "worker", "once"])

    with session_factory() as session:
        stored = SchedulerService(session).repository.get(job.id)
        event = session.execute(select(operational_events_table)).mappings().one()
    output = capsys.readouterr().out
    assert stored is not None
    assert "failed job" in output
    assert stored.last_error == "telegram client is not configured"
    assert event["details_json"]["reason"] == "handler_exception"


def test_cli_worker_once_uses_builtin_pdf_parser(tmp_path, capsys, monkeypatch):
    db_path = tmp_path / "cli.db"
    pdf_path = tmp_path / "catalog.pdf"
    pdf_path.write_bytes(b"%PDF fake")
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        raw_source = CatalogSourceService(session).upsert_source(
            source_type="telegram_message",
            origin="telegram:purmaster",
            external_id="42",
            raw_text="catalog",
        )
        artifact = CatalogSourceService(session).record_artifact(
            raw_source.id,
            artifact_type="document",
            file_name="catalog.pdf",
            mime_type="application/pdf",
            local_path=str(pdf_path),
            download_status="downloaded",
        )
        job = SchedulerService(session).enqueue(
            job_type="parse_artifact",
            scope_type="parser",
            payload_json={
                "source_id": raw_source.id,
                "artifact_id": artifact.id,
                "local_path": str(pdf_path),
            },
        )

    monkeypatch.setattr("pur_leads.cli.PdfArtifactParser", FakePdfArtifactParser)

    main(["--database-path", str(db_path), "worker", "once"])

    with session_factory() as session:
        stored = SchedulerService(session).repository.get(job.id)
        chunks = session.execute(select(parsed_chunks_table)).mappings().all()
    output = capsys.readouterr().out
    assert stored is not None
    assert "succeeded job" in output
    assert stored.result_summary_json == {"chunk_count": 1, "parser_name": "fake-pdf"}
    assert [chunk["text"] for chunk in chunks] == ["parsed pdf"]


def test_cli_worker_once_uses_builtin_heuristic_extractor(tmp_path, capsys):
    db_path = tmp_path / "cli.db"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        raw_source = CatalogSourceService(session).upsert_source(
            source_type="telegram_message",
            origin="telegram:purmaster",
            external_id="17",
            raw_text="catalog",
        )
        chunk = CatalogSourceService(session).replace_parsed_chunks(
            raw_source.id,
            chunks=[
                """
                1.1 Управление освещением
                Установка управляемых выключателей
                Включение света голосом и по расписанию.
                """
            ],
            parser_name="test",
            parser_version="1",
        )[0]
        job = SchedulerService(session).enqueue(
            job_type="extract_catalog_facts",
            scope_type="parser",
            payload_json={"source_id": raw_source.id, "chunk_id": chunk.id},
        )

    main(["--database-path", str(db_path), "worker", "once"])

    with session_factory() as session:
        stored = SchedulerService(session).repository.get(job.id)
        candidate = session.execute(select(catalog_candidates_table)).mappings().one()
    output = capsys.readouterr().out
    assert stored is not None
    assert "succeeded job" in output
    assert stored.result_summary_json == {"fact_count": 1, "candidate_count": 1}
    assert candidate["candidate_type"] == "item"
    assert candidate["canonical_name"] == "Управление освещением"


def test_cli_worker_once_uses_configured_zai_llm_extractor(tmp_path, capsys, monkeypatch):
    db_path = tmp_path / "cli.db"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        raw_source = CatalogSourceService(session).upsert_source(
            source_type="telegram_message",
            origin="telegram:purmaster",
            external_id="18",
            raw_text="Dahua Hero A1 Wi-Fi camera",
        )
        chunk = CatalogSourceService(session).replace_parsed_chunks(
            raw_source.id,
            chunks=["Dahua Hero A1 Wi-Fi camera"],
            parser_name="test",
            parser_version="1",
        )[0]
        job = SchedulerService(session).enqueue(
            job_type="extract_catalog_facts",
            scope_type="parser",
            payload_json={"source_id": raw_source.id, "chunk_id": chunk.id},
        )

    monkeypatch.setenv("PUR_ZAI_API_KEY", "test-key")
    monkeypatch.setenv("PUR_CATALOG_LLM_MODEL", "glm-4.7")
    monkeypatch.setattr("pur_leads.cli.ZaiChatCompletionClient", FakeZaiChatCompletionClient)
    FakeZaiChatCompletionClient.instances.clear()

    main(["--database-path", str(db_path), "worker", "once"])

    with session_factory() as session:
        stored = SchedulerService(session).repository.get(job.id)
        candidate = session.execute(select(catalog_candidates_table)).mappings().one()
        run = session.execute(select(extraction_runs_table)).mappings().one()
    output = capsys.readouterr().out
    assert stored is not None
    assert "succeeded job" in output
    assert stored.result_summary_json == {"fact_count": 1, "candidate_count": 1}
    assert candidate["canonical_name"] == "Dahua Hero A1"
    assert candidate["normalized_value_json"]["terms"] == ["hero a1", "dahua hero"]
    assert run["extractor_version"] == "pur-llm-catalog-v1"
    assert run["model"] == "glm-4.7"
    assert FakeZaiChatCompletionClient.instances[0].base_url == (
        "https://api.z.ai/api/coding/paas/v4"
    )


def test_cli_worker_once_uses_ai_registry_catalog_route_after_explicit_bootstrap(
    tmp_path,
    capsys,
    monkeypatch,
):
    db_path = tmp_path / "cli.db"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        registry = AiRegistryService(session)
        registry.bootstrap_defaults(actor="test")
        legacy_secret_id = SecretRefService(session).create_local_secret(
            secret_type="ai_api_key",
            display_name="Legacy Z.AI",
            value="legacy-global-key",
            storage_root=tmp_path / "secrets",
        )
        account_secret_id = SecretRefService(session).create_local_secret(
            secret_type="ai_api_key",
            display_name="Catalog Z.AI",
            value="route-account-key",
            storage_root=tmp_path / "secrets",
        )
        SettingsService(session).set(
            "zai_api_key_secret_ref",
            {"secret_ref_id": legacy_secret_id},
            value_type="secret_ref",
            updated_by="test",
        )
        registry.configure_zai_account(
            actor="test",
            base_url="https://api.z.ai/api/coding/paas/v4",
            auth_secret_ref=f"secret_ref:{account_secret_id}",
            display_name="Catalog Z.AI",
        )
        raw_source = CatalogSourceService(session).upsert_source(
            source_type="telegram_message",
            origin="telegram:purmaster",
            external_id="18",
            raw_text="Dahua Hero A1 Wi-Fi camera",
        )
        chunk = CatalogSourceService(session).replace_parsed_chunks(
            raw_source.id,
            chunks=["Dahua Hero A1 Wi-Fi camera"],
            parser_name="test",
            parser_version="1",
        )[0]
        job = SchedulerService(session).enqueue(
            job_type="extract_catalog_facts",
            scope_type="parser",
            payload_json={"source_id": raw_source.id, "chunk_id": chunk.id},
        )

    monkeypatch.setattr("pur_leads.cli.ZaiChatCompletionClient", FakeZaiChatCompletionClient)
    FakeZaiChatCompletionClient.instances.clear()

    main(["--database-path", str(db_path), "worker", "once"])

    with session_factory() as session:
        stored = SchedulerService(session).repository.get(job.id)
        run = session.execute(select(extraction_runs_table)).mappings().one()
    output = capsys.readouterr().out
    assert stored is not None
    assert "succeeded job" in output
    assert run["model"] == "GLM-4-Plus"
    called_instances = [
        instance
        for instance in FakeZaiChatCompletionClient.instances
        if instance.calls and instance.calls[0]["model"] == "GLM-4-Plus"
    ]
    assert called_instances[0].api_key == "route-account-key"


def test_cli_catalog_route_ignores_legacy_model_setting_when_registry_route_exists(
    tmp_path,
    capsys,
    monkeypatch,
):
    db_path = tmp_path / "cli.db"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        registry = AiRegistryService(session)
        registry.bootstrap_defaults(actor="test")
        account_secret_id = SecretRefService(session).create_local_secret(
            secret_type="ai_api_key",
            display_name="Catalog Z.AI",
            value="route-account-key",
            storage_root=tmp_path / "secrets",
        )
        SettingsService(session).set(
            "catalog_llm_model",
            "GLM-4.5-Flash",
            value_type="string",
            updated_by="test",
        )
        registry.configure_zai_account(
            actor="test",
            base_url="https://api.z.ai/api/coding/paas/v4",
            auth_secret_ref=f"secret_ref:{account_secret_id}",
            display_name="Catalog Z.AI",
        )
        raw_source = CatalogSourceService(session).upsert_source(
            source_type="telegram_message",
            origin="telegram:purmaster",
            external_id="18",
            raw_text="Dahua Hero A1 Wi-Fi camera",
        )
        chunk = CatalogSourceService(session).replace_parsed_chunks(
            raw_source.id,
            chunks=["Dahua Hero A1 Wi-Fi camera"],
            parser_name="test",
            parser_version="1",
        )[0]
        job = SchedulerService(session).enqueue(
            job_type="extract_catalog_facts",
            scope_type="parser",
            payload_json={"source_id": raw_source.id, "chunk_id": chunk.id},
        )

    monkeypatch.setattr("pur_leads.cli.ZaiChatCompletionClient", FakeZaiChatCompletionClient)
    FakeZaiChatCompletionClient.instances.clear()

    main(["--database-path", str(db_path), "worker", "once"])

    with session_factory() as session:
        stored = SchedulerService(session).repository.get(job.id)
        run = session.execute(select(extraction_runs_table)).mappings().one()
    output = capsys.readouterr().out
    assert stored is not None
    assert "succeeded job" in output
    assert run["model"] == "GLM-4-Plus"
    called_models = [
        call["model"]
        for instance in FakeZaiChatCompletionClient.instances
        for call in instance.calls
    ]
    assert called_models == ["GLM-4-Plus"]
    called_instance = next(
        instance for instance in FakeZaiChatCompletionClient.instances if instance.calls
    )
    assert called_instance.timeout_seconds == 90.0
    assert called_instance.kwargs["connect_timeout_seconds"] == 5.0


def test_cli_catalog_extractor_uses_fallback_route_after_rate_limit(
    tmp_path,
    capsys,
    monkeypatch,
):
    db_path = tmp_path / "cli.db"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        registry = AiRegistryService(session)
        registry.bootstrap_defaults(actor="test")
        account_secret_id = SecretRefService(session).create_local_secret(
            secret_type="ai_api_key",
            display_name="Catalog Z.AI",
            value="route-account-key",
            storage_root=tmp_path / "secrets",
        )
        registry.configure_zai_account(
            actor="test",
            base_url="https://api.z.ai/api/coding/paas/v4",
            auth_secret_ref=f"secret_ref:{account_secret_id}",
            display_name="Catalog Z.AI",
        )
        raw_source = CatalogSourceService(session).upsert_source(
            source_type="telegram_message",
            origin="telegram:purmaster",
            external_id="18",
            raw_text="Dahua Hero A1 Wi-Fi camera",
        )
        chunk = CatalogSourceService(session).replace_parsed_chunks(
            raw_source.id,
            chunks=["Dahua Hero A1 Wi-Fi camera"],
            parser_name="test",
            parser_version="1",
        )[0]
        job = SchedulerService(session).enqueue(
            job_type="extract_catalog_facts",
            scope_type="parser",
            payload_json={"source_id": raw_source.id, "chunk_id": chunk.id},
        )

    monkeypatch.setattr("pur_leads.cli.ZaiChatCompletionClient", RateLimitThenFallbackZaiClient)
    RateLimitThenFallbackZaiClient.calls.clear()

    main(["--database-path", str(db_path), "worker", "once"])

    with session_factory() as session:
        stored = SchedulerService(session).repository.get(job.id)
        run = session.execute(select(extraction_runs_table)).mappings().one()
    output = capsys.readouterr().out
    assert stored is not None
    assert "succeeded job" in output
    assert stored.status == "succeeded"
    assert run["model"] == "GLM-4-Plus"
    assert [call["model"] for call in RateLimitThenFallbackZaiClient.calls] == [
        "GLM-4-Plus",
        "GLM-4.5-Air",
    ]


def test_cli_catalog_extractor_uses_fallback_route_after_read_timeout(
    tmp_path,
    capsys,
    monkeypatch,
):
    db_path = tmp_path / "cli.db"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        registry = AiRegistryService(session)
        registry.bootstrap_defaults(actor="test")
        account_secret_id = SecretRefService(session).create_local_secret(
            secret_type="ai_api_key",
            display_name="Catalog Z.AI",
            value="route-account-key",
            storage_root=tmp_path / "secrets",
        )
        registry.configure_zai_account(
            actor="test",
            base_url="https://api.z.ai/api/coding/paas/v4",
            auth_secret_ref=f"secret_ref:{account_secret_id}",
            display_name="Catalog Z.AI",
        )
        raw_source = CatalogSourceService(session).upsert_source(
            source_type="telegram_message",
            origin="telegram:purmaster",
            external_id="18",
            raw_text="Dahua Hero A1 Wi-Fi camera",
        )
        chunk = CatalogSourceService(session).replace_parsed_chunks(
            raw_source.id,
            chunks=["Dahua Hero A1 Wi-Fi camera"],
            parser_name="test",
            parser_version="1",
        )[0]
        job = SchedulerService(session).enqueue(
            job_type="extract_catalog_facts",
            scope_type="parser",
            payload_json={"source_id": raw_source.id, "chunk_id": chunk.id},
        )

    monkeypatch.setattr("pur_leads.cli.ZaiChatCompletionClient", ReadTimeoutThenFallbackZaiClient)
    ReadTimeoutThenFallbackZaiClient.calls.clear()

    main(["--database-path", str(db_path), "worker", "once"])

    with session_factory() as session:
        stored = SchedulerService(session).repository.get(job.id)
        run = session.execute(select(extraction_runs_table)).mappings().one()
    output = capsys.readouterr().out
    assert stored is not None
    assert "succeeded job" in output
    assert stored.status == "succeeded"
    assert run["model"] == "GLM-4-Plus"
    assert [call["model"] for call in ReadTimeoutThenFallbackZaiClient.calls] == [
        "GLM-4-Plus",
        "GLM-4.5-Air",
    ]


def test_cli_worker_once_uses_configured_zai_lead_shadow_classifier(
    tmp_path,
    capsys,
    monkeypatch,
):
    db_path = tmp_path / "cli.db"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        source_id = _insert_monitored_source(session)
        message_id = _insert_source_message(
            session,
            source_id,
            text="Ищу камеру Dahua для дома",
        )
        _insert_candidate(session, canonical_name="Видеонаблюдение", terms=["камера"])
        SettingsService(session).set(
            "catalog_llm_extraction_enabled",
            False,
            value_type="bool",
            updated_by="test",
        )
        SettingsService(session).set(
            "lead_llm_shadow_enabled",
            True,
            value_type="bool",
            updated_by="test",
        )
        SettingsService(session).set(
            "lead_llm_shadow_model",
            "glm-4.5-flash",
            value_type="string",
            updated_by="test",
        )
        job = SchedulerService(session).enqueue(
            job_type="classify_message_batch",
            scope_type="telegram_source",
            monitored_source_id=source_id,
            payload_json={"limit": 10},
        )

    monkeypatch.setenv("PUR_ZAI_API_KEY", "test-key")
    monkeypatch.setattr("pur_leads.cli.ZaiChatCompletionClient", FakeZaiChatCompletionClient)
    FakeZaiChatCompletionClient.instances.clear()

    main(["--database-path", str(db_path), "worker", "once"])

    with session_factory() as session:
        stored = SchedulerService(session).repository.get(job.id)
        shadow = (
            session.execute(
                select(decision_records_table).where(
                    decision_records_table.c.decision_type == "lead_detection_shadow"
                )
            )
            .mappings()
            .one()
        )
    output = capsys.readouterr().out
    assert stored is not None
    assert "succeeded job" in output
    assert stored.result_summary_json == {
        "message_count": 1,
        "event_count": 1,
        "cluster_count": 1,
        "shadow_decision_count": 1,
    }
    assert shadow["source_message_id"] == message_id
    assert shadow["model"] == "glm-4.5-flash"
    assert shadow["decision"] == "lead"
    assert FakeZaiChatCompletionClient.instances[0].calls[0]["model"] == "glm-4.5-flash"


def test_cli_worker_once_uses_configured_telethon_client(tmp_path, capsys, monkeypatch):
    db_path = tmp_path / "cli.db"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        userbot = UserbotAccountService(session).create_account(
            display_name="Main userbot",
            session_name="main",
            session_path="/app/sessions/userbot.session",
            actor="admin",
        )
        source = TelegramSourceService(session).create_draft("@example", added_by="admin")
        job = SchedulerService(session).enqueue(
            job_type="check_source_access",
            scope_type="telegram_source",
            monitored_source_id=source.id,
            userbot_account_id=userbot.id,
        )

    monkeypatch.setenv("TELEGRAM_API_ID", "123")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
    monkeypatch.setattr(
        "pur_leads.cli.TelethonTelegramClient",
        FakeConfiguredTelegramClient,
        raising=False,
    )
    FakeConfiguredTelegramClient.instances.clear()

    main(["--database-path", str(db_path), "worker", "once"])

    with session_factory() as session:
        stored = SchedulerService(session).repository.get(job.id)
        check = session.execute(select(source_access_checks_table)).mappings().one()
    output = capsys.readouterr().out
    assert stored is not None
    assert "succeeded job" in output
    assert stored.status == "succeeded"
    assert check["status"] == "succeeded"
    assert FakeConfiguredTelegramClient.instances[0].session_path == "/app/sessions/userbot.session"
    assert FakeConfiguredTelegramClient.instances[0].api_id == 123
    assert FakeConfiguredTelegramClient.instances[0].api_hash == "hash"
    assert FakeConfiguredTelegramClient.instances[0].close_count == 1


def test_cli_worker_run_supports_bounded_polling_loop(tmp_path, capsys):
    db_path = tmp_path / "cli.db"
    main(["--database-path", str(db_path), "db", "upgrade"])

    main(
        [
            "--database-path",
            str(db_path),
            "worker",
            "run",
            "--poll-interval-seconds",
            "0",
            "--max-iterations",
            "2",
        ]
    )

    output = capsys.readouterr().out
    assert "worker stopped after 2 iterations" in output


def test_cli_worker_run_supports_concurrent_bounded_polling_loop(tmp_path, capsys):
    db_path = tmp_path / "cli.db"
    main(["--database-path", str(db_path), "db", "upgrade"])

    main(
        [
            "--database-path",
            str(db_path),
            "worker",
            "run",
            "--poll-interval-seconds",
            "0",
            "--max-iterations",
            "1",
            "--concurrency",
            "2",
        ]
    )

    output = capsys.readouterr().out
    assert "worker stopped after 2 iterations" in output


def test_cli_web_uses_database_path_and_bootstrap_env(tmp_path, monkeypatch):
    db_path = tmp_path / "cli.db"
    main(["--database-path", str(db_path), "db", "upgrade"])
    captured = {}

    def fake_run(app, *, host, port):
        captured["app"] = app
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setenv("PUR_BOOTSTRAP_ADMIN_USERNAME", "operator")
    monkeypatch.setenv("PUR_BOOTSTRAP_ADMIN_PASSWORD", "initial-secret")
    monkeypatch.setenv("PUR_TELEGRAM_BOT_TOKEN", "telegram-token")
    monkeypatch.setattr("uvicorn.run", fake_run)

    main(["--database-path", str(db_path), "web"])

    client = TestClient(captured["app"])
    login_response = client.post(
        "/api/auth/local",
        json={"username": "operator", "password": "initial-secret"},
    )
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8000
    assert login_response.status_code == 200


def _write_cli_feature_export(db_path: Path, tmp_path: Path):
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        source = TelegramSourceService(session).create_draft(
            "https://t.me/purmaster",
            added_by="admin",
            purpose="catalog_ingestion",
            start_mode="from_beginning",
        )
        return TelegramRawExportService(session, raw_root=tmp_path / "raw").write_export(
            source=source,
            resolved_source=ResolvedTelegramSource(
                input_ref="https://t.me/purmaster",
                source_kind="telegram_channel",
                telegram_id="-10042",
                username="purmaster",
                title="ПУР",
            ),
            messages=[
                TelegramMessage(
                    monitored_source_ref="https://t.me/purmaster",
                    telegram_message_id=1,
                    message_date=datetime(2026, 1, 31, 10, 15, 0, tzinfo=UTC),
                    sender_id="channel-1",
                    sender_display="ПУР",
                    text="Камера Dahua Hero A1 стоит 10000р",
                    caption=None,
                    has_media=False,
                    media_metadata_json=None,
                    reply_to_message_id=None,
                    thread_id=None,
                    forward_metadata_json=None,
                    raw_metadata_json={},
                )
            ],
        )


def _write_cli_lead_candidate_export(db_path: Path, tmp_path: Path):
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        source = TelegramSourceService(session).create_draft(
            "https://t.me/chat_mila_kolpakova",
            added_by="admin",
            purpose="lead_monitoring",
            start_mode="from_beginning",
        )
        return TelegramRawExportService(session, raw_root=tmp_path / "raw").write_export(
            source=source,
            resolved_source=ResolvedTelegramSource(
                input_ref="https://t.me/chat_mila_kolpakova",
                source_kind="telegram_supergroup",
                telegram_id="-10042",
                username="chat_mila_kolpakova",
                title="Чат лидов",
            ),
            messages=[
                TelegramMessage(
                    monitored_source_ref="https://t.me/chat_mila_kolpakova",
                    telegram_message_id=1,
                    message_date=datetime(2026, 1, 31, 10, 15, 0, tzinfo=UTC),
                    sender_id="user-1",
                    sender_display="Анна",
                    text="Нужна камера Dahua для квартиры",
                    caption=None,
                    has_media=False,
                    media_metadata_json=None,
                    reply_to_message_id=None,
                    thread_id=None,
                    forward_metadata_json=None,
                    raw_metadata_json={},
                ),
                TelegramMessage(
                    monitored_source_ref="https://t.me/chat_mila_kolpakova",
                    telegram_message_id=2,
                    message_date=datetime(2026, 1, 31, 10, 16, 0, tzinfo=UTC),
                    sender_id="user-2",
                    sender_display="Олег",
                    text="Камерный дом и спокойный двор",
                    caption=None,
                    has_media=False,
                    media_metadata_json=None,
                    reply_to_message_id=None,
                    thread_id=None,
                    forward_metadata_json=None,
                    raw_metadata_json={},
                ),
            ],
        )


def _write_cli_desktop_archive(tmp_path: Path) -> Path:
    archive_path = tmp_path / "ChatExport.zip"
    payload = {
        "name": "Чат лидов",
        "type": "public_supergroup",
        "id": 1292716582,
        "messages": [
            {
                "id": 101,
                "type": "message",
                "date": "2026-04-30T13:00:00",
                "date_unixtime": "1777543200",
                "from": "Анна",
                "from_id": "user1",
                "text": "Нужна камера Dahua",
                "text_entities": [],
            }
        ],
    }
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "ChatExport_2026-04-30/result.json",
            json.dumps(payload, ensure_ascii=False),
        )
    return archive_path


def _insert_monitored_source(session) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(monitored_sources_table).values(
            id=row_id,
            source_kind="telegram_supergroup",
            input_ref="@test",
            source_purpose="lead_monitoring",
            priority="normal",
            status="active",
            lead_detection_enabled=True,
            catalog_ingestion_enabled=False,
            phase_enabled=True,
            start_mode="from_now",
            historical_backfill_policy="retro_web_only",
            poll_interval_seconds=60,
            added_by="test",
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    return row_id


def _insert_source_message(session, source_id: str, *, text: str) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(source_messages_table).values(
            id=row_id,
            monitored_source_id=source_id,
            raw_source_id=None,
            telegram_message_id=101,
            sender_id="sender-1",
            message_date=datetime(2026, 4, 28, 12, 0, tzinfo=UTC),
            text=text,
            caption=None,
            normalized_text=text.casefold(),
            has_media=False,
            media_metadata_json=None,
            reply_to_message_id=None,
            thread_id=None,
            forward_metadata_json=None,
            raw_metadata_json={},
            fetched_at=now,
            classification_status="queued",
            archive_pointer_id=None,
            is_archived_stub=False,
            text_archived=False,
            caption_archived=False,
            metadata_archived=False,
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    return row_id


def _insert_candidate(session, *, canonical_name: str, terms: list[str]) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(catalog_candidates_table).values(
            id=row_id,
            candidate_type="item",
            proposed_action="create",
            canonical_name=canonical_name,
            normalized_value_json={
                "item_type": "service",
                "category_slug": "video_surveillance",
                "terms": terms,
            },
            source_count=1,
            evidence_count=1,
            confidence=0.8,
            status="auto_pending",
            target_entity_type=None,
            target_entity_id=None,
            merge_target_candidate_id=None,
            first_seen_at=now,
            last_seen_at=now,
            created_by="system",
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    return row_id


class FakeConfiguredTelegramClient:
    instances: list["FakeConfiguredTelegramClient"] = []

    def __init__(self, *, session_path, api_id, api_hash, **_kwargs) -> None:
        self.session_path = session_path
        self.api_id = api_id
        self.api_hash = api_hash
        self.close_count = 0
        self.instances.append(self)

    async def aclose(self) -> None:
        self.close_count += 1

    async def resolve_source(self, input_ref: str) -> ResolvedTelegramSource:
        return ResolvedTelegramSource(
            input_ref=input_ref,
            source_kind="telegram_supergroup",
            telegram_id="-1001",
            username="example",
            title="Example",
        )

    async def check_access(self, source: ResolvedTelegramSource) -> SourceAccessResult:
        return SourceAccessResult(
            status="succeeded",
            can_read_messages=True,
            can_read_history=True,
            resolved_source=source,
            last_message_id=50,
        )

    async def fetch_preview_messages(self, source, *, limit):  # noqa: ANN001, ANN201
        return []

    async def fetch_message_batch(  # noqa: ANN001, ANN201
        self, source, *, after_message_id, after_date=None, limit
    ):
        return []

    async def fetch_context(self, source, *, message_id, before, after, reply_depth):  # noqa: ANN001, ANN201
        raise NotImplementedError

    async def download_message_document(self, source, *, message_id, destination_dir):  # noqa: ANN001, ANN201
        raise NotImplementedError


class FakePdfArtifactParser:
    async def parse_artifact(self, *, source_id: str, artifact_id: str | None, payload: dict):
        return ParsedArtifact(
            source_id=source_id,
            artifact_id=artifact_id,
            chunks=["parsed pdf"],
            parser_name="fake-pdf",
            parser_version="1",
        )


class FakeZaiChatCompletionClient:
    instances: list["FakeZaiChatCompletionClient"] = []

    def __init__(self, *, api_key, base_url, timeout_seconds=60.0, **kwargs) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.kwargs = kwargs
        self.calls: list[dict[str, Any]] = []
        self.instances.append(self)

    async def complete(self, *, messages, model, temperature, max_tokens):  # noqa: ANN001
        self.calls.append(
            {
                "messages": messages,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        if any("operator-assist lead arbitrator" in _message_content(message) for message in messages):
            content = """
            {
              "decision": "lead",
              "confidence": 0.88,
              "need_operator": true,
              "why": "User asks for equipment selection",
              "matched_need": "нужна камера",
              "relevant_catalog_items": [],
              "false_positive_reason": null
            }
            """
        elif any("lead-detection evaluator" in _message_content(message) for message in messages):
            content = """
            {
              "items": [
                {
                  "source_message_id": "PLACEHOLDER",
                  "decision": "lead",
                  "confidence": 0.86,
                  "commercial_value_score": 0.72,
                  "negative_score": 0.02,
                  "reason": "User is looking for a camera",
                  "signals": ["ищу камеру"],
                  "negative_signals": [],
                  "matched_text": ["Ищу камеру"],
                  "notify_reason": "purchase_intent"
                }
              ]
            }
            """
            source_message_id = _source_message_id_from_prompt(messages)
            content = content.replace("PLACEHOLDER", source_message_id)
        else:
            content = """
            {
              "facts": [
                {
                  "fact_type": "product",
                  "canonical_name": "Dahua Hero A1",
                  "category": "video_surveillance",
                  "terms": ["hero a1", "dahua hero"],
                  "evidence_quote": "Dahua Hero A1 Wi-Fi camera",
                  "confidence": 0.92
                }
              ]
            }
            """
        return AiChatCompletion(
            content=content,
            model=model,
            request_id="fake-zai-request",
            usage={"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
            raw_response={},
        )


class RateLimitThenFallbackZaiClient(FakeZaiChatCompletionClient):
    calls: list[dict[str, Any]] = []

    async def complete(self, *, messages, model, temperature, max_tokens):  # noqa: ANN001
        self.calls.append(
            {
                "messages": messages,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        self.__class__.calls.append(self.calls[-1])
        if model == "GLM-4-Plus":
            raise AiProviderError(
                status_code=429,
                error_code="1302",
                message="Rate limit reached for requests",
                retry_after_seconds=60,
            )
        return AiChatCompletion(
            content="""
            {
              "facts": [
                {
                  "fact_type": "product",
                  "canonical_name": "Dahua Hero A1",
                  "category": "video_surveillance",
                  "terms": ["hero a1", "dahua hero"],
                  "evidence_quote": "Dahua Hero A1 Wi-Fi camera",
                  "confidence": 0.92
                }
              ]
            }
            """,
            model=model,
            request_id="fallback-request",
            usage={},
            raw_response={},
        )


class ReadTimeoutThenFallbackZaiClient(FakeZaiChatCompletionClient):
    calls: list[dict[str, Any]] = []

    async def complete(self, *, messages, model, temperature, max_tokens):  # noqa: ANN001
        self.calls.append(
            {
                "messages": messages,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        self.__class__.calls.append(self.calls[-1])
        if model == "GLM-4-Plus":
            raise AiProviderError(
                status_code=None,
                error_code="read_timeout",
                message="ReadTimeout",
                retryable=True,
            )
        return AiChatCompletion(
            content="""
            {
              "facts": [
                {
                  "fact_type": "product",
                  "canonical_name": "Dahua Hero A1",
                  "category": "video_surveillance",
                  "terms": ["hero a1", "dahua hero"],
                  "evidence_quote": "Dahua Hero A1 Wi-Fi camera",
                  "confidence": 0.92
                }
              ]
            }
            """,
            model=model,
            request_id="fallback-request",
            usage={},
            raw_response={},
        )


def _message_content(message) -> str:  # noqa: ANN001
    if hasattr(message, "content"):
        return str(message.content)
    return str(message.get("content", ""))


def _source_message_id_from_prompt(messages) -> str:  # noqa: ANN001
    for message in messages:
        content = _message_content(message)
        marker = '"source_message_id": "'
        if marker in content:
            return content.split(marker, 1)[1].split('"', 1)[0]
    return "unknown"
