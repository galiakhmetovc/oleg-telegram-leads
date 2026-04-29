from datetime import timedelta

from sqlalchemy import select

from pur_leads.core.time import utc_now
from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.ai import ai_model_concurrency_leases_table
from pur_leads.services.ai_concurrency import AiModelConcurrencyService


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


def _session_factory(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    return create_session_factory(engine)
