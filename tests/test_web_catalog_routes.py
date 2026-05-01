from fastapi.testclient import TestClient
from sqlalchemy import select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.audit import audit_log_table
from pur_leads.models.catalog import (
    catalog_candidates_table,
    catalog_items_table,
    catalog_offers_table,
    catalog_terms_table,
    classifier_examples_table,
    classifier_versions_table,
    manual_inputs_table,
    parsed_chunks_table,
    sources_table,
)
from pur_leads.models.evaluation import evaluation_cases_table, evaluation_datasets_table
from pur_leads.models.scheduler import scheduler_jobs_table
from pur_leads.models.telegram_sources import source_messages_table
from pur_leads.services.catalog_candidates import CatalogCandidateService
from pur_leads.services.catalog_sources import CatalogSourceService
from pur_leads.services.scheduler import SchedulerService
from pur_leads.services.telegram_sources import TelegramSourceService
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


def test_manual_catalog_item_routes_create_edit_archive_and_rebuild_snapshot(tmp_path):
    fixture = _setup_catalog_app(tmp_path)
    client = fixture["client"]

    denied_response = client.get("/api/catalog/items")
    _login(client)
    create_response = client.post(
        "/api/catalog/items",
        json={
            "name": "Домофоны Bas-IP",
            "item_type": "product",
            "category_slug": "intercom",
            "description": "Черные минималистичные домофоны",
            "terms": [
                {"term": "bas-ip", "term_type": "alias"},
                {"term": "нужен черный домофон", "term_type": "lead_phrase"},
            ],
            "offers": [{"title": "Подбор домофона", "price_text": "по запросу"}],
            "evidence": {
                "quote": "Нужен минималистичный черный домофон",
                "source_text": "Нужен минималистичный черный домофон",
                "source_url": "https://t.me/chat_mila_kolpakova/716254",
            },
        },
    )
    item_id = create_response.json()["item"]["id"]
    term_id = create_response.json()["terms"][0]["id"]
    offer_id = create_response.json()["offers"][0]["id"]
    list_response = client.get("/api/catalog/items")
    detail_response = client.get(f"/api/catalog/items/{item_id}")
    edit_response = client.patch(
        f"/api/catalog/items/{item_id}",
        json={"name": "Домофоны Bas-IP для проектов", "description": "Обновлено вручную"},
    )
    archive_term_response = client.delete(f"/api/catalog/terms/{term_id}")
    archive_offer_response = client.delete(f"/api/catalog/offers/{offer_id}")
    snapshot_response = client.post(
        "/api/catalog/snapshots/rebuild",
        json={"reason": "manual baseline"},
    )

    assert denied_response.status_code == 401
    assert create_response.status_code == 200
    assert create_response.json()["item"]["status"] == "approved"
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["name"] == "Домофоны Bas-IP"
    assert detail_response.status_code == 200
    assert detail_response.json()["terms"][0]["term"] == "bas-ip"
    assert detail_response.json()["offers"][0]["title"] == "Подбор домофона"
    assert detail_response.json()["evidence"][0]["quote"] == "Нужен минималистичный черный домофон"
    assert edit_response.status_code == 200
    assert edit_response.json()["item"]["name"] == "Домофоны Bas-IP для проектов"
    assert archive_term_response.status_code == 200
    assert archive_term_response.json()["term"]["status"] == "deprecated"
    assert archive_offer_response.status_code == 200
    assert archive_offer_response.json()["offer"]["status"] == "expired"
    assert snapshot_response.status_code == 200
    assert snapshot_response.json()["classifier_snapshot"]["version"] == 1

    with fixture["session_factory"]() as session:
        assert session.execute(select(catalog_items_table)).mappings().one()["status"] == "approved"
        assert session.execute(select(catalog_terms_table)).mappings().all()[0]["status"] == (
            "deprecated"
        )
        assert session.execute(select(catalog_offers_table)).mappings().one()["status"] == (
            "expired"
        )
        assert session.execute(select(classifier_versions_table)).mappings().one()["version"] == 1


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


def test_manual_catalog_input_saves_raw_source_without_automatic_extraction_job(tmp_path):
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
    assert payload["queued_jobs"] == []
    with fixture["session_factory"]() as session:
        manual_input = session.execute(select(manual_inputs_table)).mappings().one()
        source = session.execute(select(sources_table)).mappings().one()
        chunks = session.execute(select(parsed_chunks_table)).mappings().all()
        jobs = session.execute(select(scheduler_jobs_table)).mappings().all()
    assert manual_input["processing_status"] == "processed"
    assert source["raw_text"] == "Dahua Hero A1 - поворотная Wi-Fi камера для дома"
    assert chunks == []
    assert jobs == []


