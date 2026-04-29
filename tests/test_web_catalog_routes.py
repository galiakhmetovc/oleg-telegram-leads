from fastapi.testclient import TestClient
from sqlalchemy import select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.audit import audit_log_table
from pur_leads.models.catalog import (
    catalog_candidates_table,
    catalog_items_table,
    classifier_examples_table,
    classifier_versions_table,
    manual_inputs_table,
    parsed_chunks_table,
    sources_table,
)
from pur_leads.models.evaluation import evaluation_cases_table, evaluation_datasets_table
from pur_leads.models.scheduler import scheduler_jobs_table
from pur_leads.services.catalog_candidates import CatalogCandidateService
from pur_leads.services.catalog_sources import CatalogSourceService
from pur_leads.services.web_auth import WebAuthService
from pur_leads.web.app import create_app


def test_catalog_candidate_routes_list_and_approve_item(tmp_path):
    fixture = _setup_catalog_app(tmp_path)
    client = fixture["client"]
    candidate_id = _create_item_candidate(fixture["session_factory"])

    denied_response = client.get("/api/catalog/candidates")
    _login(client)
    list_response = client.get("/api/catalog/candidates?status=auto_pending")
    approve_response = client.post(
        f"/api/catalog/candidates/{candidate_id}/review",
        json={"action": "approve", "reason": "Looks right"},
    )

    assert denied_response.status_code == 401
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["id"] == candidate_id
    assert list_response.json()["items"][0]["canonical_name"] == "Видеонаблюдение"
    assert list_response.json()["items"][0]["normalized_value"]["category_slug"] == (
        "video_surveillance"
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["candidate"]["status"] == "approved"
    assert approve_response.json()["promotion"]["entity_type"] == "item"

    with fixture["session_factory"]() as session:
        candidate = session.execute(select(catalog_candidates_table)).mappings().one()
        item = session.execute(select(catalog_items_table)).mappings().one()
        audit_actions = {
            row["action"] for row in session.execute(select(audit_log_table)).mappings().all()
        }
    assert candidate["status"] == "approved"
    assert item["canonical_name"] == "Видеонаблюдение"
    assert "catalog_candidate.review" in audit_actions


def test_catalog_candidate_routes_reject_candidate_without_promotion(tmp_path):
    fixture = _setup_catalog_app(tmp_path)
    client = fixture["client"]
    candidate_id = _create_item_candidate(fixture["session_factory"])
    _login(client)

    response = client.post(
        f"/api/catalog/candidates/{candidate_id}/review",
        json={"action": "reject", "reason": "Noisy extraction"},
    )

    assert response.status_code == 200
    assert response.json()["candidate"]["status"] == "rejected"
    assert response.json()["promotion"] is None
    with fixture["session_factory"]() as session:
        assert session.execute(select(catalog_items_table)).mappings().all() == []


def test_catalog_candidate_detail_returns_evidence_source_and_chunk(tmp_path):
    fixture = _setup_catalog_app(tmp_path)
    client = fixture["client"]
    candidate_id = _create_item_candidate(fixture["session_factory"])

    denied_response = client.get(f"/api/catalog/candidates/{candidate_id}")
    _login(client)
    response = client.get(f"/api/catalog/candidates/{candidate_id}")

    assert denied_response.status_code == 401
    assert response.status_code == 200
    payload = response.json()
    assert payload["candidate"]["id"] == candidate_id
    assert payload["candidate"]["normalized_value"]["category_slug"] == "video_surveillance"
    assert payload["evidence"][0]["quote"] == "5.1 Видеонаблюдение"
    assert payload["evidence"][0]["source"]["origin"] == "telegram:purmaster"
    assert payload["evidence"][0]["source"]["external_id"] == "17"
    assert payload["evidence"][0]["source"]["raw_text_excerpt"] == "Видеонаблюдение"
    assert payload["evidence"][0]["chunk"]["text"] == (
        "5.1 Видеонаблюдение Установка камер наблюдения"
    )


def test_catalog_candidate_routes_edit_candidate_before_approval(tmp_path):
    fixture = _setup_catalog_app(tmp_path)
    client = fixture["client"]
    candidate_id = _create_item_candidate(fixture["session_factory"])
    _login(client)

    edit_response = client.patch(
        f"/api/catalog/candidates/{candidate_id}",
        json={
            "canonical_name": "Камеры и видеонаблюдение",
            "normalized_value": {
                "item_type": "service",
                "category_slug": "video_surveillance",
                "terms": ["камеры", "видеонаблюдение"],
                "description": "Установка камер и настройка просмотра",
            },
            "reason": "Clean up extracted title",
        },
    )
    approve_response = client.post(
        f"/api/catalog/candidates/{candidate_id}/review",
        json={"action": "approve"},
    )

    assert edit_response.status_code == 200
    assert edit_response.json()["candidate"]["canonical_name"] == "Камеры и видеонаблюдение"
    assert edit_response.json()["candidate"]["normalized_value"]["terms"] == [
        "камеры",
        "видеонаблюдение",
    ]
    assert approve_response.status_code == 200
    assert approve_response.json()["promotion"]["entity_type"] == "item"
    with fixture["session_factory"]() as session:
        item = session.execute(select(catalog_items_table)).mappings().one()
        audit_actions = [
            row["action"] for row in session.execute(select(audit_log_table)).mappings().all()
        ]
    assert item["canonical_name"] == "Камеры и видеонаблюдение"
    assert "catalog_candidate.update" in audit_actions
    assert "catalog_candidate.review" in audit_actions


def test_manual_catalog_input_creates_source_chunk_and_extraction_job(tmp_path):
    fixture = _setup_catalog_app(tmp_path)
    client = fixture["client"]

    denied_response = client.post(
        "/api/catalog/manual-inputs",
        json={"input_type": "catalog_note", "text": "Dahua", "evidence_note": "test"},
    )
    _login(client)

    response = client.post(
        "/api/catalog/manual-inputs",
        json={
            "input_type": "catalog_note",
            "text": "Dahua Hero A1 - поворотная Wi-Fi камера для дома",
            "evidence_note": "Олег добавил вручную",
        },
    )

    assert denied_response.status_code == 401
    assert response.status_code == 200
    payload = response.json()
    assert payload["manual_input"]["input_type"] == "catalog_note"
    assert payload["source"]["source_type"] == "manual_text"
    assert len(payload["queued_jobs"]) == 1
    with fixture["session_factory"]() as session:
        manual_input = session.execute(select(manual_inputs_table)).mappings().one()
        source = session.execute(select(sources_table)).mappings().one()
        chunk = session.execute(select(parsed_chunks_table)).mappings().one()
        job = session.execute(select(scheduler_jobs_table)).mappings().one()
    assert manual_input["processing_status"] == "processed"
    assert source["raw_text"] == "Dahua Hero A1 - поворотная Wi-Fi камера для дома"
    assert chunk["source_id"] == source["id"]
    assert chunk["text"] == "Dahua Hero A1 - поворотная Wi-Fi камера для дома"
    assert job["job_type"] == "extract_catalog_facts"
    assert job["priority"] == "low"
    assert job["payload_json"]["source_id"] == source["id"]
    assert job["payload_json"]["chunk_id"] == chunk["id"]
    assert job["payload_json"]["manual_input_id"] == manual_input["id"]


def test_manual_lead_example_creates_classifier_example_snapshot_and_evaluation_case(tmp_path):
    fixture = _setup_catalog_app(tmp_path)
    client = fixture["client"]
    _login(client)

    response = client.post(
        "/api/catalog/manual-inputs",
        json={
            "input_type": "lead_example",
            "text": "Ищу камеру на дачу с просмотром через телефон",
            "evidence_note": "Пример лида от Олега",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["classifier_example"]["polarity"] == "positive"
    assert payload["evaluation_case"]["expected_decision"] == "lead"
    assert payload["evaluation_case"]["label_source"] == "manual"
    assert payload["classifier_snapshot"]["version"] == 1
    with fixture["session_factory"]() as session:
        source = session.execute(select(sources_table)).mappings().one()
        example = session.execute(select(classifier_examples_table)).mappings().one()
        snapshot = session.execute(select(classifier_versions_table)).mappings().one()
        dataset = session.execute(select(evaluation_datasets_table)).mappings().one()
        evaluation_case = session.execute(select(evaluation_cases_table)).mappings().one()
    assert example["raw_source_id"] == source["id"]
    assert example["example_type"] == "lead_positive"
    assert example["example_text"] == "Ищу камеру на дачу с просмотром через телефон"
    assert example["status"] == "active"
    assert dataset["dataset_key"] == "manual_examples:lead_detection"
    assert dataset["dataset_type"] == "golden"
    assert evaluation_case["source_id"] == source["id"]
    assert evaluation_case["message_text"] == "Ищу камеру на дачу с просмотром через телефон"
    assert evaluation_case["expected_decision"] == "lead"
    assert evaluation_case["context_json"]["manual_input_id"] == payload["manual_input"]["id"]
    assert evaluation_case["context_json"]["classifier_example_id"] == example["id"]
    assert snapshot["created_by"] == "admin"


def test_manual_non_lead_and_maybe_examples_create_expected_evaluation_cases(tmp_path):
    fixture = _setup_catalog_app(tmp_path)
    client = fixture["client"]
    _login(client)

    non_lead_response = client.post(
        "/api/catalog/manual-inputs",
        json={
            "input_type": "non_lead_example",
            "text": "Подскажите, какую камеру лучше взять, покупать не планирую",
            "evidence_note": "Пример не лида от Олега",
        },
    )
    maybe_response = client.post(
        "/api/catalog/manual-inputs",
        json={
            "input_type": "maybe_example",
            "text": "Думаю поставить видеонаблюдение, пока изучаю варианты",
            "evidence_note": "Пограничный пример от Олега",
        },
    )

    assert non_lead_response.status_code == 200
    assert maybe_response.status_code == 200
    assert non_lead_response.json()["classifier_example"]["polarity"] == "negative"
    assert non_lead_response.json()["evaluation_case"]["expected_decision"] == "not_lead"
    assert maybe_response.json()["classifier_example"]["polarity"] == "neutral"
    assert maybe_response.json()["evaluation_case"]["expected_decision"] == "maybe"
    with fixture["session_factory"]() as session:
        examples = session.execute(select(classifier_examples_table)).mappings().all()
        cases = session.execute(select(evaluation_cases_table)).mappings().all()
    assert [example["example_type"] for example in examples] == ["lead_negative", "maybe"]
    assert [case["expected_decision"] for case in cases] == ["not_lead", "maybe"]


def test_manual_telegram_link_parses_chat_and_message_identity(tmp_path):
    fixture = _setup_catalog_app(tmp_path)
    client = fixture["client"]
    _login(client)

    response = client.post(
        "/api/catalog/manual-inputs",
        json={
            "input_type": "telegram_link",
            "url": "https://t.me/purmaster/42",
            "evidence_note": "Источник от Олега",
        },
    )

    assert response.status_code == 200
    with fixture["session_factory"]() as session:
        manual_input = session.execute(select(manual_inputs_table)).mappings().one()
        source = session.execute(select(sources_table)).mappings().one()
    assert manual_input["chat_ref"] == "purmaster"
    assert manual_input["message_id"] == 42
    assert source["source_type"] == "manual_link"
    assert source["origin"] == "purmaster"
    assert source["external_id"] == "42"


def _create_item_candidate(session_factory) -> str:
    with session_factory() as session:
        source = CatalogSourceService(session).upsert_source(
            source_type="telegram_message",
            origin="telegram:purmaster",
            external_id="17",
            raw_text="Видеонаблюдение",
        )
        chunk = CatalogSourceService(session).replace_parsed_chunks(
            source.id,
            chunks=["5.1 Видеонаблюдение Установка камер наблюдения"],
            parser_name="test",
            parser_version="1",
        )[0]
        candidates = CatalogCandidateService(session)
        run = candidates.start_extraction_run(
            run_type="catalog_extraction",
            extractor_version="test",
            source_scope_json={"source_id": source.id, "chunk_id": chunk.id},
        )
        fact = candidates.create_extracted_fact(
            extraction_run_id=run.id,
            fact_type="service",
            canonical_name="Видеонаблюдение",
            value_json={
                "item_type": "service",
                "category_slug": "video_surveillance",
                "terms": ["Видеонаблюдение", "камеры наблюдения"],
            },
            confidence=0.9,
            source_id=source.id,
            chunk_id=chunk.id,
        )
        candidate = candidates.create_or_update_candidate_from_fact(
            fact.id,
            candidate_type="item",
            evidence_quote="5.1 Видеонаблюдение",
            created_by="system",
        )
        return candidate.id


def _setup_catalog_app(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        WebAuthService(session, telegram_bot_token="telegram-token").ensure_bootstrap_admin(
            username="admin",
            password="initial-secret",
        )
    app = create_app(database_path=db_path, telegram_bot_token="telegram-token")
    return {"client": TestClient(app), "session_factory": session_factory}


def _login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/local",
        json={"username": "admin", "password": "initial-secret"},
    )
    assert response.status_code == 200
