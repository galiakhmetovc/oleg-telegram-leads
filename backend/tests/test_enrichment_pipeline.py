from pathlib import Path
from typing import TypedDict

from app.infrastructure.nlp.config_loader import load_nlp_config
from app.infrastructure.nlp.russian_text_enricher import RussianTextEnricher


class FollowUpLeadCase(TypedDict):
    id: str
    text: str
    signals: set[str]
    facts: set[str]
    areas: set[str]
    segments: set[str]
    temperatures: set[str]


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


def test_default_config_marks_smart_home_value_evaluation_family_apartment_lead_text() -> None:
    config = load_nlp_config(Path("config/nlp"))
    enricher = RussianTextEnricher(config)
    text = (
        "Вопрос от заказчиков: а посоветуйте, надо ли нам умный дом? В квартиру. "
        "Родители и двое детей. У меня как-то до этого все сами знали, надо им "
        "или не надо. Радиаторы не меняем. Кондиционеры - обычный один на "
        "солнечной стороне. На технику с вай фай, вероятно, бюджета не хватит. "
        "В общем, КОМУ и ЗАЧЕМ нужен умный дом. Какие плюшки? Моими сложными "
        "и многочисленными сценариями освещения управлять?"
    )

    result = enricher.enrich(text)

    signal_types = {signal.type for signal in result.domain_signals}
    fact_types = {fact.type for fact in result.facts}

    assert "smart_home_automation" in signal_types
    assert "smart_home_value_question" in signal_types
    assert "budget_constraint" in signal_types
    assert "family_apartment_context" in signal_types
    assert "lighting_control" in signal_types
    assert "solution_area" in fact_types
    assert "property_type" in fact_types
    assert "controlled_device" in fact_types
    assert result.lead_assessment is not None
    assert result.lead_assessment.is_lead is True
    assert result.lead_assessment.temperature in {"warm", "hot"}
    assert "smart_home" in {item.type for item in result.lead_assessment.solution_areas}
    segment_types = {item.type for item in result.lead_assessment.customer_segments}
    assert "family_residential" in segment_types
    assert "research_project" in segment_types
    assert "renovation_project" not in segment_types


