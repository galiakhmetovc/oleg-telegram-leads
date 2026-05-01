"""Telegram Stage 3/4/5 feature, aggregate, and entity extraction behavior."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
import json

import pyarrow.parquet as pq
from sqlalchemy import select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.integrations.documents.pdf_parser import PdfArtifactParser
from pur_leads.integrations.telegram.types import ResolvedTelegramSource, TelegramMessage
from pur_leads.models.telegram_sources import telegram_raw_export_runs_table
from pur_leads.services.telegram_aggregated_stats import TelegramAggregatedStatsService
from pur_leads.services.telegram_artifact_texts import TelegramArtifactTextExtractionService
from pur_leads.services.telegram_entity_extraction import TelegramEntityExtractionService
from pur_leads.services.telegram_entity_ranking import TelegramEntityRankingService
from pur_leads.services.telegram_feature_enrichment import TelegramFeatureEnrichmentService
from pur_leads.services.telegram_raw_export import TelegramRawExportService
from pur_leads.services.telegram_sources import TelegramSourceService
from pur_leads.services.telegram_text_normalization import TelegramTextNormalizationService


def test_telegram_feature_enrichment_writes_features_for_messages_and_artifacts(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        export = _prepared_export(session, tmp_path)
        TelegramTextNormalizationService(
            session,
            processed_root=tmp_path / "processed",
        ).write_texts(export.run_id)
        TelegramArtifactTextExtractionService(
            session,
            processed_root=tmp_path / "processed",
            document_parser=PdfArtifactParser(reader_factory=lambda path: FakeReader([])),
            fetch_external_pages=False,
        ).write_texts(export.run_id)

        result = TelegramFeatureEnrichmentService(
            session,
            processed_root=tmp_path / "processed",
        ).write_features(export.run_id)

        assert result.features_parquet_path.exists()
        rows = pq.read_table(result.features_parquet_path).to_pylist()
        assert {row["entity_type"] for row in rows} == {"telegram_message", "telegram_artifact"}
        assert result.metrics["total_rows"] == len(rows)
        assert result.metrics["rows_with_price"] >= 2
        assert result.metrics["feature_profile_status"] == "not_configured"
        assert "domain_category_counts" not in result.metrics

        question = next(row for row in rows if row["telegram_message_id"] == 1)
        assert question["is_question_like"] is True
        assert question["has_price"] is True
        assert question["has_phone"] is True
        assert question["feature_profile_id"] == ""
        assert question["feature_profile_version"] == ""
        assert question["feature_profile_applied"] is False
        assert "domain_categories_json" not in question
        assert "domain_hits_json" not in question
        assert json.loads(question["price_values_json"])[0]["amount"] == 10000

        artifact = next(row for row in rows if row["entity_type"] == "telegram_artifact")
        assert artifact["artifact_kind"] == "document"
        assert artifact["file_name"] == "catalog.txt"
        assert artifact["has_noun_term"] is True
        assert artifact["technical_language_score"] > 0
        assert "domain_categories_json" not in artifact

        run = (
            session.execute(
                select(telegram_raw_export_runs_table).where(
                    telegram_raw_export_runs_table.c.id == export.run_id
                )
            )
            .mappings()
            .one()
        )
        metadata = run["metadata_json"]["feature_enrichment"]
        assert metadata["features_parquet_path"] == str(result.features_parquet_path)
        assert metadata["total_rows"] == len(rows)
        assert metadata["feature_profile_status"] == "not_configured"


def test_telegram_aggregated_stats_writes_reports_from_features(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        export = _prepared_export(session, tmp_path)
        TelegramTextNormalizationService(
            session,
            processed_root=tmp_path / "processed",
        ).write_texts(export.run_id)
        TelegramArtifactTextExtractionService(
            session,
            processed_root=tmp_path / "processed",
            document_parser=PdfArtifactParser(reader_factory=lambda path: FakeReader([])),
            fetch_external_pages=False,
        ).write_texts(export.run_id)
        TelegramFeatureEnrichmentService(
            session,
            processed_root=tmp_path / "processed",
        ).write_features(export.run_id)

        result = TelegramAggregatedStatsService(
            session,
            enriched_root=tmp_path / "enriched",
        ).write_stats(export.run_id)

        assert result.summary_path.exists()
        assert result.ngrams_path.exists()
        assert result.entity_candidates_path.exists()
        assert result.url_summary_path.exists()
        assert result.source_quality_path.exists()
        assert result.metrics["total_rows"] >= 3
        assert "domain_category_counts" not in result.metrics

        ngrams = json.loads(result.ngrams_path.read_text(encoding="utf-8"))
        assert any(item["term"] == "камера" for item in ngrams["top_lemmas"])

        entities = json.loads(result.entity_candidates_path.read_text(encoding="utf-8"))
        assert "price_summary" not in entities
        assert "domain_categories" not in entities
        assert "domain_terms" not in entities

        quality = json.loads(result.source_quality_path.read_text(encoding="utf-8"))
        assert quality["entity_type_counts"]["telegram_artifact"] >= 1


def test_telegram_entity_extraction_writes_pos_entities_and_review_candidates(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        export = _prepared_export(session, tmp_path)
        TelegramTextNormalizationService(
            session,
            processed_root=tmp_path / "processed",
        ).write_texts(export.run_id)
        TelegramArtifactTextExtractionService(
            session,
            processed_root=tmp_path / "processed",
            document_parser=PdfArtifactParser(reader_factory=lambda path: FakeReader([])),
            fetch_external_pages=False,
        ).write_texts(export.run_id)
        TelegramFeatureEnrichmentService(
            session,
            processed_root=tmp_path / "processed",
        ).write_features(export.run_id)
        TelegramAggregatedStatsService(
            session,
            enriched_root=tmp_path / "enriched",
        ).write_stats(export.run_id)

        result = TelegramEntityExtractionService(
            session,
            enriched_root=tmp_path / "enriched",
        ).write_entities(export.run_id)

        assert result.entities_parquet_path.exists()
        assert result.entity_groups_path.exists()
        assert result.resolution_candidates_path.exists()
        assert result.summary_path.exists()
        assert result.metrics["entity_rows"] > 0
        assert result.metrics["group_count"] > 0

        rows = pq.read_table(result.entities_parquet_path).to_pylist()
        normalized_terms = {row["normalized_text"] for row in rows}
        assert "камера" in normalized_terms
        assert "умный дом" in normalized_terms
        assert "датчик протечка" in normalized_terms
        assert "стоить" not in normalized_terms
        assert all(
            json.loads(row["pos_pattern_json"])
            in (["NOUN"], ["PROPN"], ["NOUN", "NOUN"], ["ADJ", "NOUN"])
            for row in rows
        )

        smart_home = next(row for row in rows if row["normalized_text"] == "умный дом")
        assert smart_home["group_confidence"] == "high"
        assert smart_home["group_method"] == "exact"
        assert smart_home["mention_count"] >= 1
        assert json.loads(smart_home["source_refs_json"])

        groups = json.loads(result.entity_groups_path.read_text(encoding="utf-8"))
        smart_home_group = next(
            group for group in groups["groups"] if group["normalized_text"] == "умный дом"
        )
        assert smart_home_group["auto_merge_allowed"] is True
        assert smart_home_group["confidence"] == "high"

        with result.resolution_candidates_path.open(encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            assert reader.fieldnames == [
                "group_id",
                "candidate_1",
                "candidate_2",
                "similarity_score",
                "method",
                "pos_pattern",
                "example_context",
                "action_status",
            ]

        run = (
            session.execute(
                select(telegram_raw_export_runs_table).where(
                    telegram_raw_export_runs_table.c.id == export.run_id
                )
            )
            .mappings()
            .one()
        )
        metadata = run["metadata_json"]["entity_extraction"]
        assert metadata["entities_parquet_path"] == str(result.entities_parquet_path)
        assert metadata["entity_groups_path"] == str(result.entity_groups_path)
        assert metadata["auto_merge_policy"] == "exact_only"


def test_telegram_entity_ranking_marks_useful_terms_and_noise(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        export = _prepared_export(session, tmp_path)
        TelegramTextNormalizationService(
            session,
            processed_root=tmp_path / "processed",
        ).write_texts(export.run_id)
        TelegramArtifactTextExtractionService(
            session,
            processed_root=tmp_path / "processed",
            document_parser=PdfArtifactParser(reader_factory=lambda path: FakeReader([])),
            fetch_external_pages=False,
        ).write_texts(export.run_id)
        TelegramFeatureEnrichmentService(
            session,
            processed_root=tmp_path / "processed",
        ).write_features(export.run_id)
        TelegramAggregatedStatsService(
            session,
            enriched_root=tmp_path / "enriched",
        ).write_stats(export.run_id)
        TelegramEntityExtractionService(
            session,
            enriched_root=tmp_path / "enriched",
        ).write_entities(export.run_id)

        result = TelegramEntityRankingService(
            session,
            enriched_root=tmp_path / "enriched",
        ).write_rankings(export.run_id)

        assert result.ranked_entities_parquet_path.exists()
        assert result.ranked_entities_json_path.exists()
        assert result.noise_report_path.exists()
        assert result.summary_path.exists()
        assert result.metrics["ranked_entity_rows"] > 0
        assert result.metrics["promote_candidate_rows"] >= 1
        assert result.metrics["noise_rows"] >= 1

        rows = pq.read_table(result.ranked_entities_parquet_path).to_pylist()
        by_term = {row["normalized_text"]: row for row in rows}

        smart_home = by_term["умный дом"]
        assert smart_home["ranking_status"] == "promote_candidate"
        assert smart_home["score"] >= 0.65
        assert "pos_pattern:ADJ_NOUN" in json.loads(smart_home["reasons_json"])
        assert "artifact_mentions" in json.loads(smart_home["reasons_json"])

        leak_sensor = by_term["датчик протечка"]
        assert leak_sensor["ranking_status"] in {"promote_candidate", "review_candidate"}
        assert "pos_pattern:NOUN_NOUN" in json.loads(leak_sensor["reasons_json"])

        telegram_channel = by_term["telegram-канал"]
        assert telegram_channel["ranking_status"] == "noise"
        assert "navigation_noise" in json.loads(telegram_channel["penalties_json"])

        ranked = json.loads(result.ranked_entities_json_path.read_text(encoding="utf-8"))
        assert any(item["normalized_text"] == "умный дом" for item in ranked["promote_candidates"])
        assert "noise" in ranked

        noise = json.loads(result.noise_report_path.read_text(encoding="utf-8"))
        assert noise["penalty_counts"]["navigation_noise"] >= 1

        run = (
            session.execute(
                select(telegram_raw_export_runs_table).where(
                    telegram_raw_export_runs_table.c.id == export.run_id
                )
            )
            .mappings()
            .one()
        )
        metadata = run["metadata_json"]["entity_ranking"]
        assert metadata["ranked_entities_parquet_path"] == str(result.ranked_entities_parquet_path)
        assert metadata["ranking_policy"] == "rule_based_v1"


def _prepared_export(session, tmp_path):
    source = TelegramSourceService(session).create_draft(
        "https://t.me/purmaster",
        added_by="admin",
        purpose="catalog_ingestion",
        start_mode="from_beginning",
    )
    document_path = tmp_path / "catalog.txt"
    document_path.write_text(
        "Датчики протечки 2500 руб, реле защиты и сценарии умного дома.",
        encoding="utf-8",
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
                text="Сколько стоит камера Dahua Hero A1 за 10000р? +7 905 500-13-59",
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
                text="Предлагаем комплект видеонаблюдения и умный дом https://purmaster.ru @ssglocal",
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
            ),
            TelegramMessage(
                monitored_source_ref="https://t.me/purmaster",
                telegram_message_id=3,
                message_date=datetime(2026, 1, 31, 10, 17, 0, tzinfo=UTC),
                sender_id="channel-1",
                sender_display="ПУР",
                text="Перейти в категорию Telegram-канал и выбрать город.",
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


class FakeReader:
    def __init__(self, pages):
        self.pages = pages
