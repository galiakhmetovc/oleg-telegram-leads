from datetime import UTC, datetime

import pytest

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.integrations.catalog.heuristic_extractor import HeuristicCatalogExtractor
from pur_leads.services.catalog_sources import CatalogSourceService


@pytest.fixture
def extractor_session(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        yield session


@pytest.mark.asyncio
async def test_heuristic_extractor_extracts_numbered_service(extractor_session):
    source = CatalogSourceService(extractor_session).upsert_source(
        source_type="telegram_message",
        origin="telegram:purmaster",
        external_id="17",
        raw_text="catalog",
        published_at=datetime(2026, 4, 28, tzinfo=UTC),
    )
    chunk = CatalogSourceService(extractor_session).replace_parsed_chunks(
        source.id,
        chunks=[
            """
            # Что делаем Что получает клиент
            1.1 Управление освещением в
            помещениях
            Установка управляемых выключателей
            Включение/выключение освещения в приложении, с пульта, голосом.
            1.2 Диммирование Установка управляемого диммера
            Плавное включение/выключение.
            """
        ],
        parser_name="test",
        parser_version="1",
    )[0]

    facts = await HeuristicCatalogExtractor(extractor_session).extract_catalog_facts(
        source_id=source.id,
        chunk_id=chunk.id,
        payload={},
    )

    assert [fact.canonical_name for fact in facts] == [
        "Управление освещением в помещениях",
        "Диммирование",
    ]
    first = facts[0]
    assert first.fact_type == "service"
    assert first.candidate_type == "item"
    assert first.value_json["item_type"] == "service"
    assert first.value_json["category_slug"] == "lighting_shades"
    assert first.value_json["source_code"] == "1.1"
    assert first.value_json["terms"] == [
        "Управление освещением в помещениях",
        "освещение",
        "управление освещением",
    ]
    assert first.source_id == source.id
    assert first.chunk_id == chunk.id
    assert "Управление освещением" in (first.evidence_quote or "")


@pytest.mark.asyncio
async def test_heuristic_extractor_extracts_access_solution_and_offer(extractor_session):
    source = CatalogSourceService(extractor_session).upsert_source(
        source_type="telegram_message",
        origin="telegram:purmaster",
        external_id="28",
        raw_text="catalog",
    )
    chunk = CatalogSourceService(extractor_session).replace_parsed_chunks(
        source.id,
        chunks=[
            """
            Типовые решения по автоматизации въездной группы
            Уровень 3 - Начальный
            Принцип работы: Открытие исполнительного механизма методом дозвона.
            Стоимость решения:
            ИТОГО: 85 000руб
            Работы 35000
            Итоговая стоимость решения под ключ от 120 000руб
            """
        ],
        parser_name="test",
        parser_version="1",
    )[0]

    facts = await HeuristicCatalogExtractor(extractor_session).extract_catalog_facts(
        source_id=source.id,
        chunk_id=chunk.id,
        payload={},
    )

    assert [fact.candidate_type for fact in facts] == ["item", "offer"]
    solution = facts[0]
    offer = facts[1]
    assert solution.fact_type == "bundle"
    assert solution.canonical_name == "Автоматизация въездной группы: Уровень 3 - Начальный"
    assert solution.value_json["item_type"] == "solution"
    assert solution.value_json["category_slug"] == "access_control"
    assert "въездная группа" in solution.value_json["terms"]
    assert offer.fact_type == "offer"
    assert offer.candidate_type == "offer"
    assert offer.canonical_name == (
        "Автоматизация въездной группы: Уровень 3 - Начальный - стоимость"
    )
    assert offer.value_json["price_text"] == "от 120 000 руб"
    assert offer.value_json["currency"] == "RUB"
