from datetime import UTC, datetime
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient
import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.integrations.telegram.types import ResolvedTelegramSource, TelegramMessage
from pur_leads.models.telegram_sources import telegram_raw_export_runs_table
from pur_leads.services.telegram_raw_export import TelegramRawExportService
from pur_leads.services.telegram_run_metadata import merge_raw_export_run_metadata
from pur_leads.services.telegram_sources import TelegramSourceService
from pur_leads.services.web_auth import WebAuthService
from pur_leads.web.app import create_app


def test_artifact_routes_list_run_artifacts_and_return_preview(tmp_path):
    fixture = _setup_artifact_app(tmp_path)
    client = fixture["client"]
    artifact_path = tmp_path / "enriched" / "lead_candidate_llm_arbitration.json"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text(
        '{"metrics":{"lead_count":3},"results":[{"decision":{"decision":"lead"}}]}',
        encoding="utf-8",
    )
    with fixture["session_factory"]() as session:
        export = _create_raw_export(session, tmp_path)
        merge_raw_export_run_metadata(
            session,
            export.run_id,
            key="lead_candidate_llm_arbitration",
            value={
                "stage": "telegram_lead_candidate_llm_arbitration",
                "arbitration_json_path": str(artifact_path),
                "metrics": {"lead_count": 3},
            },
        )
        session.commit()

    denied = client.get("/api/artifacts")
    _login(client)
    page = client.get("/artifacts")
    payload = client.get("/api/artifacts").json()

    assert denied.status_code == 401
    assert page.status_code == 200
    assert 'data-page="artifacts"' in page.text
    assert 'id="artifact-list"' in page.text
    assert 'id="artifact-detail"' in page.text
    assert payload["summary"]["run_count"] == 1
    assert payload["summary"]["artifact_count"] >= 7
    assert payload["summary"]["missing_count"] == 0

    arbitration = next(
        item for item in payload["items"] if item["key"] == "arbitration_json_path"
    )
    detail = client.get(f"/api/artifacts/{arbitration['id']}").json()

    assert arbitration["stage"] == "lead_candidate_llm_arbitration"
    assert arbitration["kind"] == "json"
    assert arbitration["exists"] is True
    assert detail["artifact"]["id"] == arbitration["id"]
    assert '"lead_count": 3' in detail["preview"]["text"]
    assert detail["preview"]["truncated"] is False


def test_artifact_detail_previews_parquet_and_sqlite_structures(tmp_path):
    fixture = _setup_artifact_app(tmp_path)
    client = fixture["client"]
    parquet_path = tmp_path / "processed" / "texts.parquet"
    parquet_path.parent.mkdir(parents=True)
    pq.write_table(
        pa.table(
            {
                "telegram_message_id": [1, 2],
                "clean_text": ["нужна камера", "спасибо"],
                "tokens": [["нужна", "камера"], ["спасибо"]],
            }
        ),
        parquet_path,
    )
    sqlite_path = tmp_path / "search" / "search.sqlite3"
    sqlite_path.parent.mkdir(parents=True)
    with sqlite3.connect(sqlite_path) as connection:
        connection.execute("create table messages(id integer primary key, clean_text text)")
        connection.execute("insert into messages(clean_text) values (?)", ("нужна камера",))

    with fixture["session_factory"]() as session:
        export = _create_raw_export(session, tmp_path)
        merge_raw_export_run_metadata(
            session,
            export.run_id,
            key="text_normalization",
            value={"texts_parquet_path": str(parquet_path)},
        )
        merge_raw_export_run_metadata(
            session,
            export.run_id,
            key="fts_index",
            value={"search_db_path": str(sqlite_path)},
        )
        session.commit()

    _login(client)
    payload = client.get("/api/artifacts").json()
    parquet = next(item for item in payload["items"] if item["key"] == "texts_parquet_path")
    sqlite = next(item for item in payload["items"] if item["key"] == "search_db_path")

    parquet_detail = client.get(f"/api/artifacts/{parquet['id']}").json()
    sqlite_detail = client.get(f"/api/artifacts/{sqlite['id']}").json()

    assert parquet_detail["preview"]["available"] is True
    assert parquet_detail["preview"]["kind"] == "parquet"
    assert parquet_detail["preview"]["row_count"] == 2
    assert parquet_detail["preview"]["columns"][0] == {
        "name": "telegram_message_id",
        "type": "int64",
    }
    assert parquet_detail["preview"]["rows"][0]["clean_text"] == "нужна камера"
    assert "telegram_message_id: int64" in parquet_detail["preview"]["text"]

    assert sqlite_detail["preview"]["available"] is True
    assert sqlite_detail["preview"]["kind"] == "sqlite"
    assert sqlite_detail["preview"]["tables"] == [{"name": "messages", "row_count": 1}]
    assert sqlite_detail["preview"]["sample"]["table"] == "messages"
    assert sqlite_detail["preview"]["sample"]["rows"][0]["clean_text"] == "нужна камера"
    assert "messages: 1 rows" in sqlite_detail["preview"]["text"]


