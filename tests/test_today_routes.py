from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import insert, select

from pur_leads.core.ids import new_id
from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.audit import audit_log_table
from pur_leads.models.catalog import catalog_candidates_table
from pur_leads.models.crm import contact_reasons_table
from pur_leads.models.leads import lead_clusters_table
from pur_leads.models.tasks import tasks_table
from pur_leads.models.telegram_sources import monitored_sources_table, source_messages_table
from pur_leads.repositories.tasks import TaskRepository
from pur_leads.services.audit import AuditService
from pur_leads.services.crm import CrmService
from pur_leads.services.today import TodayService
from pur_leads.services.web_auth import WebAuthService
from pur_leads.web.app import create_app


def test_today_routes_require_auth_and_expose_daily_work(tmp_path):
    fixture = _setup_app(tmp_path)
    client = fixture["client"]
    now = datetime(2026, 4, 29, 12, 0, tzinfo=UTC)

    assert client.get("/api/today").status_code == 401

    with fixture["session_factory"]() as session:
        lead_cluster_id = _insert_lead_cluster(session, now=now)
        profile = CrmService(session).create_client_profile(
            actor="admin",
            display_name="Ivan",
            contacts=[{"telegram_username": "ivan"}],
            contact_reasons=[
                {
                    "title": "New camera is available",
                    "reason_text": "Client looked for this camera earlier",
                    "priority": "high",
                    "status": "new",
                    "due_at": now + timedelta(hours=1),
                }
            ],
            support_cases=[
                {
                    "title": "Camera offline",
                    "status": "new",
                    "priority": "urgent",
                    "issue_text": "Existing client needs help",
                }
            ],
        )
        contact_reason_id = profile.contact_reasons[0].id
        task = TaskRepository(session).create(
            client_id=profile.client.id,
            lead_cluster_id=lead_cluster_id,
            lead_event_id=None,
            opportunity_id=None,
            support_case_id=None,
            contact_reason_id=None,
            title="Call Ivan",
            description="Discuss camera",
            status="open",
            priority="high",
            due_at=now - timedelta(days=1),
            owner_user_id=None,
            assignee_user_id=None,
            created_at=now,
            updated_at=now,
            completed_at=None,
        )
        _insert_catalog_candidate(session, now=now)
        AuditService(session).record_event(
            event_type="scheduler",
            severity="error",
            message="worker failed",
            entity_type="scheduler_job",
            entity_id="job-1",
        )
        session.commit()

    _login(client)
    summary = client.get("/api/today").json()
    complete_response = client.post(f"/api/today/tasks/{task.id}/complete")
    snooze_response = client.post(
        f"/api/today/contact-reasons/{contact_reason_id}/snooze",
        json={"snoozed_until": "2026-04-30T09:00:00Z"},
    )
    done_response = client.post(f"/api/today/contact-reasons/{contact_reason_id}/done")
    create_task_response = client.post(
        "/api/today/tasks",
        json={
            "title": "Prepare quote",
            "description": "Camera kit estimate",
            "priority": "normal",
            "due_at": "2026-04-29T16:00:00Z",
            "client_id": profile.client.id,
        },
    )

    assert summary["counts"]["new_leads"] == 1
    assert summary["counts"]["due_tasks"] == 1
    assert summary["counts"]["overdue_tasks"] == 1
    assert summary["counts"]["contact_reasons"] == 1
    assert summary["counts"]["support_cases"] == 1
    assert summary["counts"]["catalog_candidates"] == 1
    assert summary["counts"]["operational_issues"] == 1
    assert summary["leads"][0]["cluster_id"] == lead_cluster_id
    assert summary["tasks"][0]["title"] == "Call Ivan"
    assert summary["contact_reasons"][0]["client"]["display_name"] == "Ivan"
    assert summary["support_cases"][0]["priority"] == "urgent"
    assert summary["catalog_candidates"][0]["canonical_name"] == "Dahua Hero A1"
    assert summary["operational_issues"][0]["message"] == "worker failed"
    assert complete_response.status_code == 200
    assert complete_response.json()["task"]["status"] == "done"
    assert snooze_response.status_code == 200
    assert snooze_response.json()["contact_reason"]["status"] == "snoozed"
    assert done_response.status_code == 200
    assert done_response.json()["contact_reason"]["status"] == "done"
    assert create_task_response.status_code == 200
    assert create_task_response.json()["task"]["title"] == "Prepare quote"

    with fixture["session_factory"]() as session:
        stored_task = (
            session.execute(select(tasks_table).where(tasks_table.c.id == task.id)).mappings().one()
        )
        stored_reason = (
            session.execute(
                select(contact_reasons_table).where(contact_reasons_table.c.id == contact_reason_id)
            )
            .mappings()
            .one()
        )
        audit_actions = [
            row["action"] for row in session.execute(select(audit_log_table)).mappings().all()
        ]
    assert stored_task["status"] == "done"
    assert stored_reason["status"] == "done"
    assert "today.task_completed" in audit_actions
    assert "today.contact_reason_snoozed" in audit_actions
    assert "today.contact_reason_done" in audit_actions


