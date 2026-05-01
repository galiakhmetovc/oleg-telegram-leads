from datetime import timedelta

from sqlalchemy import select

from pur_leads.core.time import utc_now
from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.ai import ai_model_concurrency_leases_table
from pur_leads.services.ai_concurrency import (
    AiModelConcurrencyService,
    begin_serialized_lease_transaction,
)


def test_ai_model_concurrency_service_applies_80_percent_safety_ratio_and_releases(tmp_path):
    session_factory = _session_factory(tmp_path)
    with session_factory() as session:
        service = AiModelConcurrencyService(session)

        first = service.acquire_model_slot(
            provider="zai",
            model="glm-4.5-flash",
            worker_name="worker-1",
        )
        blocked = service.acquire_model_slot(
            provider="zai",
            model="GLM-4.5-Flash",
            worker_name="worker-2",
        )

        rows = session.execute(select(ai_model_concurrency_leases_table)).mappings().all()
        assert first is not None
        assert blocked is None
        assert service.raw_limit_for_model("glm-4.5-flash") == 2
        assert service.effective_limit_for_model("glm-4.5-flash") == 1
        assert len(rows) == 1
        assert {row["normalized_model"] for row in rows} == {"glm-4.5-flash"}
        assert rows[0]["raw_limit"] == 2
        assert rows[0]["utilization_ratio"] == 0.8
        assert rows[0]["effective_limit"] == 1

        service.release_model_slot(first)
        acquired_after_release = service.acquire_model_slot(
            provider="zai",
            model="glm-4.5-flash",
            worker_name="worker-3",
        )

        assert acquired_after_release is not None


def test_ai_model_concurrency_service_ignores_expired_leases(tmp_path):
    session_factory = _session_factory(tmp_path)
    with session_factory() as session:
        service = AiModelConcurrencyService(session)
        expired = service.acquire_slot(
            provider="zai",
            model="glm-5.1",
            limit=1,
            worker_name="worker-1",
            lease_seconds=1,
        )
        assert expired is not None
        session.execute(
            ai_model_concurrency_leases_table.update()
            .where(ai_model_concurrency_leases_table.c.id == expired.id)
            .values(lease_expires_at=utc_now() - timedelta(seconds=1))
        )
        session.commit()

        acquired = service.acquire_slot(
            provider="zai",
            model="glm-5.1",
            limit=1,
            worker_name="worker-2",
            lease_seconds=1,
        )

        rows = session.execute(select(ai_model_concurrency_leases_table)).mappings().all()
        assert acquired is not None
        assert len(rows) == 1
        assert rows[0]["worker_name"] == "worker-2"


def test_begin_serialized_lease_transaction_uses_postgres_advisory_lock():
    session = _FakeSession("postgresql")

    begin_serialized_lease_transaction(session, lock_key="zai:glm-5.1")

    assert session.committed is True
    assert session.executed[0][0] == "SELECT pg_advisory_xact_lock(hashtext(:lock_key))"
    assert session.executed[0][1] == {"lock_key": "zai:glm-5.1"}


def test_begin_serialized_lease_transaction_keeps_sqlite_immediate_transaction():
    session = _FakeSession("sqlite")

    begin_serialized_lease_transaction(session, lock_key="zai:glm-5.1")

    assert session.committed is True
    assert session.executed[0][0] == "BEGIN IMMEDIATE"
    assert session.executed[0][1] is None


def _session_factory(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    return create_session_factory(engine)


class _FakeDialect:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeBind:
    def __init__(self, dialect_name: str) -> None:
        self.dialect = _FakeDialect(dialect_name)


class _FakeText:
    def __init__(self, value: str) -> None:
        self.text = value


class _FakeSession:
    def __init__(self, dialect_name: str) -> None:
        self.bind = _FakeBind(dialect_name)
        self.committed = False
        self.executed = []

    def get_bind(self):
        return self.bind

    def commit(self) -> None:
        self.committed = True

    def execute(self, statement, params=None):  # noqa: ANN001
        value = getattr(statement, "text", str(statement))
        self.executed.append((value, params))
