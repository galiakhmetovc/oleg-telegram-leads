import { Alert, Box, Button, Chip, Paper, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from "@mui/material";

export function SettingsHelpPage() {
  return (
    <Box className="help-shell">
      <Paper variant="outlined" className="settings-panel">
        <Stack spacing={3}>
          <Box>
            <Typography variant="h5" component="h2" sx={{ fontWeight: 800 }}>
              Справка по настройкам
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Текущая модель настроек - v3. Рабочая цепочка такая: текст сначала дает
              alias или fact, затем из фактов собираются сигналы, затем lead scoring
              считает итог. Самое важное правило: у фактов два источника - fact rule и
              alias dictionary.
            </Typography>
          </Box>

          <Alert
            severity="info"
            action={
              <Button color="inherit" size="small" href="/guide">
                Открыть guide
              </Button>
            }
          >
            Полный операторский алгоритм теперь живет во вкладке `Как работать`.
            Эта страница остается технической справкой по структуре настроек.
          </Alert>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Главная схема</Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Слой</TableCell>
                    <TableCell>Что делает</TableCell>
                    <TableCell>Примеры v3</TableCell>
                    <TableCell>Как влияет на сообщение</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>Словари</TableCell>
                    <TableCell>Находят конкретные бренды, протоколы, устройства и ПО.</TableCell>
                    <TableCell>vendors:yandex, devices:camera, software:alice</TableCell>
                    <TableCell>Создают alias-факт `alias:catalog:key` и общие факты вроде `vendor`, `protocol`, `software`.</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Факты</TableCell>
                    <TableCell>Извлекают намерение, контекст, объект и доменную конкретику.</TableCell>
                    <TableCell>intent_provider_search, context_wiring_output, domain_video_surveillance</TableCell>
                    <TableCell>Появляются либо из fact rule, либо из словаря; попадают в таблицу фактов, подсветку текста и `weights.facts`.</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Доменные сигналы</TableCell>
                    <TableCell>Собирают бизнес-смысл из фактов и alias-фактов.</TableCell>
                    <TableCell>pur_smart_home, pur_leak_protection, lead_active_intent</TableCell>
                    <TableCell>Попадают в причины score, зоны решений, сегменты и очереди разбора.</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Оценка лида</TableCell>
                    <TableCell>Суммирует веса и применяет ограничения.</TableCell>
                    <TableCell>thresholds, weights, score_caps, review_lanes</TableCell>
                    <TableCell>Даёт `is_lead`, score, temperature, направления, сегменты и lane.</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
            <Alert severity="info">
              В v3 доменные сигналы не должны содержать свои `phrases` или `patterns`.
              Они ссылаются на факты через `match.facts`. Это делает причину срабатывания
              проверяемой: сначала видно найденный факт, затем видно сигнал, который от него зависит.
              Конкретный текстовый фрагмент должен иметь одного владельца: либо fact rule,
              либо alias-словарь.
            </Alert>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Что Использовать Когда</Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Что ты видишь в тексте</TableCell>
                    <TableCell>Что создавать</TableCell>
                    <TableCell>Почему</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>Бренд, протокол, устройство, модель, ПО</TableCell>
                    <TableCell>Alias dictionary</TableCell>
                    <TableCell>Если это бренды, протоколы, устройства, модели или ПО - используй словарь.</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Намерение, контекст, домен, объект, шум</TableCell>
                    <TableCell>Fact rule</TableCell>
                    <TableCell>Если это намерение, контекст, домен, объект или шум - используй факт.</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Бизнес-вывод по уже найденным фактам</TableCell>
                    <TableCell>Signal</TableCell>
                    <TableCell>Если это бизнес-вывод по найденным фактам - используй сигнал.</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
            <Alert severity="warning">
              Не моделируй словарь как особый вид fact rule. Словарь канонизирует именованные
              сущности и выпускает факты; fact rule сам матчится по точной или лемматической фразе.
            </Alert>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Конструктор</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Во вкладке `Конструктор` работа идет через локальный draft. Сначала оператор
              вставляет сообщение и запускает preview, потом выделяет текст и решает,
              кому принадлежит этот фрагмент.
            </Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Шаг</TableCell>
                    <TableCell>Что делать</TableCell>
                    <TableCell>Что получится</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>1. Разобрать сообщение</TableCell>
                    <TableCell>Вставь текст и нажми `Разобрать`.</TableCell>
                    <TableCell>Появятся словарные совпадения, facts, сигналы и lead score для текущего draft.</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>2. Назначить owner выделению</TableCell>
                    <TableCell>Выдели кусок текста и отправь его `В словарь`, `В факт` или `В шум`.</TableCell>
                    <TableCell>Draft обновится, а preview пересчитается на тех же настройках.</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>3. Собрать доменный сигнал</TableCell>
                    <TableCell>Ниже отметь нужные facts и сохрани сигнал в draft.</TableCell>
                    <TableCell>Сигнал начнет зависеть от отмеченных facts через `match.facts`.</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>4. Сохранить ревизию</TableCell>
                    <TableCell>Когда preview стал правильным, нажми `Сохранить ревизию`.</TableCell>
                    <TableCell>Только на этом шаге draft уходит в active NLP revision.</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
            <Alert severity="info">
              Конструктор не пишет текст напрямую в signal. Выделенный фрагмент можно
              превратить только в alias или fact. Signal строится отдельно, уже из найденных facts.
            </Alert>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Pipeline</Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Этап</TableCell>
                    <TableCell>Что добавляет</TableCell>
                    <TableCell>Что будет, если выключить</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>segmentation / morph / syntax / ner</TableCell>
                    <TableCell>токены, леммы, POS, синтаксис и NER</TableCell>
                    <TableCell>часть визуального enrichment пропадёт; Yargy-факты и alias matching останутся, если их этапы включены</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>facts</TableCell>
                    <TableCell>факты из правил и словарей</TableCell>
                    <TableCell>доменные сигналы v3 почти не смогут сработать, потому что зависят от фактов</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>domain_signals</TableCell>
                    <TableCell>сигналы намерения, контекста, сегмента и целевого домена</TableCell>
                    <TableCell>score потеряет основные причины, зоны решений и очереди разбора</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>lead_scoring</TableCell>
                    <TableCell>lead_assessment: score, temperature, reasons, areas, segments, lane</TableCell>
                    <TableCell>текст будет обогащён, но решения "лид / не лид" не будет</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Факты</Typography>
            <Typography variant="body2" color="text.secondary">
              Факт отвечает на вопрос "какая конкретная деталь есть в тексте?". Факты
              делятся на намерения, контекст проекта, объект, целевой домен и шум.
            </Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Группа</TableCell>
                    <TableCell>Примеры ключей</TableCell>
                    <TableCell>Когда добавлять</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>Намерение</TableCell>
                    <TableCell>intent_provider_search, intent_install_connect, intent_consultation</TableCell>
                    <TableCell>Пользователь ищет контакты, хочет установить, просит подсказать или выбрать решение.</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Контекст проекта</TableCell>
                    <TableCell>context_design_project, context_wiring_output, context_warranty_risk</TableCell>
                    <TableCell>Есть чертежи, выводы, ремонт, white box, гарантия, изменение схемы.</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Объект / сегмент</TableCell>
                    <TableCell>object_apartment, object_commercial, object_family</TableCell>
                    <TableCell>Нужно понять, кто потенциальный клиент: квартира, дом, коммерция, семья.</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Целевой домен</TableCell>
                    <TableCell>domain_smart_home, domain_leak_protection, domain_video_surveillance</TableCell>
                    <TableCell>Текст явно говорит про умный дом, протечки, видеонаблюдение, СКУД, климат, свет, СКС.</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Шум</TableCell>
                    <TableCell>noise_supply_sale, noise_diy_equipment_only, noise_ordinary_household</TableCell>
                    <TableCell>Продажа железки, DIY без монтажа, бытовой вопрос вне целевого домена или только цена.</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
            <Alert severity="info">
              У фактов два источника: fact rule и alias dictionary. Fact rule сам находит
              текст и создает факт. Alias dictionary сначала находит именованную сущность,
              затем выпускает alias-факт `alias:catalog:key` и дополнительные `fact_types`.
              Это не значит, что факт зависит от словаря; это значит, что факт мог прийти
              из словаря как из источника.
            </Alert>
            <Alert severity="info">
              operator_noise_fact - обычный fact rule. Его правильно настраивать через
              exact phrase и при необходимости через lemmatized phrase. Он не требует словаря.
            </Alert>
            <Alert severity="warning">
              `type` у факта - технический ключ латиницей в snake_case. Русский текст пишется
              в `label`. Ключи используются в API, deep links, фильтрах, весах и миграциях.
            </Alert>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Evidence-only факты</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Некоторые `domain_*` факты нужны для трассировки, но не должны сами
              поднимать score. Это evidence-only слой: система показывает тему, а
              лидовый вывод делает только по более узкому intent или requirement.
            </Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Пример текста</TableCell>
                    <TableCell>Что извлекаем</TableCell>
                    <TableCell>Что НЕ делаем</TableCell>
                    <TableCell>Что включает лид</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>как обычно делают вентиляцию</TableCell>
                    <TableCell>domain_ventilation</TableCell>
                    <TableCell>не включаем pur_ventilation от одного слова</TableCell>
                    <TableCell>ничего: это не лид без запроса на проект или специалиста</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>контакты специалистов по вентиляции</TableCell>
                    <TableCell>intent_ventilation_specialist_request</TableCell>
                    <TableCell>не весим generic `вентиляция` напрямую</TableCell>
                    <TableCell>pur_ventilation и lane ventilation_specialist_referral</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>сценарии освещения в описании умного дома</TableCell>
                    <TableCell>общий контекст без узкого lighting intent</TableCell>
                    <TableCell>не включаем pur_lighting_automation</TableCell>
                    <TableCell>DALI, реле, датчики движения, умные выключатели или запрос на производителей</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>теплый пол, радиатора нет</TableCell>
                    <TableCell>описание помещения</TableCell>
                    <TableCell>не включаем pur_climate_control</TableCell>
                    <TableCell>узкий запрос на климат-контроль, прогрев или управление</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
            <Alert severity="info">
              Практическое правило: `domain_*` может быть просто evidence. Если слово
              часто встречается в обзорах, вакансиях или бытовых обсуждениях, сигнал
              должен зависеть от более узкого `intent_*` или `requirement_*`.
            </Alert>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Точные и лемматические фразы</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Эти два механизма относятся только к fact rules. Словарь не делает
              лемматический поиск, а signal вообще не матчится по тексту напрямую.
            </Typography>
            <Box className="help-grid">
              <Paper variant="outlined" className="help-section">
                <Typography variant="subtitle2">Точное совпадение</Typography>
                <Typography variant="body2" color="text.secondary">
                  Точное совпадение для коротких устойчивых записей. Регистр не важен, текст
                  перед сопоставлением приводится к нижнему регистру. Подходит для `220v`,
                  `white box`, `спб`, но не для брендов, если бренд уже есть в словаре.
                </Typography>
                <Stack spacing={0.75} direction="row" useFlexGap sx={{ flexWrap: "wrap" }}>
                  {["220v", "white box", "спб", "скуд"].map((item) => (
                    <Chip key={item} label={item} size="small" variant="outlined" />
                  ))}
                </Stack>
              </Paper>
              <Paper variant="outlined" className="help-section">
                <Typography variant="subtitle2">Лемматическое совпадение</Typography>
                <Typography variant="body2" color="text.secondary">
                  Лемматическое совпадение для русских смыслов. Оператор вводит обычный
                  текст, backend сохраняет исходную фразу и леммы, а правило ловит падежи,
                  числа и роды: "система видеонаблюдения" найдёт "систему видеонаблюдения".
                </Typography>
                <Stack spacing={0.75} direction="row" useFlexGap sx={{ flexWrap: "wrap" }}>
                  {["заказчик хочет", "нужна консультация", "чертежи электрики"].map((item) => (
                    <Chip key={item} label={item} size="small" variant="outlined" />
                  ))}
                </Stack>
              </Paper>
            </Box>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Поля правил</Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Поле</TableCell>
                    <TableCell>Как заполнять</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>type</TableCell>
                    <TableCell>type пишем латиницей в snake_case, потому что это стабильный API/filter key.</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>label</TableCell>
                    <TableCell>label - русское название, которое оператор видит в интерфейсе.</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>confidence</TableCell>
                    <TableCell>confidence - доверие к правилу; score считается весами, а не confidence.</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>group</TableCell>
                    <TableCell>group - папка для навигации по длинным спискам настроек.</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
            <Alert severity="info">
              Пример лемматического правила: оператор вводит "нужна консультация",
              backend показывает леммы "нужный консультация" и сохраняет исходный ввод
              для интерфейса.
            </Alert>
            <Stack spacing={0.75} direction="row" useFlexGap sx={{ flexWrap: "wrap" }}>
              <Chip label="нужна консультация" size="small" variant="outlined" />
              <Chip label="нужный консультация" size="small" variant="outlined" />
            </Stack>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Словари</Typography>
            <Typography variant="body2" color="text.secondary">
              Словари хранят конкретные сущности рынка: vendors, protocols, devices,
              software. Названия можно писать латиницей, кириллицей, транслитерацией и
              с частыми ошибками. Небольшой fuzzy-допуск включён отдельно и не заменяет
              нормальный curated alias. Если слово уже есть в словаре, facts/signals не
              повторяют его текстом, а ссылаются на выпущенный alias-факт.
            </Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Поле</TableCell>
                    <TableCell>Что это</TableCell>
                    <TableCell>Пример</TableCell>
                    <TableCell>Как связано с сигналами</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>key</TableCell>
                    <TableCell>стабильный ключ записи</TableCell>
                    <TableCell>neptun, zigbee, smart_lock</TableCell>
                    <TableCell>сигнал ссылается на `alias:vendors:neptun` или `alias:devices:smart_lock`</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>canonical</TableCell>
                    <TableCell>нормальное имя сущности</TableCell>
                    <TableCell>Neptun, Zigbee, Умный замок</TableCell>
                    <TableCell>показывается в найденных словарных сущностях</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>aliases</TableCell>
                    <TableCell>варианты написания</TableCell>
                    <TableCell>Neptun, Нептун, Нептуп, Neptun ProW</TableCell>
                    <TableCell>каждый alias создаёт alias-факт и общие fact_types</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>fact_types</TableCell>
                    <TableCell>общие типы фактов</TableCell>
                    <TableCell>vendor, model, protocol, software, automation_component</TableCell>
                    <TableCell>дают дополнительный вес и помогают объяснить найденную сущность</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
            <Alert severity="info">
              Словарь не делает лемматический поиск. Если нужна падежная или смысловая
              вариативность, это почти всегда fact rule, а не alias dictionary.
            </Alert>
            <Alert severity="info">
              Связь сигналов и словарей строится через факты. Например, "Нептун" живёт только в словаре vendors. Сигнал
              `pur_leak_protection` не хранит фразу "Нептун"; он зависит от факта
              `alias:vendors:neptun` и в результате появляется с `source=fact_dependency`.
              Поэтому править написания надо в словаре, а не дублировать их в доменных сигналах.
            </Alert>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Alias matching</Typography>
            <Typography variant="body2" color="text.secondary">
              Alias matching использует casefold, поэтому регистр в сообщении не важен.
              Настройки `fuzzy_min_length`, `fuzzy_max_distance`,
              `fuzzy_long_min_length` и `fuzzy_long_max_distance` ограничивают fuzzy-поиск.
              Короткие alias должны быть особенно осторожными: короткие alias вроде KNX,
              DVR или SST не должны случайно матчить обычные слова.
            </Typography>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Доменные сигналы</Typography>
            <Typography variant="body2" color="text.secondary">
              Сигнал отвечает на вопрос "что это значит для лида?". В v3 сигналы
              бывают четырёх типов: намерение лида, проектный контекст, клиентский
              сегмент и целевой домен.
            </Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Тип сигналов</TableCell>
                    <TableCell>Примеры</TableCell>
                    <TableCell>Откуда берутся</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>Intent</TableCell>
                    <TableCell>lead_active_intent, lead_consultation_intent, lead_partner_sourcing</TableCell>
                    <TableCell>из фактов intent_*: поиск контактов, установка, консультация, подбор, партнерский поиск</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Context</TableCell>
                    <TableCell>project_context</TableCell>
                    <TableCell>из context_*: выводы, чертежи, ремонт, гарантия, white box</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Segment</TableCell>
                    <TableCell>segment_designer, segment_private_residential, segment_commercial</TableCell>
                    <TableCell>из object_* и context_designer</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>PUR domain</TableCell>
                    <TableCell>pur_smart_home, pur_video_surveillance, pur_leak_protection, pur_ventilation</TableCell>
                    <TableCell>из domain_* фактов, узких intent_* фактов и alias-фактов словарей</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
            <Alert severity="warning">
              Не связывай широкий вендор сразу с несколькими доменами. Если одно слово
              "камера" или "ИК" начинает давать умный дом, климат и протоколы одновременно,
              значит зависимость слишком широкая. Лучше добавить точный доменный факт или
              более узкий alias.
            </Alert>
            <Alert severity="info">
              Доменный сигнал не обязан зависеть от широкого `domain_*`. Например,
              `pur_ventilation` должен включаться от `intent_ventilation_specialist_request`,
              потому что само слово "вентиляция" слишком широкое для лида.
            </Alert>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Оценка лида</Typography>
            <Typography variant="body2" color="text.secondary">
              Формула расчёта показывается в обзоре результата. Механика простая:
              score = сумма весов найденных сигналов и фактов, затем применяются caps.
              Negative weights используются для шумовых сигналов.
            </Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Настройка</TableCell>
                    <TableCell>Что означает</TableCell>
                    <TableCell>Как влияет</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>thresholds.lead / warm / hot</TableCell>
                    <TableCell>пороги лида и температуры</TableCell>
                    <TableCell>ниже `lead` сообщение не лид; выше `hot` становится hot</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>weights.signals</TableCell>
                    <TableCell>веса сигналов</TableCell>
                    <TableCell>`pur_smart_home: 30` добавляет 30 баллов, если найден сигнал</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>weights.facts</TableCell>
                    <TableCell>веса фактов</TableCell>
                    <TableCell>`intent_provider_search: 8` добавляет контекстную причину</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>solution_areas</TableCell>
                    <TableCell>карта сигналов в направления</TableCell>
                    <TableCell>даёт "Умный дом", "Безопасность", "СКУД", "Климат", фильтры аналитики и ссылки</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>customer_segments</TableCell>
                    <TableCell>карта сигналов/фактов в сегменты</TableCell>
                    <TableCell>выделяет дизайнеров, частное жильё, коммерческие объекты, активный запрос</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>intent_signal_types</TableCell>
                    <TableCell>какие сигналы считаются намерением</TableCell>
                    <TableCell>попадают в отдельный блок intent и участвуют в lanes/caps</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>noise_signal_types / lead_veto_signal_types</TableCell>
                    <TableCell>какие сигналы считаются шумом и запрещают автолид</TableCell>
                    <TableCell>score остаётся виден для разбора, но `is_lead=false`, temperature=`none`</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>score_caps.domain_without_intent</TableCell>
                    <TableCell>домен без намерения</TableCell>
                    <TableCell>слова вроде "камера", "хаб", "Нептун" остаются ниже порога лида</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>score_caps.intent_without_pur_domain</TableCell>
                    <TableCell>намерение без целевого домена</TableCell>
                    <TableCell>"где заказать обычный стол" не становится лидом</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>review_lanes</TableCell>
                    <TableCell>очереди ручного разбора</TableCell>
                    <TableCell>первое подходящее правило по priority выбирает lane в аналитике</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
            <Alert severity="info">
              Прямой лид в v3 обычно требует два слоя одновременно: целевой домен
              и конкретное активное намерение, например `intent_provider_search` или
              `intent_install_connect`. Консультационные и исследовательские вопросы
              идут в `research_warm`, а одиночные доменные слова остаются ниже порога.
            </Alert>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Сквозной пример</Typography>
            <Typography variant="body2" color="text.secondary">
              Один и тот же текст должен раскладываться по слоям последовательно:
              сначала ownership span, затем facts, затем signals, затем lead scoring.
            </Typography>
            <Paper variant="outlined" className="help-section" sx={{ mt: 2 }}>
              <Typography variant="subtitle2">Текст сообщения</Typography>
              <Typography variant="body2">
                Хочу поставить умный дом Aqara с Zigbee в квартире. Нужна консультация по датчикам протечки.
              </Typography>
            </Paper>
            <TableContainer sx={{ mt: 2 }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Фрагмент</TableCell>
                    <TableCell>Owner</TableCell>
                    <TableCell>Что выпускается</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>Хочу поставить</TableCell>
                    <TableCell>fact rule</TableCell>
                    <TableCell>intent_install_connect</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>умный дом</TableCell>
                    <TableCell>fact rule</TableCell>
                    <TableCell>domain_smart_home</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Aqara</TableCell>
                    <TableCell>alias dictionary: vendors</TableCell>
                    <TableCell>alias:vendors:aqara, vendor</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Zigbee</TableCell>
                    <TableCell>alias dictionary: protocols</TableCell>
                    <TableCell>alias:protocols:zigbee, protocol</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>в квартире</TableCell>
                    <TableCell>fact rule</TableCell>
                    <TableCell>object_apartment</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Нужна консультация</TableCell>
                    <TableCell>fact rule</TableCell>
                    <TableCell>intent_consultation</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>датчикам протечки</TableCell>
                    <TableCell>fact rule</TableCell>
                    <TableCell>domain_leak_protection</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
            <Alert severity="info" sx={{ mt: 2 }}>
              Здесь хорошо видно границу: Aqara и Zigbee живут только в словарях,
              а "Хочу поставить", "умный дом", "в квартире", "Нужна консультация"
              и "датчикам протечки" живут как fact rules.
            </Alert>
            <TableContainer sx={{ mt: 2 }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Какие facts уже найдены</TableCell>
                    <TableCell>Какой signal срабатывает</TableCell>
                    <TableCell>Почему</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>intent_install_connect</TableCell>
                    <TableCell>lead_active_intent</TableCell>
                    <TableCell>Есть явное намерение установить/подключить.</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>intent_consultation</TableCell>
                    <TableCell>lead_consultation_intent</TableCell>
                    <TableCell>Есть консультационный запрос.</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>domain_smart_home + alias:vendors:aqara + alias:protocols:zigbee</TableCell>
                    <TableCell>pur_smart_home</TableCell>
                    <TableCell>Есть домен плюс словарные сущности того же рынка.</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>domain_leak_protection</TableCell>
                    <TableCell>pur_leak_protection</TableCell>
                    <TableCell>Отдельный доменный слой по протечкам.</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>object_apartment</TableCell>
                    <TableCell>segment_private_residential</TableCell>
                    <TableCell>Понятен объект применения: квартира.</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
            <TableContainer sx={{ mt: 2 }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Слой scoring</TableCell>
                    <TableCell>Что читает</TableCell>
                    <TableCell>Что дает на выходе</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>weights.signals</TableCell>
                    <TableCell>lead_active_intent, lead_consultation_intent, pur_smart_home, pur_leak_protection</TableCell>
                    <TableCell>Основные баллы за бизнес-сигналы.</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>weights.facts</TableCell>
                    <TableCell>intent_install_connect, object_apartment</TableCell>
                    <TableCell>Контекстные и уточняющие причины score.</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>solution_areas</TableCell>
                    <TableCell>pur_smart_home, pur_leak_protection</TableCell>
                    <TableCell>Направления: умный дом и защита от протечек.</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>customer_segments</TableCell>
                    <TableCell>segment_private_residential</TableCell>
                    <TableCell>Сегмент: частное жилье.</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
            <Alert severity="warning" sx={{ mt: 2 }}>
              Если в таком примере что-то не сработало, чинить надо первый сломанный
              слой слева направо: сначала owner span, потом fact, потом signal,
              и только потом scoring.
            </Alert>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Примеры</Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Текст</TableCell>
                    <TableCell>Что должно найтись</TableCell>
                    <TableCell>Итог</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>Установить и подключить zigbee шлюз через Алису</TableCell>
                    <TableCell>intent_install_connect, pur_smart_home, lead_active_intent</TableCell>
                    <TableCell>прямой лид</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Где заказать видеонаблюдение для квартиры?</TableCell>
                    <TableCell>intent_provider_search, domain_video_surveillance, object_apartment</TableCell>
                    <TableCell>прямой лид, зона "Безопасность"</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Нужны контакты специалистов по вентиляции</TableCell>
                    <TableCell>intent_ventilation_specialist_request, pur_ventilation</TableCell>
                    <TableCell>лид: вентиляция как запрос на специалиста</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Как обычно делают вентиляцию в квартире?</TableCell>
                    <TableCell>domain_ventilation без узкого intent</TableCell>
                    <TableCell>не лид: evidence-only домен</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Ищу строительные бригады и мастеров для объектов</TableCell>
                    <TableCell>intent_partner_contractor_search, lead_partner_sourcing</TableCell>
                    <TableCell>лид: очередь partner_contractor_sourcing</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>камера</TableCell>
                    <TableCell>alias:devices:camera, pur_video_surveillance</TableCell>
                    <TableCell>не лид: домен без намерения</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Умный дом и сценарии освещения</TableCell>
                    <TableCell>domain_smart_home без узкого lighting evidence</TableCell>
                    <TableCell>не световой лид: нужен DALI, реле, датчики или запрос</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Подскажите, где заказать обычный стол?</TableCell>
                    <TableCell>intent_provider_search без целевого домена</TableCell>
                    <TableCell>не лид: намерение без целевого домена</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>
        </Stack>
      </Paper>
    </Box>
  );
}
