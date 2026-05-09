import { Alert, Box, Chip, Paper, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from "@mui/material";

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
              Текущая модель настроек - v3. Старые имена сигналов и фактов не являются
              совместимым контрактом. Рабочая цепочка теперь такая: словари находят сущности,
              факты описывают смысловые детали текста, доменные сигналы собираются из фактов,
              а оценка лида считает score только по найденным сигналам и фактам.
            </Typography>
          </Box>

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
                    <TableCell>Попадают в таблицу фактов, подсветку текста и `weights.facts`.</TableCell>
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
                    <TableCell>сигналы намерения, контекста, сегмента и домена ПУР</TableCell>
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
              делятся на намерения, контекст проекта, объект, домен ПУР и шум.
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
                    <TableCell>Домен ПУР</TableCell>
                    <TableCell>domain_smart_home, domain_leak_protection, domain_video_surveillance</TableCell>
                    <TableCell>Текст явно говорит про умный дом, протечки, видеонаблюдение, СКУД, климат, свет, СКС.</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Шум</TableCell>
                    <TableCell>noise_supply_sale, noise_diy_equipment_only, noise_ordinary_household</TableCell>
                    <TableCell>Продажа железки, DIY без монтажа, бытовой вопрос вне ПУР или только цена.</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
            <Alert severity="warning">
              `type` у факта - технический ключ латиницей в snake_case. Русский текст пишется
              в `label`. Ключи используются в API, deep links, фильтрах, весах и миграциях.
            </Alert>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Точные и лемматические фразы</Typography>
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
                  {["заказчик хочет", "датчик протечки", "чертежи электрики"].map((item) => (
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
              нормальный curated alias.
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
              Сигнал отвечает на вопрос "что это значит для ПУР?". В v3 сигналы
              бывают четырёх типов: намерение лида, проектный контекст, клиентский
              сегмент и домен ПУР.
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
                    <TableCell>lead_active_intent, lead_consultation_intent, lead_research_intent</TableCell>
                    <TableCell>из фактов intent_*: поиск контактов, установка, консультация, подбор</TableCell>
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
                    <TableCell>pur_smart_home, pur_video_surveillance, pur_leak_protection</TableCell>
                    <TableCell>из domain_* фактов и alias-фактов словарей</TableCell>
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
                    <TableCell>карта сигналов в направления ПУР</TableCell>
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
                    <TableCell>домен ПУР без намерения</TableCell>
                    <TableCell>слова вроде "камера", "хаб", "Нептун" остаются ниже порога лида</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>score_caps.intent_without_pur_domain</TableCell>
                    <TableCell>намерение без домена ПУР</TableCell>
                    <TableCell>"где заказать обычный стол" не становится лидом ПУР</TableCell>
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
              Прямой лид ПУР в v3 обычно требует два слоя одновременно: домен ПУР
              и конкретное активное намерение, например `intent_provider_search` или
              `intent_install_connect`. Консультационные и исследовательские вопросы
              идут в `research_warm`, а одиночные доменные слова остаются ниже порога.
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
                    <TableCell>прямой лид ПУР</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Где заказать видеонаблюдение для квартиры?</TableCell>
                    <TableCell>intent_provider_search, domain_video_surveillance, object_apartment</TableCell>
                    <TableCell>прямой лид, зона "Безопасность"</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>камера</TableCell>
                    <TableCell>alias:devices:camera, pur_video_surveillance</TableCell>
                    <TableCell>не лид: домен без намерения</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Подскажите, где заказать обычный стол?</TableCell>
                    <TableCell>intent_provider_search без домена ПУР</TableCell>
                    <TableCell>не лид: намерение без домена ПУР</TableCell>
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
