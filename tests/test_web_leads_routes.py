from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import insert, select

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.catalog import (
    catalog_categories_table,
    catalog_terms_table,
    classifier_snapshot_entries_table,
    classifier_versions_table,
)
from pur_leads.models.leads import feedback_events_table, lead_clusters_table, lead_matches_table
from pur_leads.models.tasks import tasks_table
from pur_leads.models.telegram_sources import monitored_sources_table, source_messages_table
from pur_leads.services.leads import LeadDetectionResult, LeadMatchInput, LeadService
from pur_leads.services.web_auth import WebAuthService
from pur_leads.web.app import create_app


def test_leads_api_requires_auth_and_returns_queue_detail_with_filters(tmp_path):
    fixture = _setup_app(tmp_path)
    client = fixture["client"]

    assert client.get("/api/leads").status_code == 401
    _login(client)

    response = client.get("/api/leads", params={"auto_pending": "true", "operator_issues": "true"})
    detail_response = client.get(f"/api/leads/{fixture['cluster_id']}")

    assert response.status_code == 200
    rows = response.json()["items"]
    assert [row["cluster_id"] for row in rows] == [fixture["cluster_id"]]
    assert rows[0]["primary_message"]["text"] == "нужна камера на дачу"
    assert rows[0]["has_auto_pending"] is True
    assert rows[0]["category"]["name"] == "Video"
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["cluster"]["cluster_id"] == fixture["cluster_id"]
    assert detail["cluster"]["primary_sender_id"] == "sender-1"
    assert detail["cluster"]["merge_strategy"] == "none"
    assert detail["cluster"]["crm_candidate_count"] == 0
    assert [entry["kind"] for entry in detail["timeline"]] == ["message", "event"]
    assert detail["events"][0]["classifier_version_id"] == fixture["classifier_version_id"]
    assert detail["events"][0]["message_url"] == "https://t.me/test/100"
    assert detail["matches"][0]["status_at_detection"] == "auto_pending"


def test_lead_actions_take_into_work_not_lead_and_feedback(tmp_path):
    fixture = _setup_app(tmp_path)
    client = fixture["client"]
    _login(client)

    take_response = client.post(
        f"/api/leads/{fixture['cluster_id']}/actions",
        json={"action": "take_into_work"},
    )
    rejected_response = client.post(
        f"/api/leads/{fixture['second_cluster_id']}/actions",
        json={"action": "not_lead"},
    )
    not_lead_response = client.post(
        f"/api/leads/{fixture['second_cluster_id']}/actions",
        json={"action": "not_lead", "reason_code": "no_buying_intent"},
    )
    match_feedback_response = client.post(
        "/api/feedback",
        json={
            "target_type": "lead_match",
            "target_id": fixture["match_id"],
            "action": "wrong_product_or_term",
            "reason_code": "wrong_product_or_term",
            "feedback_scope": "classifier",
            "learning_effect": "match_correction",
        },
    )
    commercial_response = client.post(
        "/api/feedback",
        json={
            "target_type": "lead_cluster",
            "target_id": fixture["cluster_id"],
            "action": "commercial_too_expensive",
        },
    )

    assert take_response.status_code == 200
    assert take_response.json()["task"]["status"] == "open"
    assert rejected_response.status_code == 400
    assert not_lead_response.status_code == 200
    assert match_feedback_response.status_code == 200
    assert commercial_response.status_code == 200

    session_factory = fixture["session_factory"]
    with session_factory() as session:
        cluster = (
            session.execute(
                select(lead_clusters_table).where(lead_clusters_table.c.id == fixture["cluster_id"])
            )
            .mappings()
            .one()
        )
        second_cluster = (
            session.execute(
                select(lead_clusters_table).where(
                    lead_clusters_table.c.id == fixture["second_cluster_id"]
                )
            )
            .mappings()
            .one()
        )
        task = session.execute(select(tasks_table)).mappings().one()
        feedback_rows = session.execute(select(feedback_events_table)).mappings().all()
    assert cluster["cluster_status"] == "in_work"
    assert cluster["primary_task_id"] == task["id"]
    assert second_cluster["cluster_status"] == "not_lead"
    assert any(row["target_type"] == "lead_match" for row in feedback_rows)
    assert any(
        row["action"] == "commercial_too_expensive"
        and row["feedback_scope"] == "crm_outcome"
        and row["learning_effect"] == "no_classifier_learning"
        for row in feedback_rows
    )


