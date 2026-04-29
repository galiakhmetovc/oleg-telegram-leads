from fastapi.testclient import TestClient

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.services.evaluation import EvaluationResultInput, EvaluationService
from pur_leads.services.web_auth import WebAuthService
from pur_leads.web.app import create_app


def test_quality_routes_require_auth_and_expose_evaluation_state(tmp_path):
    fixture = _setup_app(tmp_path)
    denied = fixture["anonymous"].get("/api/quality/summary")

    with fixture["session_factory"]() as session:
        service = EvaluationService(session)
        decision = service.record_decision(
            decision_type="lead_detection",
            entity_type="lead_event",
            entity_id="lead-1",
            decision="lead",
            confidence=0.88,
            reason="camera intent",
            created_by="system",
            dedupe_key="lead_detection:lead-1",
        )
        dataset = service.get_or_create_feedback_regression_dataset(created_by="test")
        case = service.create_case(
            evaluation_dataset_id=dataset.id,
            label_source="manual",
            created_by="test",
            message_text="ищу камеру",
            expected_decision="lead",
        )
        run = service.start_run(
            evaluation_dataset_id=dataset.id,
            run_type="lead_detection",
            created_by="test",
            classifier_version_id=None,
            catalog_hash="catalog",
            prompt_hash="prompt",
            model="glm-test",
            settings_hash="settings",
        )
        service.record_result(
            evaluation_run_id=run.id,
            evaluation_case_id=case.id,
            result=EvaluationResultInput(
                decision_record_id=decision.id,
                actual_decision="not_lead",
                passed=False,
                failure_type="false_negative",
                details_json={"reason": "missed camera"},
            ),
        )
        service.complete_run(run.id)

    _login(fixture["client"])
    summary = fixture["client"].get("/api/quality/summary").json()
    datasets = fixture["client"].get("/api/quality/datasets").json()
    cases = fixture["client"].get(f"/api/quality/cases?dataset_id={dataset.id}").json()
    runs = fixture["client"].get("/api/quality/runs?status=completed").json()
    results = fixture["client"].get("/api/quality/results?passed=false").json()
    decisions = fixture["client"].get("/api/quality/decisions?decision_type=lead_detection").json()

    assert denied.status_code == 401
    assert summary["decisions"]["total"] == 1
    assert summary["decisions"]["by_type"]["lead_detection"] == 1
    assert summary["datasets"]["by_type"]["feedback_regression"] == 1
    assert summary["cases"]["by_label_source"]["manual"] == 1
    assert summary["runs"]["by_status"]["completed"] == 1
    assert summary["results"]["failed"] == 1
    assert summary["results"]["failure_types"]["false_negative"] == 1
    assert datasets["items"][0]["dataset_key"] == "feedback_regression:lead_detection"
    assert cases["items"][0]["expected_decision"] == "lead"
    assert runs["items"][0]["metrics_json"]["failed"] == 1
    assert results["items"][0]["failure_type"] == "false_negative"
    assert decisions["items"][0]["reason"] == "camera intent"


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