def test_catalog_raw_ingest_routes_show_received_messages_artifacts_and_chunks(tmp_path):
    fixture = _setup_catalog_app(tmp_path)
    client = fixture["client"]
    source_message_id = _create_raw_catalog_ingest_sample(fixture["session_factory"])

    denied_response = client.get("/api/catalog/raw-ingest")
    _login(client)
    list_response = client.get("/api/catalog/raw-ingest")
    detail_response = client.get(f"/api/catalog/raw-ingest/messages/{source_message_id}")

    assert denied_response.status_code == 401
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["summary"] == {
        "catalog_sources": 1,
        "messages": 1,
        "mirrored_sources": 1,
        "artifacts": 1,
        "parsed_chunks": 2,
        "pending_jobs": 1,
    }
    assert payload["sources"][0]["message_count"] == 1
    assert payload["sources"][0]["raw_source_count"] == 1
    assert payload["sources"][0]["chunk_count"] == 2
    assert payload["sources"][0]["artifact_count"] == 1
    assert payload["sources"][0]["pending_job_count"] == 1
    assert payload["messages"][0]["id"] == source_message_id
    assert payload["messages"][0]["telegram_message_id"] == 41
    assert payload["messages"][0]["text_excerpt"] == "Dahua Hero A1 camera PDF catalog"
    assert payload["messages"][0]["raw_source"]["origin"] == "telegram:purmaster"
    assert payload["messages"][0]["raw_source"]["chunk_count"] == 2
    assert payload["messages"][0]["raw_source"]["artifact_count"] == 1
    assert payload["messages"][0]["pending_jobs"][0]["job_type"] == "download_artifact"

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["message"]["id"] == source_message_id
    assert detail["message"]["message_url"] == "https://t.me/purmaster/41"
    assert detail["monitored_source"]["input_ref"] == "https://t.me/purmaster"
    assert detail["raw_source"]["raw_text"] == "Dahua Hero A1 camera PDF catalog"
    assert detail["artifacts"][0]["file_name"] == "catalog.pdf"
    assert [chunk["chunk_index"] for chunk in detail["chunks"]] == [0, 1]
    assert detail["chunks"][0]["text"] == "Dahua Hero A1 camera"
    assert detail["jobs"][0]["job_type"] == "download_artifact"
    assert detail["jobs"][0]["status"] == "queued"


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


def _create_raw_catalog_ingest_sample(session_factory) -> str:
    with session_factory() as session:
        telegram_source = TelegramSourceService(session).create_draft(
            "https://t.me/purmaster",
            purpose="catalog_ingestion",
            added_by="admin",
        )
        telegram_source = TelegramSourceService(session).activate(
            telegram_source.id,
            actor="admin",
        )
        raw_source = CatalogSourceService(session).upsert_source(
            source_type="telegram_message",
            origin="telegram:purmaster",
            external_id="41",
            raw_text="Dahua Hero A1 camera PDF catalog",
            url="https://t.me/purmaster/41",
            title="purmaster #41",
            metadata_json={
                "monitored_source_id": telegram_source.id,
                "telegram_message_id": 41,
                "source_purpose": "catalog_ingestion",
            },
        )
        CatalogSourceService(session).replace_parsed_chunks(
            raw_source.id,
            chunks=["Dahua Hero A1 camera", "PDF catalog"],
            parser_name="telegram-message-text",
            parser_version="1",
        )
        CatalogSourceService(session).record_artifact(
            raw_source.id,
            artifact_type="document",
            file_name="catalog.pdf",
            mime_type="application/pdf",
            file_size=1234,
            local_path="/tmp/catalog.pdf",
            download_status="downloaded",
        )
        source_message_id = "source-message-41"
        session.execute(
            source_messages_table.insert().values(
                id=source_message_id,
                monitored_source_id=telegram_source.id,
                raw_source_id=raw_source.id,
                telegram_message_id=41,
                sender_id="oleg",
                message_date=raw_source.published_at or raw_source.created_at,
                text="Dahua Hero A1 camera",
                caption="PDF catalog",
                normalized_text="Dahua Hero A1 camera PDF catalog",
                has_media=True,
                media_metadata_json={
                    "type": "MessageMediaDocument",
                    "document": {
                        "file_name": "catalog.pdf",
                        "mime_type": "application/pdf",
                        "file_size": 1234,
                        "downloadable": True,
                    },
                },
                reply_to_message_id=None,
                thread_id=None,
                forward_metadata_json=None,
                raw_metadata_json={},
                fetched_at=raw_source.created_at,
                classification_status="unclassified",
                archive_pointer_id=None,
                is_archived_stub=False,
                text_archived=False,
                caption_archived=False,
                metadata_archived=False,
                created_at=raw_source.created_at,
                updated_at=raw_source.created_at,
            )
        )
        SchedulerService(session).enqueue(
            job_type="download_artifact",
            scope_type="telegram_source",
            scope_id=telegram_source.id,
            monitored_source_id=telegram_source.id,
            source_message_id=source_message_id,
            idempotency_key=f"telegram-document:{source_message_id}",
            payload_json={
                "source_id": raw_source.id,
                "telegram_message_id": 41,
            },
        )
        return source_message_id


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
    app = create_app(
        database_path=db_path,
        bootstrap_admin_password="initial-secret",
        bootstrap_admin_password_file=tmp_path / "bootstrap-admin-password.txt",
        telegram_bot_token="telegram-token",
    )
    return {"client": TestClient(app), "session_factory": session_factory}


def _login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/local",
        json={"username": "admin", "password": "initial-secret"},
    )
    assert response.status_code == 200