def test_lead_operational_actions_and_narrow_feedback_targets(tmp_path):
    fixture = _setup_app(tmp_path)
    client = fixture["client"]
    _login(client)

    missing_snooze_response = client.post(
        f"/api/leads/{fixture['second_cluster_id']}/actions",
        json={"action": "snooze"},
    )
    maybe_response = client.post(
        f"/api/leads/{fixture['second_cluster_id']}/actions",
        json={"action": "maybe"},
    )
    snooze_response = client.post(
        f"/api/leads/{fixture['second_cluster_id']}/actions",
        json={"action": "snooze", "snoozed_until": "2026-05-01T09:30:00"},
    )
    duplicate_response = client.post(
        f"/api/leads/{fixture['second_cluster_id']}/actions",
        json={"action": "duplicate", "duplicate_of_cluster_id": fixture["cluster_id"]},
    )
    context_response = client.post(
        f"/api/leads/{fixture['cluster_id']}/actions",
        json={
            "action": "context_only",
            "lead_event_id": fixture["lead_event_id"],
            "reason_code": "context_only",
        },
    )
    invalid_correction_response = client.post(
        "/api/feedback",
        json={
            "target_type": "lead_match",
            "target_id": fixture["match_id"],
            "action": "wrong_category",
            "applied_entity_type": "category",
        },
    )
    term_feedback_response = client.post(
        f"/api/feedback/term/{fixture['term_id']}",
        json={
            "action": "term_too_broad",
            "reason_code": "term_too_broad",
            "feedback_scope": "classifier",
            "learning_effect": "term_review",
        },
    )
    category_feedback_response = client.post(
        f"/api/feedback/category/{fixture['category_id']}",
        json={
            "action": "wrong_category",
            "reason_code": "wrong_category",
            "feedback_scope": "classifier",
            "learning_effect": "match_correction",
        },
    )

    assert missing_snooze_response.status_code == 400
    assert maybe_response.status_code == 200
    assert snooze_response.status_code == 200
    assert duplicate_response.status_code == 200
    assert context_response.status_code == 200
    assert invalid_correction_response.status_code == 400
    assert term_feedback_response.status_code == 200
    assert category_feedback_response.status_code == 200

    with fixture["session_factory"]() as session:
        feedback_rows = session.execute(select(feedback_events_table)).mappings().all()
    assert any(row["action"] == "maybe" for row in feedback_rows)
    assert any(row["action"] == "snooze" for row in feedback_rows)
    assert any(row["action"] == "duplicate" for row in feedback_rows)
    assert any(row["action"] == "mark_context_only" for row in feedback_rows)
    assert any(
        row["target_type"] == "catalog_term"
        and row["target_id"] == fixture["term_id"]
        and row["action"] == "term_too_broad"
        for row in feedback_rows
    )
    assert any(
        row["target_type"] == "category"
        and row["target_id"] == fixture["category_id"]
        and row["action"] == "wrong_category"
        for row in feedback_rows
    )


