import pytest
from sqlalchemy import select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.audit import audit_log_table
from pur_leads.models.catalog import (
    catalog_evidence_table,
    catalog_items_table,
    catalog_offers_table,
    catalog_terms_table,
    classifier_versions_table,
)
from pur_leads.services.catalog_editor import CatalogEditorService


@pytest.fixture
def catalog_editor_session(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        yield session


def test_manual_catalog_editor_creates_item_terms_offer_evidence_and_snapshot(
    catalog_editor_session,
):
    service = CatalogEditorService(catalog_editor_session)

    item = service.create_item(
        actor="admin",
        name="Домофоны Bas-IP для проектов",
        item_type="product",
        category_slug="intercom",
        description="Черные минималистичные домофоны для проектов ПУР",
        terms=[
            {"term": "bas-ip", "term_type": "alias"},
            {"term": "черный домофон", "term_type": "lead_phrase"},
            {"term": "стоимость", "term_type": "negative_phrase"},
        ],
        offers=[
            {
                "title": "Подбор домофона",
                "price_text": "по запросу",
                "offer_type": "service_price",
            }
        ],
        evidence={
            "quote": "Нужен минималистичный черный домофон",
            "source_url": "https://t.me/chat_mila_kolpakova/716254",
            "source_text": "Нужен минималистичный черный домофон",
        },
    )
    snapshot = service.rebuild_classifier_snapshot(actor="admin", reason="manual baseline")

    items = catalog_editor_session.execute(select(catalog_items_table)).mappings().all()
    terms = catalog_editor_session.execute(select(catalog_terms_table)).mappings().all()
    offers = catalog_editor_session.execute(select(catalog_offers_table)).mappings().all()
    evidence = catalog_editor_session.execute(select(catalog_evidence_table)).mappings().all()
    audit_actions = {
        row["action"]
        for row in catalog_editor_session.execute(select(audit_log_table)).mappings().all()
    }
    snapshots = catalog_editor_session.execute(select(classifier_versions_table)).mappings().all()

    assert item.status == "approved"
    assert items[0]["canonical_name"] == "Домофоны Bas-IP для проектов"
    assert {term["term_type"] for term in terms} == {
        "alias",
        "lead_phrase",
        "negative_phrase",
    }
    assert {term["normalized_term"] for term in terms} == {
        "bas-ip",
        "черный домофон",
        "стоимость",
    }
    assert offers[0]["title"] == "Подбор домофона"
    assert offers[0]["status"] == "approved"
    assert evidence[0]["entity_type"] == "item"
    assert evidence[0]["entity_id"] == item.id
    assert "catalog_editor.item_create" in audit_actions
    assert "catalog_editor.snapshot_rebuild" in audit_actions
    assert snapshot.version == 1
    assert snapshots[0]["created_by"] == "admin"


def test_manual_catalog_editor_updates_and_archives_entities(catalog_editor_session):
    service = CatalogEditorService(catalog_editor_session)
    item = service.create_item(
        actor="admin",
        name="Dahua Hero A1",
        item_type="product",
        category_slug="video_surveillance",
        terms=[{"term": "hero a1", "term_type": "alias"}],
    )

    updated = service.update_item(
        item.id,
        actor="admin",
        name="Dahua Hero A1 Wi-Fi",
        description="Поворотная Wi-Fi камера",
    )
    term = service.add_term(
        item.id,
        actor="admin",
        term="камера на дачу",
        term_type="lead_phrase",
    )
    offer = service.add_offer(
        item.id,
        actor="admin",
        title="Dahua Hero A1",
        price_text="по запросу",
    )
    archived_term = service.archive_term(term.id, actor="admin", reason="too broad")
    archived_offer = service.archive_offer(offer.id, actor="admin", reason="old price")
    archived_item = service.archive_item(updated.id, actor="admin", reason="duplicate")

    assert updated.name == "Dahua Hero A1 Wi-Fi"
    assert archived_term.status == "deprecated"
    assert archived_offer.status == "expired"
    assert archived_item.status == "deprecated"
