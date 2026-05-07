from pathlib import Path

from app.infrastructure.nlp.config_loader import load_nlp_config
from app.infrastructure.nlp.russian_text_enricher import RussianTextEnricher


def test_enriches_text_with_configured_domain_signal(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    config_dir.mkdir()
    (config_dir / "pipeline.yaml").write_text(
        """
stages:
  - name: segmentation
    enabled: true
  - name: morph
    enabled: true
  - name: syntax
    enabled: true
  - name: ner
    enabled: true
  - name: domain_signals
    enabled: true
""",
        encoding="utf-8",
    )
    (config_dir / "signals.yaml").write_text(
        """
signals:
  - type: demand
    label: Потребность
    color: "#2e7d32"
    phrases:
      - ["ищем", "поставщика"]
""",
        encoding="utf-8",
    )
    config = load_nlp_config(config_dir)
    enricher = RussianTextEnricher(config)

    result = enricher.enrich("Ищем поставщика в Москве. Нужно 20 тонн до 12 мая.")

    assert result.original_text.startswith("Ищем поставщика")
    assert any(token.lemma == "поставщик" for token in result.tokens)
    assert any(entity.text == "Москве" and entity.type == "LOC" for entity in result.entities)
    assert [
        signal.type for signal in result.domain_signals if signal.text.lower() == "ищем поставщика"
    ] == ["demand"]
    assert result.metrics.token_count > 0
    assert any(item.stage == "domain_signals" for item in result.pipeline_trace)


def test_default_config_marks_smart_home_automation_lead_text() -> None:
    config = load_nlp_config(Path("config/nlp"))
    enricher = RussianTextEnricher(config)
    text = (
        "Всем добрый вечер! Дизайнеры, подскажите, пожалуйста, если заказчик "
        "хочет систему умного дома от яндекс, влияет ли это как-то на чертежи "
        "электрики? Не могу просто понять, нужно ли учесть какие-то нюансы, "
        "что-то добавить на планах розеток или освещения"
    )

    result = enricher.enrich(text)

    signal_types = {signal.type for signal in result.domain_signals}
    fact_types = {fact.type for fact in result.facts}

    assert "smart_home_automation" in signal_types
    assert "customer_intent" in signal_types
    assert "electrical_design_context" in signal_types
    assert "solution_area" in fact_types
    assert "vendor" in fact_types
    assert "design_scope" in fact_types
    assert result.lead_assessment is not None
    assert result.lead_assessment.is_lead is True
    assert result.lead_assessment.temperature in {"warm", "hot"}
    assert "smart_home" in {item.type for item in result.lead_assessment.solution_areas}
    assert "designer_partner" in {item.type for item in result.lead_assessment.customer_segments}


def test_default_config_marks_hot_zigbee_installation_lead_text() -> None:
    config = load_nlp_config(Path("config/nlp"))
    enricher = RussianTextEnricher(config)
    text = (
        "Коллеги, такой запрос от клиента. К кому идти? Посоветуйте контакты "
        "по Москве 🙏🏻\n\nУстановить и подключить zigbee шлюз для управления "
        "через приложение/алису.\n\nСвет, розетки, входной замок, ТВ, "
        "кондиционер, электрокарниз (если будет), система защиты от протечек."
    )

    result = enricher.enrich(text)

    signal_types = {signal.type for signal in result.domain_signals}
    fact_types = {fact.type for fact in result.facts}

    assert "hot_lead_intent" in signal_types
    assert "customer_intent" in signal_types
    assert "provider_search" in signal_types
    assert "installation_request" in signal_types
    assert "smart_home_automation" in signal_types
    assert "service_location" in fact_types
    assert "work_type" in fact_types
    assert "automation_component" in fact_types
    assert "controlled_device" in fact_types
    assert result.lead_assessment is not None
    assert result.lead_assessment.is_lead is True
    assert result.lead_assessment.temperature == "hot"
    assert "smart_home" in {item.type for item in result.lead_assessment.solution_areas}


def test_default_config_marks_video_surveillance_apartment_lead_text() -> None:
    config = load_nlp_config(Path("config/nlp"))
    enricher = RussianTextEnricher(config)
    text = (
        "Подскажите, пожалуйста, где можно заказать систему видеонаблюдения "
        "для квартиры: это просто камера на стену, нужно проконсультироваться "
        "по выводам для нее. Спасибо"
    )

    result = enricher.enrich(text)

    signal_types = {signal.type for signal in result.domain_signals}
    fact_types = {fact.type for fact in result.facts}

    assert "provider_search" in signal_types
    assert "consultation_request" in signal_types
    assert "video_surveillance" in signal_types
    assert "installation_context" in signal_types
    assert "solution_area" in fact_types
    assert "property_type" in fact_types
    assert "automation_component" in fact_types
    assert "installation_surface" in fact_types
    assert "wiring_output" in fact_types
    assert result.lead_assessment is not None
    assert result.lead_assessment.is_lead is True
    assert result.lead_assessment.temperature in {"warm", "hot"}
    assert "security" in {item.type for item in result.lead_assessment.solution_areas}


def test_default_config_marks_water_leak_sensor_design_lead_from_artifact() -> None:
    config = load_nlp_config(Path("config/nlp"))
    enricher = RussianTextEnricher(config)
    text = (
        "Всем привет! Подскажите пожалуйста, когда вы планируете на объекте "
        "спрятать датчик протечки в керамогранит, вы прикладываете на чертежах "
        "схему подробную или просто примечание указываете соответствующее, "
        "или с прорабом уже на месте обсуждаете?\n"
        "Хочу реализовать в текущем проекте, хочу понять как отобразить это "
        "решение правильно"
    )

    result = enricher.enrich(text)

    signal_types = {signal.type for signal in result.domain_signals}
    fact_types = {fact.type for fact in result.facts}

    assert "consultation_request" in signal_types
    assert "installation_context" in signal_types
    assert "water_leak_protection" in signal_types
    assert "implementation_intent" in signal_types
    assert "automation_component" in fact_types
    assert "installation_surface" in fact_types
    assert "design_scope" in fact_types
    assert result.lead_assessment is not None
    assert result.lead_assessment.is_lead is True
    assert result.lead_assessment.temperature in {"warm", "hot"}
    assert "smart_home" in {item.type for item in result.lead_assessment.solution_areas}


def test_default_config_marks_developer_smart_home_modification_lead_text() -> None:
    config = load_nlp_config(Path("config/nlp"))
    enricher = RussianTextEnricher(config)
    text = (
        "Добрый день! Коллеги, подскажите, работал ли кто-нибудь с квартирами "
        "с системой умный дом от застройщика? Электрики не хотят брать в работу "
        "такие проекты с добавлением розеток , выключателей, опасаются проблем "
        "с системой ; а застройщик говорит- если что-то в схему добавить, "
        "слетает гарантия. Выход только хоронить умный дом и делать все с нуля?😬"
    )

    result = enricher.enrich(text)

    signal_types = {signal.type for signal in result.domain_signals}
    fact_types = {fact.type for fact in result.facts}

    assert "smart_home_automation" in signal_types
    assert "developer_smart_home_context" in signal_types
    assert "renovation_modification_context" in signal_types
    assert "warranty_risk" in signal_types
    assert "apartment_context" in signal_types
    assert "solution_area" in fact_types
    assert "property_type" in fact_types
    assert "design_scope" in fact_types
    assert "controlled_device" in fact_types
    assert result.lead_assessment is not None
    assert result.lead_assessment.is_lead is True
    assert result.lead_assessment.temperature in {"warm", "hot"}
    assert "smart_home" in {item.type for item in result.lead_assessment.solution_areas}
    segment_types = {item.type for item in result.lead_assessment.customer_segments}
    assert "renovation_project" in segment_types
    assert "private_residential" in segment_types
    assert "commercial_client" not in segment_types


def test_default_config_marks_smart_home_solution_selection_learning_lead_text() -> None:
    config = load_nlp_config(Path("config/nlp"))
    enricher = RussianTextEnricher(config)
    text = (
        'Здравствуйте друзья. Подскажите какие действительно нужные и полезные '
        'системы "умного дома" можно внедрить в проект? Раньше вообще с этим '
        "не сталеивался. Где можно изучить эту тему?"
    )

    result = enricher.enrich(text)

    signal_types = {signal.type for signal in result.domain_signals}
    fact_types = {fact.type for fact in result.facts}

    assert "smart_home_automation" in signal_types
    assert "solution_selection_request" in signal_types
    assert "education_request" in signal_types
    assert "consultation_request" in signal_types
    assert "solution_area" in fact_types
    assert "work_type" in fact_types
    assert result.lead_assessment is not None
    assert result.lead_assessment.is_lead is True
    assert result.lead_assessment.temperature in {"warm", "hot"}
    assert "smart_home" in {item.type for item in result.lead_assessment.solution_areas}
    assert "research_project" in {item.type for item in result.lead_assessment.customer_segments}


def test_default_config_does_not_mark_diy_equipment_sale_as_lead() -> None:
    config = load_nlp_config(Path("config/nlp"))
    enricher = RussianTextEnricher(config)
    text = "Продам камеру видеонаблюдения без монтажа, самовывоз, дешево."

    result = enricher.enrich(text)

    assert result.lead_assessment is not None
    assert result.lead_assessment.is_lead is False
    assert result.lead_assessment.temperature == "none"
    assert "diy_or_equipment_only" in {item.type for item in result.lead_assessment.noise_signals}