def test_feedback_routes_validate_auth_targets_and_enum_fields(tmp_path):
    fixture = _setup_app(tmp_path)
    client = fixture["client"]

    unauth_action_response = client.post(
        f"/api/leads/{fixture['cluster_id']}/actions",
        json={"action": "take_into_work"},
    )
    unauth_feedback_response = client.post(
        "/api/feedback",
        json={
            "target_type": "lead_cluster",
            "target_id": fixture["cluster_id"],
            "action": "commercial_too_expensive",
        },
    )
    unauth_target_feedback_response = client.post(
        f"/api/feedback/term/{fixture['term_id']}",
        json={"action": "term_too_broad"},
    )
    _login(client)

    unknown_cluster_response = client.post(
        "/api/feedback",
        json={
            "target_type": "lead_cluster",
            "target_id": new_id(),
            "action": "commercial_too_expensive",
        },
    )
    unknown_term_response = client.post(
        f"/api/feedback/term/{new_id()}",
        json={"action": "term_too_broad", "reason_code": "term_too_broad"},
    )
    invalid_status_response = client.post(
        "/api/feedback",
        json={
            "target_type": "lead_cluster",
            "target_id": fixture["cluster_id"],
            "action": "commercial_too_expensive",
            "application_status": "bad_status",
        },
    )
    applied_status_response = client.post(
        "/api/feedback",
        json={
            "target_type": "lead_cluster",
            "target_id": fixture["cluster_id"],
            "action": "commercial_too_expensive",
            "application_status": "applied",
            "applied_entity_type": "lead_cluster",
            "applied_entity_id": fixture["cluster_id"],
        },
    )
    invalid_scope_effect_response = client.post(
        "/api/feedback",
        json={
            "target_type": "lead_cluster",
            "target_id": fixture["cluster_id"],
            "action": "commercial_too_expensive",
            "feedback_scope": "not_a_scope",
            "learning_effect": "not_an_effect",
        },
    )

    assert unauth_action_response.status_code == 401
    assert unauth_feedback_response.status_code == 401
    assert unauth_target_feedback_response.status_code == 401
    assert unknown_cluster_response.status_code == 404
    assert unknown_term_response.status_code == 404
    assert invalid_status_response.status_code == 400
    assert applied_status_response.status_code == 400
    assert invalid_scope_effect_response.status_code == 400


def _setup_app(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        admin = WebAuthService(session, telegram_bot_token="telegram-token").ensure_bootstrap_admin(
            username="admin",
            password="initial-secret",
        )
        source_id = _insert_monitored_source(session)
        category_id = _insert_category(session)
        term_id = _insert_term(session, category_id)
        classifier_version_id = _insert_classifier_version(session)
        snapshot_entry_id = _insert_snapshot_entry(
            session,
            classifier_version_id,
            category_id=category_id,
            term_id=term_id,
        )
        first_event, first_cluster = _create_clustered_event(
            session,
            source_id,
            category_id,
            classifier_version_id,
            snapshot_entry_id,
            telegram_message_id=100,
            sender_id="sender-1",
        )
        _, second_cluster = _create_clustered_event(
            session,
            source_id,
            category_id,
            classifier_version_id,
            None,
            telegram_message_id=101,
            sender_id="sender-2",
        )
        match_id = session.execute(
            select(lead_matches_table.c.id).where(
                lead_matches_table.c.lead_event_id == first_event.id
            )
        ).scalar_one()
        session.commit()
        return {
            "client": TestClient(
                create_app(database_path=db_path, telegram_bot_token="telegram-token")
            ),
            "session_factory": session_factory,
            "admin_id": admin.id,
            "cluster_id": first_cluster.id,
            "second_cluster_id": second_cluster.id,
            "lead_event_id": first_event.id,
            "category_id": category_id,
            "term_id": term_id,
            "classifier_version_id": classifier_version_id,
            "match_id": match_id,
        }


def _login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/local",
        json={"username": "admin", "password": "initial-secret"},
    )
    assert response.status_code == 200


