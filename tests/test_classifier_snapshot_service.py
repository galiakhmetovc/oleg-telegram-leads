from sqlalchemy import insert, select

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.catalog import (
    catalog_attributes_table,
    catalog_candidates_table,
    catalog_items_table,
    catalog_offers_table,
    catalog_terms_table,
    classifier_examples_table,
    classifier_snapshot_entries_table,
    classifier_version_artifacts_table,
    classifier_versions_table,
)
from pur_leads.services.catalog import CatalogService
from pur_leads.services.classifier_snapshots import ClassifierSnapshotService


def test_build_classifier_snapshot_includes_allowed_catalog_entries(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        service = CatalogService(session)
        service.seed_initial_categories()
        category_id = service.repository.find_category_by_slug("video_surveillance").id  # type: ignore[union-attr]
        item_id = _insert_item(session, category_id, status="auto_pending")
        rejected_item_id = _insert_item(
            session, category_id, name="Rejected", canonical_name="Rejected", status="rejected"
        )
        term_id = _insert_term(session, item_id, category_id, status="approved")
        attribute_id = _insert_attribute(session, item_id, status="auto_pending")
        offer_id = _insert_offer(session, item_id, category_id, status="approved")
        example_id = _insert_example(session, item_id, term_id, status="active")
        _insert_term(session, rejected_item_id, category_id, term="bad", status="rejected")

        snapshot = ClassifierSnapshotService(session).build_snapshot(
            created_by="system",
            model="glm-test",
            settings_snapshot={"include_auto_pending": True},
        )

        entries = session.execute(select(classifier_snapshot_entries_table)).mappings().all()
        artifacts = session.execute(select(classifier_version_artifacts_table)).mappings().all()
        version = session.execute(select(classifier_versions_table)).mappings().one()
        identities = {(row["entry_type"], row["entity_id"]) for row in entries}
        assert snapshot.version == 1
        assert version["model"] == "glm-test"
        assert ("item", item_id) in identities
        assert ("term", term_id) in identities
        assert ("attribute", attribute_id) in identities
        assert ("offer", offer_id) in identities
        assert ("example", example_id) in identities
        assert ("item", rejected_item_id) not in identities
        assert {artifact["artifact_type"] for artifact in artifacts} == {
            "catalog_prompt",
            "keyword_index",
            "settings_snapshot",
            "token_estimate",
        }
        assert all(len(row["content_hash"]) == 64 for row in entries)


def test_build_classifier_snapshot_includes_auto_pending_candidate_terms(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        candidate_id = _insert_candidate(
            session,
            canonical_name="Видеонаблюдение",
            status="auto_pending",
            normalized_value_json={
                "item_type": "service",
                "category_slug": "video_surveillance",
                "terms": ["видеонаблюдение", "камера на дачу"],
            },
        )
        rejected_candidate_id = _insert_candidate(
            session,
            canonical_name="Rejected camera",
            status="rejected",
            normalized_value_json={"terms": ["не использовать"]},
        )

        snapshot = ClassifierSnapshotService(session).build_snapshot(created_by="system")

        entries = session.execute(select(classifier_snapshot_entries_table)).mappings().all()
        artifacts = session.execute(select(classifier_version_artifacts_table)).mappings().all()
    candidate_entries = [row for row in entries if row["entity_type"] == "catalog_candidate"]
    assert snapshot.version == 1
    assert {(row["entry_type"], row["entity_id"]) for row in candidate_entries} == {
        ("candidate", candidate_id),
        ("candidate_term", candidate_id),
    }
    assert {row["normalized_value"] for row in candidate_entries} == {
        "видеонаблюдение",
        "камера на дачу",
    }
    assert all(row["entity_id"] != rejected_candidate_id for row in candidate_entries)
    keyword_index = next(
        artifact["content_json"]
        for artifact in artifacts
        if artifact["artifact_type"] == "keyword_index"
    )
    assert "камера на дачу" in {entry["term"] for entry in keyword_index}


def _insert_item(
    session,
    category_id: str,
    *,
    name: str = "Dahua Hero A1",
    canonical_name: str = "Dahua Hero A1",
    status: str,
) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(catalog_items_table).values(
            id=row_id,
            category_id=category_id,
            item_type="product",
            name=name,
            canonical_name=canonical_name,
            description="Camera",
            status=status,
            confidence=0.9,
            first_seen_source_id=None,
            first_seen_at=now,
            last_seen_at=now,
            created_by="test",
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    return row_id


def _insert_term(
    session,
    item_id: str,
    category_id: str,
    *,
    term: str = "Hero A1",
    status: str,
) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(catalog_terms_table).values(
            id=row_id,
            item_id=item_id,
            category_id=category_id,
            term=term,
            normalized_term=term.casefold(),
            term_type="alias",
            language="ru",
            status=status,
            weight=1.0,
            created_by="test",
            first_seen_source_id=None,
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    return row_id


def _insert_attribute(session, item_id: str, *, status: str) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(catalog_attributes_table).values(
            id=row_id,
            item_id=item_id,
            attribute_name="resolution",
            attribute_value="2MP",
            value_type="text",
            unit=None,
            status=status,
            valid_from=None,
            valid_to=None,
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    return row_id


def _insert_offer(session, item_id: str, category_id: str, *, status: str) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(catalog_offers_table).values(
            id=row_id,
            item_id=item_id,
            category_id=category_id,
            offer_type="price",
            title="Hero A1 price",
            description=None,
            price_amount=2500,
            currency="RUB",
            price_text="2500 RUB",
            terms_json=None,
            status=status,
            valid_from=None,
            valid_to=None,
            ttl_days=30,
            ttl_source="default_setting",
            first_seen_source_id=None,
            last_seen_source_id=None,
            last_seen_at=now,
            expired_at=None,
            created_by="test",
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    return row_id


def _insert_example(session, item_id: str, term_id: str, *, status: str) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(classifier_examples_table).values(
            id=row_id,
            example_type="lead_positive",
            polarity="positive",
            status=status,
            source_message_id=None,
            raw_source_id=None,
            lead_cluster_id=None,
            lead_event_id=None,
            category_id=None,
            catalog_item_id=item_id,
            catalog_term_id=term_id,
            reason_code=None,
            example_text="Нужна камера на дачу",
            context_json=None,
            weight=1.0,
            created_from="manual_input",
            created_by="test",
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    return row_id


def _insert_candidate(
    session,
    *,
    canonical_name: str,
    status: str,
    normalized_value_json: dict,
) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(catalog_candidates_table).values(
            id=row_id,
            candidate_type="item",
            proposed_action="create",
            canonical_name=canonical_name,
            normalized_value_json=normalized_value_json,
            source_count=1,
            evidence_count=1,
            confidence=0.8,
            status=status,
            target_entity_type=None,
            target_entity_id=None,
            merge_target_candidate_id=None,
            first_seen_at=now,
            last_seen_at=now,
            created_by="system",
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    return row_id
