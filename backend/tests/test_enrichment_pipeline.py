from pathlib import Path
from typing import TypedDict

from pytest import MonkeyPatch

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


def test_reuses_compiled_yargy_parsers_between_enrichments(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    config_dir = tmp_path / "nlp"
    config_dir.mkdir()
    (config_dir / "pipeline.yaml").write_text(
        """
stages:
  - name: segmentation
    enabled: true
  - name: facts
    enabled: true
  - name: domain_signals
    enabled: true
""",
        encoding="utf-8",
    )
    (config_dir / "signals.yaml").write_text(
        """
signals:
  - type: smart_home
    label: Умный дом
    patterns:
      - tokens:
          - normalized: "умный"
          - normalized: "дом"
""",
        encoding="utf-8",
    )
    (config_dir / "facts.yaml").write_text(
        """
facts:
  - type: solution_area
    label: Направление
    patterns:
      - tokens:
          - normalized: "умный"
          - normalized: "дом"
""",
        encoding="utf-8",
    )

    import app.infrastructure.nlp.russian_text_enricher as enricher_module

    parser_calls = 0
    original_parser = getattr(enricher_module, "Parser")

    def counting_parser(*args: object, **kwargs: object) -> object:
        nonlocal parser_calls
        parser_calls += 1
        return original_parser(*args, **kwargs)

    monkeypatch.setattr(enricher_module, "Parser", counting_parser)

    config = load_nlp_config(config_dir)
    enricher = RussianTextEnricher(config)
    enricher.enrich("Заказчик хочет умный дом.")
    enricher.enrich("Нужен умный дом.")

    assert parser_calls == 2


def test_enriches_text_with_alias_catalog_signals_and_facts(tmp_path: Path) -> None:
    config_dir = tmp_path / "nlp"
    config_dir.mkdir()
    (config_dir / "pipeline.yaml").write_text(
        """
stages:
  - name: segmentation
    enabled: true
  - name: facts
    enabled: true
  - name: domain_signals
    enabled: true
  - name: lead_scoring
    enabled: true
""",
        encoding="utf-8",
    )
    (config_dir / "signals.yaml").write_text("signals: []\n", encoding="utf-8")
    (config_dir / "facts.yaml").write_text("facts: []\n", encoding="utf-8")
    (config_dir / "lead_scoring.yaml").write_text(
        """
lead_scoring:
  thresholds:
    lead: 35
    warm: 55
    hot: 80
  weights:
    signals:
      smart_home_platform: 20
      protocol_gateway: 20
      water_leak_protection: 25
    facts:
      vendor: 5
      protocol: 5
      automation_component: 10
      software: 5
  solution_areas:
    smart_home:
      label: Умный дом / автоматизация
      signal_types:
        - smart_home_platform
        - protocol_gateway
        - water_leak_protection
      fact_types:
        - automation_component
  customer_segments: {}
  intent_signal_types:
    - smart_home_platform
    - protocol_gateway
    - water_leak_protection
  noise_signal_types: []
""",
        encoding="utf-8",
    )
    (config_dir / "vendors.yaml").write_text(
        """
vendors:
  - key: aqara
    canonical: Aqara
    type: vendor
    aliases:
      - Aqara
      - Акара
    signal_types:
      - smart_home_platform
    fact_types:
      - vendor
""",
        encoding="utf-8",
    )
    (config_dir / "protocols.yaml").write_text(
        """
protocols:
  - key: zigbee
    canonical: Zigbee
    type: protocol
    aliases:
      - Zigbee
      - Зигби
    signal_types:
      - protocol_gateway
    fact_types:
      - protocol
""",
        encoding="utf-8",
    )
    (config_dir / "devices.yaml").write_text(
        """
devices:
  - key: leak_sensor
    canonical: Датчик протечки
    type: device
    aliases:
      - датчик протечки
      - датчики протечки
    signal_types:
      - water_leak_protection
    fact_types:
      - automation_component
  - key: relay
    canonical: Реле
    type: device
    aliases:
      - реле
    signal_types:
      - protocol_gateway
    fact_types:
      - automation_component
""",
        encoding="utf-8",
    )
    (config_dir / "software.yaml").write_text(
        """
software:
  - key: alice
    canonical: Алиса
    type: software
    aliases:
      - Алиса
    signal_types:
      - smart_home_platform
    fact_types:
      - software
""",
        encoding="utf-8",
    )

    result = RussianTextEnricher(load_nlp_config(config_dir)).enrich(
        "Клиент хочет Aqara, Zigbee реле, датчики протечки и Алиса."
    )

    signal_types = {signal.type for signal in result.domain_signals}
    fact_types = {fact.type for fact in result.facts}
    assert {"smart_home_platform", "protocol_gateway", "water_leak_protection"} <= signal_types
    assert {"vendor", "protocol", "automation_component", "software"} <= fact_types
    assert any(signal.source == "alias_catalog" for signal in result.domain_signals)
    assert any(fact.text == "Aqara" and fact.source == "alias_catalog" for fact in result.facts)
    assert result.lead_assessment is not None
    assert result.lead_assessment.is_lead is True
    assert "smart_home" in {item.type for item in result.lead_assessment.solution_areas}


def test_default_config_detects_curated_rf_cis_smart_home_aliases() -> None:
    config = load_nlp_config(Path("config/nlp"))
    enricher = RussianTextEnricher(config)
    text = (
        "Нужно подобрать Aqara Hub M3 или Яндекс Хаб для датчиков протечки "
        "Нептун, Zigbee реле Sonoff, сценариев в Home Assistant и управления "
        "через Алису. Клиент еще спрашивает про Wiren Board и Tuya Smart Life."
    )

    result = enricher.enrich(text)

    signal_types = {signal.type for signal in result.domain_signals}
    fact_types = {fact.type for fact in result.facts}
    matched_texts = {fact.text.casefold() for fact in result.facts}
    assert {"smart_home_platform", "protocol_gateway", "water_leak_protection"} <= signal_types
    assert {"vendor", "protocol", "automation_component", "software"} <= fact_types
    assert any(text.startswith("aqara") for text in matched_texts)
    assert {"яндекс", "нептун", "sonoff", "wiren board", "tuya smart life"} <= matched_texts
    assert result.lead_assessment is not None
    assert result.lead_assessment.is_lead is True
    assert result.lead_assessment.temperature in {"warm", "hot"}


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
            "facts": {"solution_area", "property_type"},
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


def test_default_config_marks_latest_motion_relay_and_hvac_leads() -> None:
    config = load_nlp_config(Path("config/nlp"))
    enricher = RussianTextEnricher(config)

    motion_result = enricher.enrich(
        "Коллеги, помогите решить такую задачу. Я хочу сделать в туалете ночной "
        "свет, примерно как ступени лесницы освещают: у пола, и чтобы включалось "
        "оно на движение в определенные часы, а заодно на это и два бра в коридоре "
        "запитать, чтобы при движении ночью они включались. Как реализуется такая "
        "схема или можно ли при этом оставить независимое механическое включение бра?"
    )
    motion_signals = {signal.type for signal in motion_result.domain_signals}
    motion_facts = {fact.type for fact in motion_result.facts}

    assert motion_result.lead_assessment is not None
    assert motion_result.lead_assessment.is_lead is True
    assert motion_result.lead_assessment.temperature in {"warm", "hot"}
    assert {"motion_lighting_automation", "lighting_control", "consultation_request"} <= motion_signals
    assert {"controlled_device", "design_scope"} <= motion_facts
    assert "smart_home" in {item.type for item in motion_result.lead_assessment.solution_areas}

    relay_result = enricher.enrich(
        "Добрый день всем) Подскажите на счет умного дома Яндекс, нашла видео как "
        "подключить через Зигби устройства с пультами к Алисе. А как подключить "
        "свет (бра, треки), клиент говорит, что есть какие то шайбы которые "
        "ставятся на электрику и так же можно подключить к Алисе. Слышали про такое?"
    )
    relay_signals = {signal.type for signal in relay_result.domain_signals}
    relay_facts = {fact.type for fact in relay_result.facts}

    assert relay_result.lead_assessment is not None
    assert relay_result.lead_assessment.is_lead is True
    assert relay_result.lead_assessment.temperature in {"warm", "hot"}
    assert {"smart_home_automation", "smart_relay_control", "lighting_control"} <= relay_signals
    assert {"solution_area", "vendor", "automation_component", "controlled_device"} <= relay_facts
    assert "smart_home" in {item.type for item in relay_result.lead_assessment.solution_areas}

    hvac_result = enricher.enrich(
        "Дизайнеры, добрый день! Подскажите, кто-нибудь работал с камерами "
        "статического давления O’CLIMATE для Ораковских изделий? Хочу сделать "
        "решетки в потолочных карнизах в проекте канального кондиционирования, "
        "инженеры говорят что это не возможно. Или может есть еще какие-то "
        "устройства для Orac."
    )
    hvac_signals = {signal.type for signal in hvac_result.domain_signals}
    hvac_facts = {fact.type for fact in hvac_result.facts}

    assert hvac_result.lead_assessment is not None
    assert hvac_result.lead_assessment.is_lead is True
    assert hvac_result.lead_assessment.temperature in {"warm", "hot"}
    hvac_areas = {item.type for item in hvac_result.lead_assessment.solution_areas}
    assert {"climate_control", "consultation_request", "designer_context"} <= hvac_signals
    assert "video_surveillance" not in hvac_signals
    assert {"solution_area", "vendor", "design_scope"} <= hvac_facts
    assert "climate" in hvac_areas
    assert "security" not in hvac_areas
    assert "designer_partner" in {item.type for item in hvac_result.lead_assessment.customer_segments}


def test_default_config_marks_neptun_water_leak_monitoring_lead() -> None:
    config = load_nlp_config(Path("config/nlp"))
    enricher = RussianTextEnricher(config)

    result = enricher.enrich(
        "Коллеги, подскажите кто ставил систему Нептуп ProW, хочу ее выбрать, "
        "проводные датчик...но в то же время важно чтобы понимать где какой "
        "датчик сработал- то это только на смартфон вывод инфы получается и "
        "уже только система Profi WI-Fi или я ошибаюсь?"
    )

    signal_types = {signal.type for signal in result.domain_signals}
    fact_types = {fact.type for fact in result.facts}

    assert result.lead_assessment is not None
    assert result.lead_assessment.is_lead is True
    assert result.lead_assessment.temperature in {"warm", "hot"}
    assert {"water_leak_protection", "consultation_request"} <= signal_types
    assert {"vendor", "automation_component", "controlled_device"} <= fact_types
    assert "smart_home" in {item.type for item in result.lead_assessment.solution_areas}
    assert "security" in {item.type for item in result.lead_assessment.solution_areas}


def test_default_config_does_not_mark_diy_equipment_sale_as_lead() -> None:
    config = load_nlp_config(Path("config/nlp"))
    enricher = RussianTextEnricher(config)
    text = "Продам камеру видеонаблюдения без монтажа, самовывоз, дешево."

    result = enricher.enrich(text)

    assert result.lead_assessment is not None
    assert result.lead_assessment.is_lead is False
    assert result.lead_assessment.temperature == "none"
    assert "diy_or_equipment_only" in {item.type for item in result.lead_assessment.noise_signals}