def test_today_summary_counts_are_not_capped_by_render_limit(tmp_path):
    fixture = _setup_app(tmp_path)
    now = datetime(2026, 4, 29, 12, 0, tzinfo=UTC)

    with fixture["session_factory"]() as session:
        profile = CrmService(session).create_client_profile(
            actor="admin",
            display_name="Ivan",
        )
        for index in range(2):
            TaskRepository(session).create(
                client_id=profile.client.id,
                lead_cluster_id=None,
                lead_event_id=None,
                opportunity_id=None,
                support_case_id=None,
                contact_reason_id=None,
                title=f"Task {index}",
                description=None,
                status="open",
                priority="normal",
                due_at=now,
                owner_user_id=None,
                assignee_user_id=None,
                created_at=now,
                updated_at=now,
                completed_at=None,
            )
            _insert_catalog_candidate(session, now=now, name=f"Dahua Hero A{index}")
            AuditService(session).record_event(
                event_type="scheduler",
                severity="error",
                message=f"worker failed {index}",
                entity_type="scheduler_job",
                entity_id=f"job-{index}",
            )

        summary = TodayService(session).summary(now=now, limit=1)

    assert len(summary["tasks"]) == 1
    assert summary["counts"]["due_tasks"] == 2
    assert len(summary["catalog_candidates"]) == 1
    assert summary["counts"]["catalog_candidates"] == 2
    assert len(summary["operational_issues"]) == 1
    assert summary["counts"]["operational_issues"] == 2


def _setup_app(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        WebAuthService(session, telegram_bot_token="telegram-token").ensure_bootstrap_admin(
            username="admin",
            password="initial-secret",
        )
    return {
        "client": TestClient(
            create_app(database_path=db_path, telegram_bot_token="telegram-token")
        ),
        "session_factory": session_factory,
    }


def _login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/local",
        json={"username": "admin", "password": "initial-secret"},
    )
    assert response.status_code == 200


def _insert_lead_cluster(session, *, now: datetime) -> str:
    source_id = new_id()
    message_id = new_id()
    cluster_id = new_id()
    session.execute(
        insert(monitored_sources_table).values(
            id=source_id,
            source_kind="telegram_group",
            telegram_id="123",
            username="support",
            title="Support chat",
            invite_link_hash=None,
            input_ref="@support",
            source_purpose="lead_monitoring",
            assigned_userbot_account_id=None,
            priority="normal",
            status="active",
            lead_detection_enabled=True,
            catalog_ingestion_enabled=False,
            phase_enabled=True,
            start_mode="from_now",
            start_message_id=None,
            start_recent_limit=None,
            start_recent_days=None,
            historical_backfill_policy="manual",
            checkpoint_message_id=None,
            checkpoint_date=None,
            last_preview_at=None,
            preview_message_count=None,
            next_poll_at=None,
            poll_interval_seconds=60,
            last_success_at=None,
            last_error_at=None,
            last_error=None,
            added_by="admin",
            activated_by="admin",
            activated_at=now,
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        insert(source_messages_table).values(
            id=message_id,
            monitored_source_id=source_id,
            raw_source_id=None,
            telegram_message_id=100,
            sender_id="sender-1",
            message_date=now,
            text="нужна камера на дачу",
            caption=None,
            normalized_text="нужна камера на дачу",
            has_media=False,
            media_metadata_json=None,
            reply_to_message_id=None,
            thread_id=None,
            forward_metadata_json=None,
            raw_metadata_json=None,
            fetched_at=now,
            classification_status="classified",
            archive_pointer_id=None,
            is_archived_stub=False,
            text_archived=False,
            caption_archived=False,
            metadata_archived=False,
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        insert(lead_clusters_table).values(
            id=cluster_id,
            monitored_source_id=source_id,
            chat_id="123",
            primary_sender_id="sender-1",
            primary_sender_name="Ivan",
            primary_lead_event_id=None,
            primary_source_message_id=message_id,
            category_id=None,
            summary="Camera request",
            cluster_status="new",
            review_status="unreviewed",
            work_outcome="none",
            first_message_at=now,
            last_message_at=now,
            message_count=1,
            lead_event_count=1,
            confidence_max=0.9,
            commercial_value_score_max=0.8,
            negative_score_min=0.1,
            dedupe_key="lead:test",
            merge_strategy="none",
            merge_reason=None,
            last_notified_at=None,
            notify_update_count=0,
            snoozed_until=None,
            duplicate_of_cluster_id=None,
            primary_task_id=None,
            converted_entity_type=None,
            converted_entity_id=None,
            crm_candidate_count=0,
            crm_conversion_action_id=None,
            created_at=now,
            updated_at=now,
        )
    )
    return cluster_id


def _insert_catalog_candidate(
    session,
    *,
    now: datetime,
    name: str = "Dahua Hero A1",
) -> None:
    session.execute(
        insert(catalog_candidates_table).values(
            id=new_id(),
            candidate_type="item",
            proposed_action="create",
            canonical_name=name,
            normalized_value_json={"item_type": "product"},
            source_count=1,
            evidence_count=1,
            confidence=0.91,
            status="auto_pending",
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
