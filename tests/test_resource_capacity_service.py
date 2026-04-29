from datetime import UTC, datetime, timedelta

from sqlalchemy import insert, select

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.ai import (
    ai_model_concurrency_leases_table,
    ai_provider_accounts_table,
    ai_providers_table,
)
from pur_leads.models.telegram_sources import telegram_bots_table, userbot_accounts_table
from pur_leads.services.ai_registry import AiRegistryService
from pur_leads.services.resource_capacity import ResourceCapacityService
from pur_leads.services.settings import SettingsService


def test_capacity_planner_sums_provider_account_model_slots_and_telegram_resources(tmp_path):
    session_factory = _session_factory(tmp_path)
    with session_factory() as session:
        registry = AiRegistryService(session)
        registry.bootstrap_defaults(actor="test")
        provider_id = session.execute(select(ai_providers_table.c.id)).scalar_one()
        _insert_ai_account(session, provider_id, display_name="Second Z.AI")
        _insert_userbot(session, max_parallel_telegram_jobs=2)
        _insert_userbot(session, max_parallel_telegram_jobs=1)
        _insert_bot(session, display_name="Bot A")
        _insert_bot(session, display_name="Bot B")
        SettingsService(session).set(
            "worker_capacity_global_cap",
            64,
            value_type="int",
            updated_by="test",
        )
        session.commit()

        report = ResourceCapacityService(session).capacity_report()

        glm_plus_pools = [
            pool
            for pool in report["ai_model_pools"]
            if pool["normalized_model_name"] == "glm-4-plus"
        ]
        glm_ocr_pool = next(
            pool for pool in report["ai_model_pools"] if pool["normalized_model_name"] == "glm-ocr"
        )
        assert len(glm_plus_pools) == 2
        assert {pool["effective_limit"] for pool in glm_plus_pools} == {16}
        assert glm_plus_pools[0]["supports_thinking"] is False
        assert "llm.structured_output" not in glm_plus_pools[0]["capabilities"]
        assert glm_ocr_pool["endpoint_family"] == "layout_parsing"
        assert glm_ocr_pool["supports_document_input"] is True
        assert "ocr.document" in glm_ocr_pool["capabilities"]
        assert report["totals"]["ai_model_effective_slots"] >= 32
        assert report["totals"]["telegram_userbot_effective_slots"] == 3
        assert report["totals"]["telegram_bot_effective_slots"] == 2
        assert report["worker_capacity"]["resource_limited_worker_capacity"] > 32
        assert report["worker_capacity"]["recommended_worker_concurrency"] > 32
        assert report["worker_capacity"]["configured_worker_concurrency"] == 1
        assert report["bottlenecks"][0]["kind"] == "worker_concurrency"


def test_capacity_planner_subtracts_active_ai_model_leases_by_provider_account(tmp_path):
    session_factory = _session_factory(tmp_path)
    with session_factory() as session:
        AiRegistryService(session).bootstrap_defaults(actor="test")
        account_id = session.execute(select(ai_provider_accounts_table.c.id)).scalar_one()
        _insert_ai_lease(
            session,
            provider_account_id=account_id,
            provider="zai",
            model="GLM-4-Plus",
        )
        _insert_ai_lease(
            session,
            provider_account_id="other-account",
            provider="zai",
            model="GLM-4-Plus",
        )
        session.commit()

        report = ResourceCapacityService(session).capacity_report()

        glm_plus_pool = next(
            pool
            for pool in report["ai_model_pools"]
            if pool["normalized_model_name"] == "glm-4-plus"
        )
        assert glm_plus_pool["used_slots"] == 1
        assert glm_plus_pool["available_slots"] == 15


def _session_factory(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    return create_session_factory(engine)


def _insert_ai_account(session, provider_id: str, *, display_name: str) -> str:
    now = datetime(2026, 4, 29, 12, 0, tzinfo=UTC)
    account_id = new_id()
    session.execute(
        insert(ai_provider_accounts_table).values(
            id=account_id,
            ai_provider_id=provider_id,
            display_name=display_name,
            base_url="https://api.z.ai/api/coding/paas/v4",
            auth_secret_ref="secret:test",
            plan_type="unknown",
            enabled=True,
            priority=20,
            request_timeout_seconds=60.0,
            policy_warning_required=False,
            policy_warning_acknowledged_at=None,
            metadata_json={},
            notes=None,
            created_at=now,
            updated_at=now,
        )
    )
    return account_id


def _insert_userbot(session, *, max_parallel_telegram_jobs: int) -> str:
    now = datetime(2026, 4, 29, 12, 0, tzinfo=UTC)
    account_id = new_id()
    session.execute(
        insert(userbot_accounts_table).values(
            id=account_id,
            display_name=f"Userbot {max_parallel_telegram_jobs}",
            telegram_user_id=None,
            telegram_username=None,
            session_name=f"session-{account_id}",
            session_path=f"/tmp/{account_id}.session",
            status="active",
            priority="normal",
            max_parallel_telegram_jobs=max_parallel_telegram_jobs,
            flood_sleep_threshold_seconds=60,
            last_connected_at=None,
            last_error=None,
            created_at=now,
            updated_at=now,
        )
    )
    return account_id


def _insert_bot(session, *, display_name: str) -> str:
    now = datetime(2026, 4, 29, 12, 0, tzinfo=UTC)
    bot_id = new_id()
    session.execute(
        insert(telegram_bots_table).values(
            id=bot_id,
            display_name=display_name,
            telegram_bot_id=None,
            telegram_username=None,
            token_secret_ref=f"secret:{bot_id}",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    return bot_id


def _insert_ai_lease(
    session,
    *,
    provider_account_id: str,
    provider: str,
    model: str,
) -> None:
    now = utc_now()
    session.execute(
        insert(ai_model_concurrency_leases_table).values(
            id=new_id(),
            provider=provider,
            ai_provider_account_id=provider_account_id,
            model=model,
            normalized_model=model.casefold(),
            worker_name="test-worker",
            ai_model_id=None,
            ai_run_id=None,
            ai_run_output_id=None,
            raw_limit=20,
            utilization_ratio=0.8,
            effective_limit=16,
            acquired_at=now,
            lease_expires_at=now + timedelta(minutes=5),
            metadata_json={},
        )
    )
