import pytest
from sqlalchemy import select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.audit import audit_log_table, operational_events_table
from pur_leads.services.audit import AuditService


@pytest.fixture
def audit_service(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        yield AuditService(session), session


def test_record_change_stores_actor_entity_and_values(audit_service):
    service, session = audit_service

    service.record_change(
        actor="admin",
        action="settings.update",
        entity_type="setting",
        entity_id="telegram_worker_count",
        old_value_json={"value": 1},
        new_value_json={"value": 2},
    )

    row = session.execute(select(audit_log_table)).mappings().one()
    assert row["actor"] == "admin"
    assert row["action"] == "settings.update"
    assert row["entity_type"] == "setting"
    assert row["entity_id"] == "telegram_worker_count"
    assert row["old_value_json"] == {"value": 1}
    assert row["new_value_json"] == {"value": 2}


def test_record_event_stores_runtime_details(audit_service):
    service, session = audit_service

    service.record_event(
        event_type="scheduler",
        severity="warning",
        message="worker lease expired",
        entity_type="scheduler_job",
        entity_id="job-1",
        correlation_id="corr-1",
        details_json={"worker": "worker-a"},
    )

    row = session.execute(select(operational_events_table)).mappings().one()
    assert row["event_type"] == "scheduler"
    assert row["severity"] == "warning"
    assert row["correlation_id"] == "corr-1"
    assert row["details_json"] == {"worker": "worker-a"}


def test_secret_like_values_are_masked_in_audit_and_events(audit_service):
    service, session = audit_service

    service.record_change(
        actor="admin",
        action="secret.update",
        entity_type="secret_ref",
        entity_id="secret-1",
        old_value_json=None,
        new_value_json={"api_key": "raw-key", "nested": {"token": "raw-token"}},
    )
    service.record_event(
        event_type="scheduler",
        severity="error",
        message="secret check failed",
        details_json={"password": "raw-password"},
    )

    audit_row = session.execute(select(audit_log_table)).mappings().one()
    event_row = session.execute(select(operational_events_table)).mappings().one()
    assert audit_row["new_value_json"] == {
        "api_key": "***",
        "nested": {"token": "***"},
    }
    assert event_row["details_json"] == {"password": "***"}
