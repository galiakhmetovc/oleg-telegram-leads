from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import insert, update

from pur_leads.core.ids import new_id
from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.catalog import extraction_runs_table
from pur_leads.models.evaluation import evaluation_runs_table
from pur_leads.models.notifications import notification_events_table
from pur_leads.models.scheduler import scheduler_jobs_table
from pur_leads.models.telegram_sources import monitored_sources_table, source_access_checks_table
from pur_leads.services.audit import AuditService
from pur_leads.services.evaluation import EvaluationService
from pur_leads.services.scheduler import SchedulerService
from pur_leads.services.web_auth import WebAuthService
from pur_leads.web.app import create_app


def test_operations_routes_require_auth_and_expose_runtime_state(tmp_path):
    fixture = _setup_app(tmp_path)
    client = fixture["client"]
    denied = client.get("/api/operations/summary")

    with fixture["session_factory"]() as session:
        queued_job = SchedulerService(session).enqueue(
            job_type="build_ai_batch",
            scope_type="global",
            payload_json={"value": 1},
        )
        failed_job = SchedulerService(session).enqueue(
            job_type="parse_artifact",
            scope_type="parser",
            payload_json={"source_id": "source-1"},
        )
        session.execute(
            update(scheduler_jobs_table)
            .where(scheduler_jobs_table.c.id == failed_job.id)
            .values(status="failed", last_error="parser missing")
        )
        scheduler = SchedulerService(session)
        run_id = scheduler.start_run(queued_job.id, worker_name="test-worker")
        scheduler.finish_run(run_id, status="succeeded", result_json={"count": 1})
        AuditService(session).record_event(
            event_type="scheduler",
            severity="error",
            message="parser missing",
            entity_type="scheduler_job",
            entity_id=failed_job.id,
        )
        AuditService(session).record_change(
            actor="admin",
            action="settings.update",
            entity_type="setting",
            entity_id="telegram_worker_count",
            old_value_json={"value": 1},
            new_value_json={"value": 2},
        )
        _insert_notification(session, status="suppressed", reason="maybe_web_only")
        _insert_extraction_run(session, status="failed", error="llm timeout")
        _insert_access_check(session, status="flood_wait", error="wait 60s")
        dataset = EvaluationService(session).get_or_create_feedback_regression_dataset(
            created_by="test"
        )
        failed_evaluation = EvaluationService(session).start_run(
            evaluation_dataset_id=dataset.id,
            run_type="lead_detection",
            created_by="test",
        )
        session.execute(
            update(evaluation_runs_table)
            .where(evaluation_runs_table.c.id == failed_evaluation.id)
            .values(status="failed", error="quality threshold missed")
        )
        session.commit()

    _login(client)
    summary = client.get("/api/operations/summary").json()
    jobs = client.get("/api/operations/jobs?status=failed").json()
    job_detail = client.get(f"/api/operations/jobs/{queued_job.id}").json()
    events = client.get("/api/operations/events?severity=error").json()
    audit = client.get("/api/operations/audit?action=settings.update").json()
    notifications = client.get("/api/operations/notifications").json()
    extraction_runs = client.get("/api/operations/extraction-runs?status=failed").json()
    access_checks = client.get("/api/operations/access-checks?status=flood_wait").json()
    backup_denied = fixture["anonymous"].post("/api/operations/backups/sqlite")
    backup_response = client.post("/api/operations/backups/sqlite")
    backups = client.get("/api/operations/backups").json()
    restore_response = client.post(
        f"/api/operations/backups/{backup_response.json()['backup']['id']}/dry-run-restore"
    )
    restores = client.get("/api/operations/restores").json()
    summary_after_backup = client.get("/api/operations/summary").json()

    assert denied.status_code == 401
    assert summary["jobs"]["by_status"]["queued"] == 1
    assert summary["jobs"]["by_status"]["failed"] == 1
    assert summary["events"]["by_severity"]["error"] == 1
    assert summary["notifications"]["by_status"]["suppressed"] == 1
    assert summary["extraction_runs"]["by_status"]["failed"] == 1
    assert summary["access_checks"]["by_status"]["flood_wait"] == 1
    assert summary["quality"]["runs"]["by_status"]["failed"] == 1
    assert summary["quality"]["runs"]["recent_failed"][0]["error"] == "quality threshold missed"
    assert jobs["items"][0]["id"] == failed_job.id
    assert jobs["items"][0]["last_error"] == "parser missing"
    assert job_detail["job"]["id"] == queued_job.id
    assert job_detail["runs"][0]["worker_name"] == "test-worker"
    assert job_detail["runs"][0]["result_json"] == {"count": 1}
    assert events["items"][0]["entity_id"] == failed_job.id
    assert audit["items"][0]["action"] == "settings.update"
    assert notifications["items"][0]["suppressed_reason"] == "maybe_web_only"
    assert extraction_runs["items"][0]["error"] == "llm timeout"
    assert extraction_runs["items"][0]["token_usage_json"] == {"prompt_tokens": 100}
    assert access_checks["items"][0]["error"] == "wait 60s"
    assert backup_denied.status_code == 401
    assert backup_response.status_code == 200
    assert backup_response.json()["backup"]["status"] == "verified"
    assert backups["items"][0]["id"] == backup_response.json()["backup"]["id"]
    assert restore_response.status_code == 200
    assert restore_response.json()["restore"]["validation_status"] == "passed"
    assert restores["items"][0]["id"] == restore_response.json()["restore"]["id"]
    assert summary_after_backup["backups"]["by_status"]["verified"] == 1
    assert summary_after_backup["restores"]["by_status"]["completed"] == 1


