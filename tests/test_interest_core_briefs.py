from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

from sqlalchemy import inspect, select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.integrations.ai.chat import AiChatCompletion
from pur_leads.integrations.documents.pdf_parser import PdfArtifactParser
from pur_leads.integrations.telegram.types import ResolvedTelegramSource, TelegramMessage
from pur_leads.models.interest_core_briefs import interest_core_briefs_table
from pur_leads.models.telegram_sources import telegram_raw_export_runs_table
from pur_leads.services.interest_contexts import (
    INTEREST_CONTEXT_SOURCE_PURPOSE,
    InterestContextService,
)
from pur_leads.services.interest_core_briefs import InterestCoreBriefService
from pur_leads.services.telegram_artifact_texts import TelegramArtifactTextExtractionService
from pur_leads.services.telegram_raw_export import TelegramRawExportService
from pur_leads.services.telegram_sources import TelegramSourceService
from pur_leads.services.telegram_text_normalization import TelegramTextNormalizationService
from pur_leads.workers.runtime import build_telegram_handler_registry


def test_migration_creates_interest_core_briefs_table(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")

    upgrade_database(engine)

    inspector = inspect(engine)
    assert "interest_core_briefs" in set(inspector.get_table_names())
    columns = {column["name"] for column in inspector.get_columns("interest_core_briefs")}
    assert {
        "context_id",
        "version",
        "status",
        "source",
        "brief_text",
        "brief_json",
        "prompt_text",
        "request_json",
        "response_json",
        "source_refs_json",
    }.issubset(columns)


def test_worker_registry_exposes_interest_core_brief_generation(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        handlers = build_telegram_handler_registry(session, object(), worker_name="test-worker")

    assert "generate_interest_core_brief" in handlers


def test_manual_interest_core_brief_activation_archives_previous(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        context = InterestContextService(session).create_context(
            name="ПУР",
            description="Умный дом и инженерные системы",
            actor="admin",
        )
        service = InterestCoreBriefService(session)

        first = service.create_manual(
            context.id,
            brief_text="ПУР занимается умным домом.",
            actor="admin",
            activate=True,
        )
        second = service.create_manual(
            context.id,
            brief_text="ПУР занимается умным домом, видеонаблюдением и инженеркой.",
            actor="admin",
            activate=True,
        )

        rows = [
            dict(row)
            for row in session.execute(
                select(interest_core_briefs_table).order_by(interest_core_briefs_table.c.version)
            )
            .mappings()
            .all()
        ]

    assert first.version == 1
    assert second.version == 2
    assert [row["status"] for row in rows] == ["archived", "active"]
    assert rows[1]["source"] == "manual"
    assert rows[1]["brief_text"].startswith("ПУР занимается умным домом")
    assert rows[1]["activated_by"] == "admin"


def test_llm_generation_builds_prompt_from_prepared_messages_and_documents(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        context = InterestContextService(session).create_context(
            name="ПУР",
            description="Канал для построения ядра интересов",
            actor="admin",
        )
        raw_export_run_id = _prepared_interest_export(session, tmp_path, context.id)
        client = ScriptedBriefClient(
            json.dumps(
                {
                    "subject_name": "ПУР",
                    "short_description": (
                        "Инженерный проект про умный дом, видеонаблюдение и щитовое оборудование."
                    ),
                    "business_focus": ["умный дом", "видеонаблюдение"],
                    "products_and_services": ["камеры Dahua", "датчики протечки"],
                    "customer_segments": ["владельцы домов"],
                    "lead_interest_criteria": ["ищет камеру", "нужен датчик"],
                    "support_interest_criteria": ["просит подобрать оборудование"],
                    "noise_criteria": ["навигационные сообщения"],
                    "hypotheses": ["можно продавать комплекты оборудования"],
                    "source_evidence": [
                        {
                            "source_ref": "telegram:purmaster:1",
                            "quote": "комплект видеонаблюдения",
                            "why": "описание предложения",
                        }
                    ],
                    "uncertain_assumptions": [],
                },
                ensure_ascii=False,
            )
        )

        record = InterestCoreBriefService(session).generate_from_sources(
            context.id,
            client=client,
            actor="admin",
            provider="zai",
            model="GLM-4-Plus",
            model_profile="Каталог: основной JSON",
            max_tokens=4096,
            temperature=0.0,
            activate=True,
        )
        row = session.execute(select(interest_core_briefs_table)).mappings().one()
        raw_run = (
            session.execute(
                select(telegram_raw_export_runs_table).where(
                    telegram_raw_export_runs_table.c.id == raw_export_run_id
                )
            )
            .mappings()
            .one()
        )

    assert record.status == "active"
    assert row["source"] == "llm_generated"
    assert row["provider"] == "zai"
    assert row["model"] == "GLM-4-Plus"
    assert row["brief_json"]["subject_name"] == "ПУР"
    assert "видеонаблюдение" in row["brief_text"]
    assert "комплект видеонаблюдения" in row["prompt_text"]
    assert "Датчики протечки" in row["prompt_text"]
    assert row["request_json"]["messages"][1]["content"] == row["prompt_text"]
    assert row["response_json"]["content"] == client.content
    assert row["parsed_response_json"]["products_and_services"] == [
        "камеры Dahua",
        "датчики протечки",
    ]
    assert row["source_refs_json"]["raw_export_run_ids"] == [raw_export_run_id]
    assert raw_run["metadata_json"]["artifact_texts"]["rows_with_text"] >= 1


class ScriptedBriefClient:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict] = []

    async def complete(self, *, messages, model: str, temperature: float, max_tokens: int):
        self.calls.append(
            {
                "messages": list(messages),
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        return AiChatCompletion(
            content=self.content,
            model=model,
            request_id="brief-request-1",
            usage={"prompt_tokens": 100, "completion_tokens": 80},
            raw_response={"id": "brief-request-1"},
        )


def _prepared_interest_export(session, tmp_path: Path, context_id: str) -> str:
    source = TelegramSourceService(session).create_draft(
        "https://t.me/purmaster",
        added_by="admin",
        purpose=INTEREST_CONTEXT_SOURCE_PURPOSE,
        interest_context_id=context_id,
        start_mode="from_beginning",
    )
    document_path = tmp_path / "catalog.txt"
    document_path.write_text(
        "Датчики протечки, реле защиты, сценарии умного дома и камеры Dahua.",
        encoding="utf-8",
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
                text="ПУР: комплект видеонаблюдения и умный дом для квартиры.",
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
                text="Документ с каталогом оборудования.",
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
        ],
    )
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
    return export.run_id


class FakeReader:
    def __init__(self, pages):
        self.pages = pages