def test_artifact_detail_previews_jsonl_records(tmp_path):
    fixture = _setup_artifact_app(tmp_path)
    client = fixture["client"]
    trace_path = tmp_path / "enriched" / "lead_candidate_llm_traces.jsonl"
    trace_path.parent.mkdir(parents=True)
    trace_path.write_text(
        "\n".join(
            [
                '{"sequence_index":0,"model":"GLM-5.1","prompt_text":"prompt 1","raw_response":"response 1"}',
                '{"sequence_index":1,"model":"GLM-5.1","prompt_text":"prompt 2","raw_response":"response 2"}',
            ]
        ),
        encoding="utf-8",
    )

    with fixture["session_factory"]() as session:
        export = _create_raw_export(session, tmp_path)
        merge_raw_export_run_metadata(
            session,
            export.run_id,
            key="lead_candidate_llm_arbitration",
            value={"traces_jsonl_path": str(trace_path)},
        )
        session.commit()

    _login(client)
    payload = client.get("/api/artifacts").json()
    trace = next(item for item in payload["items"] if item["key"] == "traces_jsonl_path")
    detail = client.get(f"/api/artifacts/{trace['id']}").json()

    assert detail["preview"]["available"] is True
    assert detail["preview"]["kind"] == "jsonl"
    assert detail["preview"]["records_previewed"] == 2
    assert detail["preview"]["records"][0]["model"] == "GLM-5.1"
    assert detail["preview"]["records"][0]["prompt_text"] == "prompt 1"
    assert "response 2" in detail["preview"]["text"]


def test_artifact_routes_discover_unregistered_files_inside_run_directories(tmp_path):
    fixture = _setup_artifact_app(tmp_path)
    client = fixture["client"]
    with fixture["session_factory"]() as session:
        export = _create_raw_export(session, tmp_path)
        run = (
            session.execute(
                select(telegram_raw_export_runs_table).where(
                    telegram_raw_export_runs_table.c.id == export.run_id
                )
            )
            .mappings()
            .one()
        )
        hidden_path = Path(run["output_dir"]) / "reports" / "unregistered_report.json"
        hidden_path.parent.mkdir(parents=True, exist_ok=True)
        hidden_path.write_text('{"status":"discovered"}', encoding="utf-8")

    _login(client)
    payload = client.get("/api/artifacts").json()
    discovered = next(
        item for item in payload["items"] if item["path"].endswith("unregistered_report.json")
    )
    detail = client.get(f"/api/artifacts/{discovered['id']}").json()

    assert discovered["stage"] == "raw_export"
    assert discovered["key"] == "reports/unregistered_report.json"
    assert discovered["metadata_json"] == {"source": "filesystem_discovery"}
    assert '"status": "discovered"' in detail["preview"]["text"]


def test_artifact_routes_discover_unregistered_files_inside_metadata_directories(tmp_path):
    fixture = _setup_artifact_app(tmp_path)
    client = fixture["client"]
    chroma_dir = tmp_path / "chroma" / "run"
    chroma_dir.mkdir(parents=True)
    sqlite_file = chroma_dir / "chroma.sqlite3"
    with sqlite3.connect(sqlite_file) as connection:
        connection.execute("create table embeddings(id text primary key)")

    with fixture["session_factory"]() as session:
        export = _create_raw_export(session, tmp_path)
        merge_raw_export_run_metadata(
            session,
            export.run_id,
            key="chroma_index",
            value={"chroma_path": str(chroma_dir)},
        )
        session.commit()

    _login(client)
    payload = client.get("/api/artifacts").json()
    discovered = next(
        item for item in payload["items"] if item["path"].endswith("chroma.sqlite3")
    )

    assert discovered["stage"] == "chroma_index"
    assert discovered["key"] == "chroma.sqlite3"
    assert discovered["kind"] == "sqlite"
    assert discovered["metadata_json"] == {"source": "filesystem_discovery"}


def _setup_artifact_app(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        WebAuthService(session, telegram_bot_token="telegram-token").ensure_bootstrap_admin(
            username="admin",
            password="initial-secret",
        )
    app = create_app(
        database_path=db_path,
        bootstrap_admin_password="initial-secret",
        bootstrap_admin_password_file=tmp_path / "bootstrap-admin-password.txt",
        telegram_bot_token="telegram-token",
    )
    return {"client": TestClient(app), "session_factory": session_factory}


def _login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/local",
        json={"username": "admin", "password": "initial-secret"},
    )
    assert response.status_code == 200


def _create_raw_export(session, tmp_path):
    source = TelegramSourceService(session).create_draft(
        "https://t.me/chat_mila_kolpakova",
        added_by="admin",
        purpose="lead_monitoring",
        start_mode="from_beginning",
    )
    export = TelegramRawExportService(session, raw_root=tmp_path / "raw").write_export(
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
                text="Нужна камера Dahua",
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
    run = (
        session.execute(
            select(telegram_raw_export_runs_table).where(
                telegram_raw_export_runs_table.c.id == export.run_id
            )
        )
        .mappings()
        .one()
    )
    assert Path(run["manifest_path"]).exists()
    return export