def test_operations_capacity_route_exposes_worker_recommendation(tmp_path):
    fixture = _setup_app(tmp_path)
    _login(fixture["client"])

    capacity = fixture["client"].get("/api/operations/capacity")

    assert capacity.status_code == 200
    payload = capacity.json()
    assert "worker_capacity" in payload
    assert payload["worker_capacity"]["configured_worker_concurrency"] >= 1
    assert "resource_limited_worker_capacity" in payload["worker_capacity"]
    assert "ai_model_pools" in payload
    assert "telegram_userbot_pools" in payload
    assert "telegram_bot_pools" in payload
    assert "bottlenecks" in payload


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
        "anonymous": TestClient(
            create_app(
                database_path=db_path,
                bootstrap_admin_password="initial-secret",
                bootstrap_admin_password_file=tmp_path / "bootstrap-admin-password.txt",
                telegram_bot_token="telegram-token",
            )
        ),
        "client": TestClient(
            create_app(
                database_path=db_path,
                bootstrap_admin_password="initial-secret",
                bootstrap_admin_password_file=tmp_path / "bootstrap-admin-password.txt",
                backup_path=tmp_path / "backups",
                telegram_bot_token="telegram-token",
            )
        ),
        "session_factory": session_factory,
    }


def _login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/local",
        json={"username": "admin", "password": "initial-secret"},
    )
    assert response.status_code == 200


def _insert_notification(session, *, status: str, reason: str) -> None:
    now = datetime(2026, 4, 29, 12, 0, tzinfo=UTC)
    session.execute(
        insert(notification_events_table).values(
            id=new_id(),
            channel="telegram",
            notification_type="maybe",
            notification_policy="suppressed",
            status=status,
            dedupe_key="lead-notify:test",
            lead_cluster_id=None,
            lead_event_id=None,
            scheduler_job_id=None,
            monitored_source_id=None,
            source_message_id=None,
            target_ref="operator-chat",
            provider_message_id=None,
            suppressed_reason=reason,
            error=None,
            payload_json={"summary": "maybe"},
            created_at=now,
            queued_at=None,
            sent_at=None,
            updated_at=now,
        )
    )
    session.commit()


def _insert_extraction_run(session, *, status: str, error: str) -> None:
    now = datetime(2026, 4, 29, 12, 0, tzinfo=UTC)
    session.execute(
        insert(extraction_runs_table).values(
            id=new_id(),
            run_type="catalog_extraction",
            model="glm-5.1",
            prompt_version="v1",
            catalog_version_id=None,
            started_at=now,
            finished_at=now,
            status=status,
            error=error,
            stats_json={"chunks": 1},
            source_scope_json={"source_id": "source-1"},
            extractor_version="llm-v1",
            candidate_count=0,
            fact_count=0,
            created_catalog_entity_count=0,
            token_usage_json={"prompt_tokens": 100},
        )
    )
    session.commit()


def _insert_access_check(session, *, status: str, error: str) -> None:
    now = datetime(2026, 4, 29, 12, 0, tzinfo=UTC)
    session.execute(
        insert(monitored_sources_table).values(
            id="source-1",
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
        insert(source_access_checks_table).values(
            id=new_id(),
            monitored_source_id="source-1",
            userbot_account_id=None,
            check_type="manual",
            status=status,
            resolved_source_kind="group",
            resolved_telegram_id="123",
            resolved_title="Support chat",
            last_message_id=42,
            can_read_messages=False,
            can_read_history=False,
            flood_wait_seconds=60,
            error=error,
            checked_at=now,
        )
    )
    session.commit()