def _create_clustered_event(
    session,
    source_id: str,
    category_id: str,
    classifier_version_id: str,
    snapshot_entry_id: str | None,
    *,
    telegram_message_id: int,
    sender_id: str,
):
    message_id = _insert_source_message(
        session,
        source_id,
        telegram_message_id=telegram_message_id,
        sender_id=sender_id,
    )
    service = LeadService(session)
    event = service.record_detection(
        source_message_id=message_id,
        classifier_version_id=classifier_version_id,
        result=LeadDetectionResult(
            decision="lead",
            detection_mode="live",
            confidence=0.9,
            commercial_value_score=0.7,
            negative_score=0.05,
            reason="User asks for a camera",
            matches=[
                LeadMatchInput(
                    classifier_snapshot_entry_id=snapshot_entry_id,
                    catalog_term_id="term-1",
                    category_id=category_id,
                    match_type="term",
                    matched_text="камера",
                    score=0.9,
                )
            ],
        ),
    )
    cluster = service.assign_event_to_cluster(event.id, window_minutes=60)
    return event, cluster


def _insert_monitored_source(session) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(monitored_sources_table).values(
            id=row_id,
            source_kind="telegram_supergroup",
            input_ref="@test",
            source_purpose="lead_monitoring",
            priority="normal",
            status="active",
            lead_detection_enabled=True,
            catalog_ingestion_enabled=False,
            phase_enabled=True,
            start_mode="from_now",
            historical_backfill_policy="retro_web_only",
            poll_interval_seconds=60,
            added_by="test",
            created_at=now,
            updated_at=now,
        )
    )
    return row_id


def _insert_category(session) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(catalog_categories_table).values(
            id=row_id,
            parent_id=None,
            slug="video",
            name="Video",
            description=None,
            status="approved",
            sort_order=1,
            created_at=now,
            updated_at=now,
        )
    )
    return row_id


def _insert_term(session, category_id: str) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(catalog_terms_table).values(
            id=row_id,
            item_id=None,
            category_id=category_id,
            term="камера",
            normalized_term="камера",
            term_type="keyword",
            language="ru",
            status="approved",
            weight=1.0,
            created_by="test",
            first_seen_source_id=None,
            created_at=now,
            updated_at=now,
        )
    )
    return row_id


def _insert_source_message(
    session,
    source_id: str,
    *,
    telegram_message_id: int,
    sender_id: str,
) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(source_messages_table).values(
            id=row_id,
            monitored_source_id=source_id,
            telegram_message_id=telegram_message_id,
            sender_id=sender_id,
            message_date=datetime(2026, 4, 28, 12, telegram_message_id % 50, 0),
            text="нужна камера на дачу",
            caption=None,
            normalized_text="нужна камера на дачу",
            has_media=False,
            media_metadata_json=None,
            reply_to_message_id=None,
            thread_id=None,
            forward_metadata_json=None,
            raw_metadata_json={},
            fetched_at=now,
            classification_status="unclassified",
            archive_pointer_id=None,
            is_archived_stub=False,
            text_archived=False,
            caption_archived=False,
            metadata_archived=False,
            created_at=now,
            updated_at=now,
        )
    )
    return row_id


def _insert_classifier_version(session) -> str:
    row_id = new_id()
    session.execute(
        insert(classifier_versions_table).values(
            id=row_id,
            version=1,
            created_at=utc_now(),
            created_by="test",
            included_statuses_json=["approved", "auto_pending"],
            catalog_hash="catalog",
            example_hash="example",
            prompt_hash="prompt",
            keyword_index_hash="keyword",
            settings_hash="settings",
        )
    )
    return row_id


def _insert_snapshot_entry(
    session,
    classifier_version_id: str,
    *,
    category_id: str,
    term_id: str,
) -> str:
    row_id = new_id()
    session.execute(
        insert(classifier_snapshot_entries_table).values(
            id=row_id,
            classifier_version_id=classifier_version_id,
            entry_type="term",
            entity_type="term",
            entity_id=term_id,
            status_at_build="auto_pending",
            weight=1.5,
            text_value="камера",
            normalized_value="камера",
            metadata_json={"category_id": category_id},
            content_hash="hash",
            created_at=utc_now(),
        )
    )
    return row_id
