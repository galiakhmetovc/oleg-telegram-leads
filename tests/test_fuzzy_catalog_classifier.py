from datetime import UTC, datetime

import pytest
from sqlalchemy import insert

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.integrations.leads.fuzzy_classifier import FuzzyCatalogLeadClassifier
from pur_leads.models.catalog import catalog_candidates_table
from pur_leads.services.classifier_snapshots import ClassifierSnapshotService
from pur_leads.workers.runtime import LeadMessageForClassification


@pytest.mark.asyncio
async def test_fuzzy_catalog_classifier_uses_latest_snapshot_for_lead_maybe_and_not_lead(
    tmp_path,
):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        _insert_candidate(
            session,
            canonical_name="Видеонаблюдение",
            terms=["камера", "видеонаблюдение"],
        )
        snapshot = ClassifierSnapshotService(session).build_snapshot(created_by="system")
        classifier = FuzzyCatalogLeadClassifier(session)

        results = await classifier.classify_message_batch(
            messages=[
                _message("message-1", "Нужна камера на дачу"),
                _message("message-2", "Обсуждали камеру Dahua в соседнем чате"),
                _message("message-3", "Спасибо, вопрос закрыт"),
            ],
            payload={},
        )

    assert [result.source_message_id for result in results] == [
        "message-1",
        "message-2",
        "message-3",
    ]
    assert [result.decision for result in results] == ["lead", "maybe", "not_lead"]
    assert all(result.classifier_version_id == snapshot.id for result in results)
    assert results[0].detection_mode == "live"
    assert results[0].confidence > results[1].confidence
    assert results[0].matches[0].matched_text == "камера"
    assert results[0].matches[0].classifier_snapshot_entry_id is not None
    assert results[1].notify_reason == "operator_review_required"
    assert results[2].matches == []


@pytest.mark.asyncio
async def test_fuzzy_catalog_classifier_flags_generic_equipment_request_without_catalog_match(
    tmp_path,
):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        classifier = FuzzyCatalogLeadClassifier(session)

        results = await classifier.classify_message_batch(
            messages=[
                _message(
                    "message-1",
                    "Какие домофоны ставите в проекты? Нужен минималистичный черный экран.",
                )
            ],
            payload={},
        )

    assert len(results) == 1
    assert results[0].decision == "lead"
    assert results[0].notify_reason == "generic_equipment_request"
    assert results[0].reason == "Detected buying intent for equipment outside catalog terms"
    assert results[0].matches == []


def _message(source_message_id: str, text: str) -> LeadMessageForClassification:
    return LeadMessageForClassification(
        source_message_id=source_message_id,
        monitored_source_id="source-1",
        telegram_message_id=1,
        sender_id="sender-1",
        message_date=datetime(2026, 4, 28, tzinfo=UTC),
        message_text=text,
        normalized_text=text.casefold(),
    )


def _insert_candidate(session, *, canonical_name: str, terms: list[str]) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(catalog_candidates_table).values(
            id=row_id,
            candidate_type="item",
            proposed_action="create",
            canonical_name=canonical_name,
            normalized_value_json={
                "item_type": "service",
                "category_slug": "video_surveillance",
                "terms": terms,
            },
            source_count=1,
            evidence_count=1,
            confidence=0.8,
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
    session.commit()
    return row_id
