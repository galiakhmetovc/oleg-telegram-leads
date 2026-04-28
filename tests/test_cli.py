from sqlalchemy import inspect
from sqlalchemy import select
from fastapi.testclient import TestClient

from pur_leads.cli import main
from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.integrations.telegram.types import ResolvedTelegramSource, SourceAccessResult
from pur_leads.models.audit import operational_events_table
from pur_leads.models.telegram_sources import source_access_checks_table
from pur_leads.services.scheduler import SchedulerService
from pur_leads.services.telegram_sources import TelegramSourceService
from pur_leads.services.userbots import UserbotAccountService


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


def test_cli_worker_once_reports_noop(tmp_path, capsys):
    db_path = tmp_path / "cli.db"
    main(["--database-path", str(db_path), "db", "upgrade"])

    main(["--database-path", str(db_path), "worker", "once"])

    output = capsys.readouterr().out
    assert "no queued jobs" in output


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
        event = session.execute(select(operational_events_table)).mappings().one()
    output = capsys.readouterr().out
    assert stored is not None
    assert "failed job" in output
    assert stored.last_error == "classify_message_batch adapter is not configured"
    assert event["details_json"]["reason"] == "handler_exception"


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


class FakeConfiguredTelegramClient:
    instances = []

    def __init__(self, *, session_path, api_id, api_hash, **_kwargs) -> None:
        self.session_path = session_path
        self.api_id = api_id
        self.api_hash = api_hash
        self.instances.append(self)

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

    async def fetch_message_batch(self, source, *, after_message_id, limit):  # noqa: ANN001, ANN201
        return []

    async def fetch_context(self, source, *, message_id, before, after, reply_depth):  # noqa: ANN001, ANN201
        raise NotImplementedError
