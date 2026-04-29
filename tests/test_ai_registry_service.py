from sqlalchemy import select, update

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.ai import (
    ai_agent_routes_table,
    ai_agents_table,
    ai_model_limits_table,
    ai_models_table,
    ai_provider_accounts_table,
    ai_providers_table,
)
from pur_leads.services.ai_registry import AiRegistryService


def test_ai_registry_bootstrap_creates_zai_models_agents_and_multi_model_routes(tmp_path):
    session_factory = _session_factory(tmp_path)
    with session_factory() as session:
        result = AiRegistryService(session).bootstrap_defaults(actor="test")

        providers = session.execute(select(ai_providers_table)).mappings().all()
        accounts = session.execute(select(ai_provider_accounts_table)).mappings().all()
        models = {
            row["normalized_model_name"]: row
            for row in session.execute(select(ai_models_table)).mappings().all()
        }
        limits = {
            (row["ai_model_id"], row["limit_scope"]): row
            for row in session.execute(select(ai_model_limits_table)).mappings().all()
        }
        agents = {
            row["agent_key"]: row
            for row in session.execute(select(ai_agents_table)).mappings().all()
        }
        routes = session.execute(select(ai_agent_routes_table)).mappings().all()

        assert result["provider_key"] == "zai"
        assert providers[0]["provider_key"] == "zai"
        assert accounts[0]["plan_type"] == "unknown"
        assert "glm-4.5-flash" in models
        assert "glm-ocr" in models
        assert models["glm-ocr"]["model_type"] == "ocr"
        assert models["glm-ocr"]["supports_thinking"] is False
        assert models["glm-ocr"]["supports_structured_output"] is False
        assert models["glm-ocr"]["supports_json_mode"] is False
        assert models["glm-ocr"]["supports_document_input"] is True
        assert models["glm-ocr"]["metadata_json"]["endpoint_family"] == "layout_parsing"
        assert models["glm-5.1"]["supports_thinking"] is True
        assert models["glm-5.1"]["supports_structured_output"] is True
        assert models["glm-5.1"]["metadata_json"]["thinking_control_values"] == [
            "enabled",
            "disabled",
        ]
        assert models["glm-4-plus"]["supports_thinking"] is False
        assert models["glm-4-plus"]["supports_structured_output"] is False
        flash_limit = limits[(models["glm-4.5-flash"]["id"], "concurrency")]
        assert flash_limit["raw_limit"] == 2
        assert flash_limit["effective_limit"] == 1
        assert flash_limit["utilization_ratio"] == 0.8
        assert "catalog_extractor" in agents
        assert "lead_detector" in agents
        assert "ocr_extractor" in agents
        catalog_routes = [
            route for route in routes if route["ai_agent_id"] == agents["catalog_extractor"]["id"]
        ]
        assert {route["route_role"] for route in catalog_routes} >= {"primary", "fallback"}
        assert {route["ai_model_id"] for route in catalog_routes} >= {
            models["glm-5.1"]["id"],
            models["glm-4.5-air"]["id"],
        }


def test_ai_registry_selects_enabled_routes_by_agent_and_role(tmp_path):
    session_factory = _session_factory(tmp_path)
    with session_factory() as session:
        service = AiRegistryService(session)
        service.bootstrap_defaults(actor="test")

        primary = service.select_routes(agent_key="catalog_extractor", route_role="primary")
        fallback = service.select_routes(agent_key="catalog_extractor", route_role="fallback")
        ocr = service.select_routes(agent_key="ocr_extractor", route_role="primary")

        assert [route.model for route in primary] == ["GLM-5.1"]
        assert [route.model for route in fallback] == ["GLM-4.5-Air"]
        assert [route.model for route in ocr] == ["GLM-OCR"]
        assert primary[0].provider == "zai"
        assert primary[0].base_url == "https://api.z.ai/api/coding/paas/v4"
        assert primary[0].thinking_mode == "off"
        assert primary[0].supports_thinking is True
        assert primary[0].supports_structured_output is True
        assert ocr[0].supports_thinking is False
        assert ocr[0].supports_structured_output is False
        assert ocr[0].endpoint_family == "layout_parsing"


def test_ai_registry_bootstrap_does_not_reenable_operator_disabled_routes(tmp_path):
    session_factory = _session_factory(tmp_path)
    with session_factory() as session:
        service = AiRegistryService(session)
        service.bootstrap_defaults(actor="test")
        primary = service.select_routes(agent_key="catalog_extractor", route_role="primary")[0]

        session.execute(
            update(ai_agent_routes_table)
            .where(ai_agent_routes_table.c.id == primary.route_id)
            .values(enabled=False)
        )
        session.commit()

        service.bootstrap_defaults(actor="test")

        assert service.select_routes(agent_key="catalog_extractor", route_role="primary") == []


def test_ai_registry_returns_raw_concurrency_limits_for_provider(tmp_path):
    session_factory = _session_factory(tmp_path)
    with session_factory() as session:
        service = AiRegistryService(session)
        service.bootstrap_defaults(actor="test")

        limits = service.model_concurrency_limits(provider_key="zai")

        assert limits["glm-4-plus"] == 20
        assert limits["glm-4.5-flash"] == 2


def test_ai_registry_bootstrap_does_not_overwrite_operator_model_limits(tmp_path):
    session_factory = _session_factory(tmp_path)
    with session_factory() as session:
        service = AiRegistryService(session)
        service.bootstrap_defaults(actor="test")
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
            update(ai_model_limits_table)
            .where(
                ai_model_limits_table.c.ai_model_id == flash["id"],
                ai_model_limits_table.c.limit_scope == "concurrency",
            )
            .values(raw_limit=7, effective_limit=5, source="operator_configured")
        )
        session.commit()

        service.bootstrap_defaults(actor="test")

        assert service.model_concurrency_limits(provider_key="zai")["glm-4.5-flash"] == 7


def _session_factory(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    return create_session_factory(engine)