def test_default_config_marks_follow_up_pur_leads_with_specific_explanations() -> None:
    config = load_nlp_config(Path("config/nlp"))
    enricher = RussianTextEnricher(config)
    cases: list[FollowUpLeadCase] = [
        {
            "id": "children_audio_wiring",
            "text": (
                "Ну вот и я думаю, для детской в принципе той же Алисы или JBL "
                "по блютус хватит? Это детская, звука большого не надо, про "
                "приставку есть сомнения, сейчас дети маленькие, а потом "
                "потребуют) Наверно единственное на что нужен кабель канал - "
                "ноут подключить? То есть можно вывести внизу где то аккуратную "
                "розетку с ним?"
            ),
            "signals": {"smart_home_automation"},
            "facts": {"automation_component", "controlled_device", "wiring_output"},
            "areas": {"smart_home"},
            "segments": set(),
            "temperatures": {"warm"},
        },
        {
            "id": "leak_sensor_outputs",
            "text": (
                "Здравствуйте, сантехнический вопрос) Все клиенты постоянно "
                "просят делать по разному и я уже запуталась… Есть устройство "
                "датчиков протечки, которые устанавливают в сантех шкафу, 1 "
                "устройство, и есть датчики протечки, допустим 6 штук, размещены "
                "по квартире. Вопрос в выводах. Нужен вывод или розетка для "
                "самого прибора. И все? Или для каждого датчика (6штук) по месту "
                "тоже нужны выводы 220v?"
            ),
            "signals": {"water_leak_protection", "installation_context", "apartment_context"},
            "facts": {"automation_component", "controlled_device", "wiring_output", "property_type"},
            "areas": {"smart_home", "security"},
            "segments": {"private_residential"},
            "temperatures": {"warm", "hot"},
        },
        {
            "id": "commercial_intercom_access_recovery",
            "text": (
                "Добрый вечер, коллеги. Такая проблема: так получилось, что уже "
                "конец ремонта, а на объекте не сделали выводы под домофон. "
                "Коммерческое помещение. Изначально забыла добавить их в проект "
                "( первый раз делала коммерцию, в рамках работы в студии, более "
                "опытные коллеги проверяли, сами не увидели) потом, я увидела "
                "этот момент. И добавила в альбом проекта, отправила в чат с "
                "прорабом. Дальше были еще правки, и у меня это оказалось в "
                "разных файлах. Похоже пдф сохранила, а сам файл нет с выводами "
                "на домофон. Еще мне никто не напомнил что нужен "
                "электромагнитный замок на входную🤦🏽‍♀️ А я первый раз, вообще "
                "не знала про это. Мой косяк, сейчас думаю какие есть выходы. "
                "Может есть какие то домофоны с вайфаем, кнопку открывания "
                "внутри тоже не вывели. Ну и на сам замок соответсвенно тоже. "
                "Есть вывод снаружи на вывеску"
            ),
            "signals": {"intercom", "access_control", "commercial_object", "need"},
            "facts": {"access_device", "property_type", "wiring_output"},
            "areas": {"security", "access_control"},
            "segments": {"commercial_client"},
            "temperatures": {"hot"},
        },
        {
            "id": "whitebox_smart_home_design",
            "text": (
                "Добрый вечер 💫 поделитесь опытом, пожалуйста. Я впервые "
                "сталкиваюсь с запросом на умный дом (опыт небольшой), как "
                "проектировать дизайн с учетом умного дома? Я так понимаю, что "
                "все оборудование, которое планируется подключать, должно "
                "поддерживать умный дом? Те же карнизы, к примеру Ситуация "
                "усложняется в разы тем, что квартира еще не сдана и будет "
                "white box"
            ),
            "signals": {"smart_home_automation", "education_request", "electrical_design_context"},
            "facts": {"solution_area", "property_type", "controlled_device"},
            "areas": {"smart_home"},
            "segments": {"private_residential", "research_project", "designer_partner"},
            "temperatures": {"warm", "hot"},
        },
        {
            "id": "security_technical_project",
            "text": (
                "Ребята, привет, нужна помощь разработать технический проект, "
                "кто сталкивался и может помочь Проект видеонаблюдения, контроль "
                "доступа, охранная и пожарная сигнализация"
            ),
            "signals": {"video_surveillance", "access_control", "security_alarm", "consultation_request"},
            "facts": {"solution_area", "design_scope"},
            "areas": {"security", "access_control"},
            "segments": {"designer_partner"},
            "temperatures": {"hot"},
        },
        {
            "id": "nanny_cameras_contractor_search",
            "text": (
                "Добрый день! Такой вопрос. Заказчики хотят установить камеры по "
                "всей квартиры, чтобы следить за няней с приложения. Ни разу еще "
                "не ставила. Может, кто-то устанавливал систему видеонаблюдения "
                "Livicom? Или может с другой системой видеонаблюдения работали? "
                "А может вообще кто-то готов поделиться контактами хорошего "
                "подрядчика? СПб. Буду благодарна 🙏"
            ),
            "signals": {"video_surveillance", "provider_search", "customer_intent", "installation_request"},
            "facts": {"solution_area", "property_type", "vendor", "service_location"},
            "areas": {"security"},
            "segments": {"private_residential", "active_request"},
            "temperatures": {"hot"},
        },
        {
            "id": "wifi_electric_curtains",
            "text": (
                "Чаще всего делаю портьеру на электрическом карнизе с Wi-Fi "
                "модулем , а тюль на обычном профильном. Электрические карнизы "
                "бывают разные по типу управления. Для работы с Алисой нужен "
                "такой электрический карниз, у которого есть Wi-Fi подключение. "
                "Если нужно и тюль и портреты на электрических карнизах, то "
                "ставите два карниза: один для тюля, и второй для портер. Оба с "
                "Wi-Fi."
            ),
            "signals": {"smart_home_automation", "electric_curtain_control", "need"},
            "facts": {"automation_component", "controlled_device"},
            "areas": {"smart_home"},
            "segments": set(),
            "temperatures": {"warm", "hot"},
        },
    ]

    for case in cases:
        result = enricher.enrich(case["text"])
        assert result.lead_assessment is not None, case["id"]
        assert result.lead_assessment.is_lead is True, case["id"]
        assert result.lead_assessment.temperature in case["temperatures"], case["id"]
        assert case["signals"] <= {signal.type for signal in result.domain_signals}, case["id"]
        assert case["facts"] <= {fact.type for fact in result.facts}, case["id"]
        assert case["areas"] <= {item.type for item in result.lead_assessment.solution_areas}, case["id"]
        assert case["segments"] <= {item.type for item in result.lead_assessment.customer_segments}, case["id"]


def test_default_config_does_not_mark_diy_equipment_sale_as_lead() -> None:
    config = load_nlp_config(Path("config/nlp"))
    enricher = RussianTextEnricher(config)
    text = "Продам камеру видеонаблюдения без монтажа, самовывоз, дешево."

    result = enricher.enrich(text)

    assert result.lead_assessment is not None
    assert result.lead_assessment.is_lead is False
    assert result.lead_assessment.temperature == "none"
    assert "diy_or_equipment_only" in {item.type for item in result.lead_assessment.noise_signals}
