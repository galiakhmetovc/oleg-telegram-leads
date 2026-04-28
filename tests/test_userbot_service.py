from sqlalchemy import select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.audit import audit_log_table
from pur_leads.services.settings import SettingsService
from pur_leads.services.userbots import UserbotAccountService


def test_create_and_list_userbot_accounts_with_audit(tmp_path):
    session = _session(tmp_path)
    service = UserbotAccountService(session)

    account = service.create_account(
        display_name="Main userbot",
        session_name="main",
        session_path="/secure/main.session",
        actor="admin",
    )
    rows = service.list_accounts()
    public = service.public_payload(account)
    audit_actions = {row["action"] for row in session.execute(select(audit_log_table)).mappings()}

    assert rows == [account]
    assert account.status == "active"
    assert account.max_parallel_telegram_jobs == 1
    assert account.flood_sleep_threshold_seconds == 60
    assert public["display_name"] == "Main userbot"
    assert public["session_name"] == "main"
    assert public["status"] == "active"
    assert "session_path" not in public
    assert "userbot_account.create" in audit_actions


def test_select_default_userbot_prefers_configured_active_account(tmp_path):
    session = _session(tmp_path)
    service = UserbotAccountService(session)
    first = service.create_account(
        display_name="First userbot",
        session_name="first",
        session_path="/secure/first.session",
        actor="admin",
    )
    second = service.create_account(
        display_name="Second userbot",
        session_name="second",
        session_path="/secure/second.session",
        actor="admin",
    )
    SettingsService(session).set(
        "telegram_default_userbot_account_id",
        second.id,
        value_type="string",
        updated_by="admin",
        reason="prefer second",
    )

    selected = service.select_default_userbot()

    assert selected is not None
    assert selected.id == second.id
    assert selected.id != first.id


def test_select_default_userbot_falls_back_to_first_active_account(tmp_path):
    session = _session(tmp_path)
    service = UserbotAccountService(session)
    paused = service.create_account(
        display_name="Paused userbot",
        session_name="paused",
        session_path="/secure/paused.session",
        actor="admin",
        status="paused",
    )
    active = service.create_account(
        display_name="Active userbot",
        session_name="active",
        session_path="/secure/active.session",
        actor="admin",
    )

    selected = service.select_default_userbot()

    assert selected is not None
    assert selected.id == active.id
    assert selected.id != paused.id


def _session(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    return create_session_factory(engine)()
