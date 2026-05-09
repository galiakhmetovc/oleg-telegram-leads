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
              Настройки управляют тем, какие фрагменты текста найдёт pipeline, какие причины
              попадут в объяснение и как из них получится оценка потенциального лида ПУР.
            </Typography>
          </Box>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Pipeline</Typography>
            <Typography variant="body2" color="text.secondary">
              Pipeline - список этапов обработки. Выключенный этап не запускается и не добавляет
              данные в результат. Если выключить `domain_signals`, сообщение не получит доменные
              сигналы; если выключить `facts`, не появятся факты; если выключить `lead_scoring`,
              не будет verdict, score, температуры, причин и очереди разбора.
            </Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Этап</TableCell>
                    <TableCell>Что добавляет</TableCell>
                    <TableCell>Как влияет</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>segmentation / morphology / lemmatization</TableCell>
                    <TableCell>предложения, токены, леммы, части речи</TableCell>
                    <TableCell>нужны для лемматического совпадения и объяснимой разметки текста</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>domain_signals</TableCell>
                    <TableCell>смысловые признаки: умный дом, видеонаблюдение, протечки</TableCell>
                    <TableCell>дают основные причины `weights.signals` для score</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>facts</TableCell>
                    <TableCell>структурные факты: устройство, город, тип работ, выводы</TableCell>
                    <TableCell>добавляют контекст и причины `weights.facts` для score</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>lead_scoring</TableCell>
                    <TableCell>lead_assessment: score, temperature, reasons, segments, lanes</TableCell>
                    <TableCell>превращает найденные сигналы и факты в решение "лид / не лид"</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>

          <Box className="help-grid">
            <Paper variant="outlined" className="help-section">
              <Typography variant="h6">Точное совпадение</Typography>
              <Typography variant="body2" color="text.secondary">
                Используй для фраз, где важна именно запись: аббревиатуры, бренды, протоколы,
                технические обозначения и короткие устойчивые выражения. Регистр не важен;
                между словами могут быть пробелы, переносы, `@`, emoji и другая пунктуация.
              </Typography>
              <Stack spacing={0.75}>
                {["с ндс", "white box", "220v", "wi-fi"].map((item) => (
                  <Chip key={item} label={item} size="small" variant="outlined" />
                ))}
              </Stack>
            </Paper>

            <Paper variant="outlined" className="help-section">
              <Typography variant="h6">Лемматическое совпадение</Typography>
              <Typography variant="body2" color="text.secondary">
                Используй для русских доменных смыслов. Оператор вводит обычную фразу, backend
                приводит слова к леммам, а правило потом находит разные падежи, роды и числа.
              </Typography>
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Ввод оператора</TableCell>
                      <TableCell>Леммы в правиле</TableCell>
                      <TableCell>Что найдет</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    <TableRow>
                      <TableCell>нужна консультация</TableCell>
                      <TableCell>нужный консультация</TableCell>
                      <TableCell>нужную консультацию, нужны консультации</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>умный дом</TableCell>
                      <TableCell>умный дом</TableCell>
                      <TableCell>умного дома, умному дому</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>система видеонаблюдения</TableCell>
                      <TableCell>система видеонаблюдение</TableCell>
                      <TableCell>систему видеонаблюдения</TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </TableContainer>
            </Paper>
          </Box>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Доменные сигналы</Typography>
            <Typography variant="body2" color="text.secondary">
              Доменный сигнал - это смысловой маркер в сообщении. Он отвечает на вопрос:
              "О чём здесь говорят с точки зрения бизнеса ПУР?". Например,
              `smart_home_platform`, `video_surveillance`, `water_leak_protection`,
              `access_control`. Один сигнал может быть найден точной фразой,
              лемматической фразой или зависимостью `match` от словаря/факта.
            </Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Поле</TableCell>
                    <TableCell>Что это</TableCell>
                    <TableCell>Как настраивать</TableCell>
                    <TableCell>Как влияет</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>type</TableCell>
                    <TableCell>стабильный технический ключ сигнала</TableCell>
                    <TableCell>type пишем латиницей в snake_case: `video_surveillance`, `smart_home_platform`</TableCell>
                    <TableCell>по этому ключу считаются веса, зоны решений, intent/noise и фильтры аналитики</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>label</TableCell>
                    <TableCell>человеческое имя в интерфейсе</TableCell>
                    <TableCell>label - русское название: "Видеонаблюдение", "Умный дом"</TableCell>
                    <TableCell>показывается оператору, но не должен использоваться как стабильный идентификатор</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>confidence</TableCell>
                    <TableCell>доверие к самому правилу, число от 0 до 1</TableCell>
                    <TableCell>confidence - доверие к правилу; ставь выше для точных терминов, ниже для широких формулировок</TableCell>
                    <TableCell>попадает в разметку найденного span; score сейчас считается весами, а не confidence</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>group</TableCell>
                    <TableCell>папка для навигации по большому списку правил</TableCell>
                    <TableCell>group - папка, можно писать по-русски: "Безопасность", "Спрос и намерение"</TableCell>
                    <TableCell>не влияет на детекцию и score; только группирует правила в интерфейсе настроек</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>phrases</TableCell>
                    <TableCell>точные фразы</TableCell>
                    <TableCell>используй для коротких устойчивых выражений; бренды, модели и протоколы держи в словарях</TableCell>
                    <TableCell>если фраза найдена, в сообщении появляется сигнал с этим type</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>patterns</TableCell>
                    <TableCell>лемматические фразы</TableCell>
                    <TableCell>оператор вводит обычный текст, backend сохраняет исходный текст и леммы</TableCell>
                    <TableCell>находит формы слов: "умного дома", "умному дому", "систему видеонаблюдения"</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>match.facts</TableCell>
                    <TableCell>зависимости сигнала от уже найденных фактов</TableCell>
                    <TableCell>выбери `alias:devices:camera`, `video_device`, `automation_component` или другой fact_type из списка</TableCell>
                    <TableCell>единственный способ связать словари с сигналами: словарь выпускает факт, сигнал зависит от факта</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
            <Alert severity="info">
              `type` технически является строкой, но в рабочих настройках не пишем его по-русски.
              Русский текст живёт в `label`. Это нужно, чтобы ключи были стабильными в API,
              аналитике, весах, миграциях и будущих eval-наборах.
            </Alert>
            <Alert severity="warning">
              Зависимости должны быть узкими. Например, `камера` может дать словарную сущность,
              факт `alias:devices:camera`, факт `video_device` и сигнал `video_surveillance`, но не должна давать
              `automation_component`, `controlled_device` или зону "Умный дом". Иначе одно
              слово начинает разгонять score сразу несколькими независимыми причинами.
            </Alert>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Факты</Typography>
            <Typography variant="body2" color="text.secondary">
              Факт - это структурная деталь, которую можно использовать в объяснении и scoring:
              тип работ, устройство, город, помещение, вывод под оборудование, протокол, модель,
              поверхность монтажа. Факт обычно отвечает не "о чём сообщение", а "какая конкретика
              в нём есть".
            </Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Поле</TableCell>
                    <TableCell>Что это</TableCell>
                    <TableCell>Как влияет на сообщение</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>type</TableCell>
                    <TableCell>технический ключ факта, тоже латиницей в snake_case</TableCell>
                    <TableCell>`controlled_device`, `wiring_output`, `service_location` могут добавить score через `weights.facts`</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>label</TableCell>
                    <TableCell>русское имя факта для оператора</TableCell>
                    <TableCell>показывается в таблицах фактов и в preview draft</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>phrases / patterns</TableCell>
                    <TableCell>такие же режимы совпадения, как у сигналов</TableCell>
                    <TableCell>создают span в `facts`; затем scorer может учесть этот fact type</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>confidence</TableCell>
                    <TableCell>доверие к правилу извлечения факта</TableCell>
                    <TableCell>помогает читать результат, но не заменяет вес в scoring</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Словари</Typography>
            <Typography variant="body2" color="text.secondary">
              Словари нужны для сущностей с множеством человеческих написаний: vendors,
              protocols, devices, software. Они ловят конкретные имена и варианты записи:
              `Yandex/Яндекс`, `Aqara/Акара`, `Zigbee/Зигби`, `Home Assistant/Хоум Ассистант`.
              Входной текст перед точным матчингом приводится к нижнему регистру, поэтому регистр
              в alias не влияет на поиск.
            </Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Поле</TableCell>
                    <TableCell>Что это</TableCell>
                    <TableCell>Как настраивать</TableCell>
                    <TableCell>Как влияет</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>key</TableCell>
                    <TableCell>стабильный ключ записи словаря</TableCell>
                    <TableCell>латиница snake_case: `yandex`, `aqara`, `neptun_prow`</TableCell>
                    <TableCell>нужен для обслуживания словаря и будущих связей</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>canonical</TableCell>
                    <TableCell>каноническое имя</TableCell>
                    <TableCell>`Yandex Smart Home`, `Aqara`, `Neptun ProW`</TableCell>
                    <TableCell>показывает, что именно имелось в виду при любом alias</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>aliases</TableCell>
                    <TableCell>варианты написания</TableCell>
                    <TableCell>латиница, кириллица, транслитерация, частые ошибки: `Нептун`, `Нептуп`</TableCell>
                    <TableCell>сам alias создаёт факты; сигналы ссылаются на них через `match.facts`</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>fact_types</TableCell>
                    <TableCell>какие факты добавить при совпадении</TableCell>
                    <TableCell>например `vendor`, `protocol`, `software`, `model`</TableCell>
                    <TableCell>добавляет структурную конкретику и может дать вес через `weights.facts`</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Alias matching</Typography>
            <Typography variant="body2" color="text.secondary">
              Alias-словари всегда сравниваются через casefold, поэтому регистр не важен:
              `Neptun`, `neptun`, `НЕПТУН` и `Нептун` обрабатываются без отдельного
              перечисления регистра. Дополнительно можно включить нормализацию `ё/е`,
              похожих латинских/кириллических букв и небольшой fuzzy-допуск.
            </Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Настройка</TableCell>
                    <TableCell>Что делает</TableCell>
                    <TableCell>Риск</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>normalize_separators</TableCell>
                    <TableCell>считает `Profi Wi-Fi`, `Profi-WiFi`, `profi wifi` близкими написаниями</TableCell>
                    <TableCell>низкий, потому что alias всё равно должен совпасть целиком</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>normalize_yo</TableCell>
                    <TableCell>считает `ё` и `е` одной буквой</TableCell>
                    <TableCell>низкий для русских технических названий</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>normalize_latin_confusables</TableCell>
                    <TableCell>ловит смешанные буквы вроде `Нептyн`, где `y` латинская</TableCell>
                    <TableCell>средний, поэтому применяется только к похожим буквам внутри слова</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>fuzzy_enabled</TableCell>
                    <TableCell>разрешает небольшую редакционную дистанцию для alias</TableCell>
                    <TableCell>может дать шум, если включить слишком большой distance</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>fuzzy_min_length</TableCell>
                    <TableCell>короткие alias не проходят fuzzy; например `sst`, `knx`, `dvr` не должны ловить случайные слова</TableCell>
                    <TableCell>если поставить слишком низко, короткие alias начнут шуметь</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>fuzzy_excluded_aliases</TableCell>
                    <TableCell>ручной стоп-лист alias, для которых fuzzy запрещён даже при достаточной длине</TableCell>
                    <TableCell>используется для спорных брендов, аббревиатур и коротких моделей</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Связь сигналов и словарей</Typography>
            <Typography variant="body2" color="text.secondary">
              Доменный сигнал и словарь не заменяют друг друга. Они являются разными источниками
              данных. Смысловая категория остаётся в доменных сигналах, а конкретные бренды,
              модели, протоколы и приложения живут в словарях. Связь строится только через
              факты: словарь выпускает `alias:catalog:key`, а доменный сигнал ссылается на
              этот факт в `match.facts`.
            </Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Шаг</TableCell>
                    <TableCell>Пример</TableCell>
                    <TableCell>Что появляется в результате</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>1. Словарь</TableCell>
                    <TableCell>`Нептун` найден в vendors/neptun</TableCell>
                    <TableCell>факт `alias:vendors:neptun` и факт `vendor`</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>2. Факт</TableCell>
                    <TableCell>`alias:vendors:neptun` выбран в `match.facts`</TableCell>
                    <TableCell>сигнал `water_leak_protection` с `source=fact_dependency`</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>3. Score</TableCell>
                    <TableCell>найден сигнал и/или факт с весом</TableCell>
                    <TableCell>причина score, направление решения, сегмент или очередь разбора</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Где настроено</TableCell>
                    <TableCell>Что произойдёт при тексте "Нептун"</TableCell>
                    <TableCell>Когда использовать</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>patterns у `water_leak_protection`</TableCell>
                    <TableCell>общие фразы вроде "датчик протечки" создают сигнал `water_leak_protection` с `source=yargy`</TableCell>
                    <TableCell>когда фраза описывает смысловую категорию, а не бренд или модель</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>`match.facts` у `water_leak_protection`</TableCell>
                    <TableCell>сигнал ссылается на факт `alias:vendors:neptun`; "Нептун" не добавляем в `phrases`, но сигнал появляется с `source=fact_dependency`</TableCell>
                    <TableCell>когда смысловой сигнал должен опираться на словарную сущность</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>alias `neptun` в словаре vendors</TableCell>
                    <TableCell>словарь создаёт факты `vendor`, `model` и хранит `Нептун`, `Нептуп`, `Neptun ProW`, `Profi Wi-Fi`</TableCell>
                    <TableCell>когда нужно хранить каноническое имя, варианты написания и ошибки</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>lead_scoring</TableCell>
                    <TableCell>score учитывает найденные типы, а не место настройки; один и тот же type в причинах считается один раз</TableCell>
                    <TableCell>веса задаются в `weights.signals` и `weights.facts` по техническим ключам type</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
            <Alert severity="info">
              Практическое правило: бренды, модели, протоколы, приложения и человеческие ошибки
              написания держим в словарях. Доменные сигналы ссылаются на словари через
              факты `alias:catalog:key` внутри `match.facts`; словари не содержат `signal_types`,
              чтобы не было двух источников правды. Обобщенные факты от alias задаются через
              `fact_types`.
            </Alert>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Оценка лида</Typography>
            <Typography variant="body2" color="text.secondary">
              Оценка лида - детерминированный слой поверх найденных сигналов и фактов. Он не
              перечитывает текст заново и не использует LLM. Он берёт уже найденные `domain_signals`
              и `facts`, суммирует настроенные веса, определяет температуру, зоны решений,
              сегменты клиента, причины и очередь разбора.
            </Typography>
            <Stack spacing={2}>
              <Alert severity="info">
                score = сумма весов всех найденных типов из `weights.signals` и `weights.facts`.
                Один type учитывается как причина, если он встретился хотя бы один раз; найденные
                тексты сохраняются в `matched_texts`, чтобы было видно, почему правило сработало.
                После суммы могут примениться `score_caps`: они добавляют отдельную отрицательную
                причину `score_cap` и ограничивают итоговую оценку.
              </Alert>
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
                      <TableCell>thresholds.lead</TableCell>
                      <TableCell>минимальный score, с которого `is_lead = true`</TableCell>
                      <TableCell>ниже порога сообщение остаётся не лидом, даже если есть отдельные признаки</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>thresholds.warm / thresholds.hot</TableCell>
                      <TableCell>пороги температуры</TableCell>
                      <TableCell>дают `cold`, `warm`, `hot`; это не отдельные правила, а диапазоны score</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>weights.signals</TableCell>
                      <TableCell>веса доменных сигналов</TableCell>
                      <TableCell>`video_surveillance: 25` добавит 25 баллов, если найден сигнал `video_surveillance`</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>weights.facts</TableCell>
                      <TableCell>веса фактов</TableCell>
                      <TableCell>`wiring_output: 8` добавит 8 баллов, если найден факт вывода под оборудование</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>negative weights</TableCell>
                      <TableCell>отрицательные веса для шума</TableCell>
                      <TableCell>`diy_or_equipment_only: -50` снижает score, если сообщение похоже на DIY или покупку железки без услуги</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>solution_areas</TableCell>
                      <TableCell>карта типов в направления решений ПУР</TableCell>
                      <TableCell>показывает "Умный дом", "Безопасность", "Климат", "СКУД" и даёт фильтры аналитики</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>customer_segments</TableCell>
                      <TableCell>карта типов в сегменты клиентов</TableCell>
                      <TableCell>выделяет дизайнеров, частное жильё, коммерческие объекты, активные запросы</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>intent_signal_types</TableCell>
                      <TableCell>какие сигналы считать намерением</TableCell>
                      <TableCell>показывает, что пользователь ищет подрядчика, консультацию, установку или подбор решения</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>noise_signal_types</TableCell>
                      <TableCell>какие сигналы считать шумом</TableCell>
                      <TableCell>объясняет, почему кандидат может быть слабым или нецелевым</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>lead_veto_signal_types</TableCell>
                      <TableCell>какой шум запрещает автолид</TableCell>
                      <TableCell>если найден такой сигнал, score сохраняется для разбора, но `is_lead=false` и температура `none`</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>score_caps</TableCell>
                      <TableCell>какие совпадения ограничивают итоговый score сверху</TableCell>
                      <TableCell>например явный шум может поставить `max_score: 0`, чтобы продажа железки не оставалась горячим кандидатом</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>review_lanes</TableCell>
                      <TableCell>очереди ручного разбора кандидатов</TableCell>
                      <TableCell>после batch import кандидат получает lane: прямой лид, проектный контекст, доменный интерес, шум</TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </TableContainer>
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Пример</TableCell>
                      <TableCell>Что найдётся</TableCell>
                      <TableCell>Почему станет лидом</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    <TableRow>
                      <TableCell>нужно подключить zigbee шлюз к Алисе</TableCell>
                      <TableCell>protocol_gateway, smart_home_platform, work_type</TableCell>
                      <TableCell>сумма весов проходит lead/hot threshold, появляются причины и smart_home area</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>где заказать видеонаблюдение для квартиры</TableCell>
                      <TableCell>provider_search, video_surveillance, apartment_context</TableCell>
                      <TableCell>есть домен безопасности и активный поиск поставщика/подрядчика</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>продам камеру, сам поставлю</TableCell>
                      <TableCell>video_surveillance плюс noise/DIY или sale</TableCell>
                      <TableCell>отрицательные веса и noise signals могут увести ниже порога или в lane "Шум"</TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </TableContainer>
            </Stack>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Очереди разбора</Typography>
            <Typography variant="body2" color="text.secondary">
              `review_lanes` - это не новая детекция текста, а способ разложить уже найденных
              кандидатов по очередям для ручного анализа. Lane с большим `priority` проверяется
              первой. `match_groups` работают как группы условий: внутри группы достаточно одного
              совпадения, а группы между собой должны выполниться все. Excluded-поля убирают
              кандидата из lane, даже если положительные условия совпали.
            </Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Поле lane</TableCell>
                    <TableCell>Назначение</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>key / label / description</TableCell>
                    <TableCell>технический ключ, русское имя и пояснение для аналитики</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>priority</TableCell>
                    <TableCell>чем выше число, тем раньше lane заберёт кандидата</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>match_groups</TableCell>
                    <TableCell>условия по signal_types, fact_types, reason_keys, solution_area_types, customer_segment_types</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>excluded_* fields</TableCell>
                    <TableCell>запреты по шуму, причинам, сигналам, сегментам или зонам решений</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Уведомления</Typography>
            <Typography variant="body2" color="text.secondary">
              Раздел управляет доставкой уведомлений после runtime enrichment. Batch-runner сюда
              не подключен: он нужен для тестирования и калибровки на архивах. Продовая цепочка
              будет такой: userbot получает сообщение, создает обычную задачу enrichment, после
              завершения результата маршруты кладут уведомления в outbox, а отдельный dispatcher
              отправляет их пачками.
            </Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Сущность</TableCell>
                    <TableCell>Что настраивается</TableCell>
                    <TableCell>Как работает</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>Боты</TableCell>
                    <TableCell>ID, название, включен/выключен, токен BotFather</TableCell>
                    <TableCell>бот владеет токеном; токен хранится в PostgreSQL и в UI/API показывается только маской</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Чаты</TableCell>
                    <TableCell>ID, название, включен/выключен, Telegram `chat_id`</TableCell>
                    <TableCell>чат не знает про токен; тестовая отправка выбирает сохраненного бота отдельно</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Маршруты</TableCell>
                    <TableCell>priority, bot, chat, режим all/any, условия и шаблон</TableCell>
                    <TableCell>после обработки текста выбирают доставку по score, temperature, lane, сегментам, сигналам, фактам и причинам; каждый match создает запись в `notification_outbox`</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Шаблон сообщения</TableCell>
                    <TableCell>{`{score}, {temperature}, {review_lane_label}, {solution_areas}, {customer_segments}, {reasons_detailed}, {text_preview}`}</TableCell>
                    <TableCell>дефолтный шаблон разбивает уведомление на блоки: оценка, очередь, направления, причины score и короткий текст; ссылки на Telegram и аналитику добавляются отдельным блоком</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Outbox batching</TableCell>
                    <TableCell>группировка по bot+chat, лимит текста, интервал flush</TableCell>
                    <TableCell>dispatcher пакует лиды под 4096 символов Telegram `sendMessage`; неполная пачка уходит, когда старейшая запись ждёт 5 минут</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Отправить тест</TableCell>
                    <TableCell>бот + чат + текст проверки</TableCell>
                    <TableCell>проверяет реальную доставку в Telegram до включения маршрутов</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Telegram вход</Typography>
            <Typography variant="body2" color="text.secondary">
              Раздел управляет входящими Telegram-источниками. Userbot - это пользовательский
              Telegram-аккаунт через Telethon, а не Bot API. Он читает указанные чаты, сохраняет
              исходные сообщения и создает обычные enrichment jobs. Секреты не показываются:
              `api_hash` и `StringSession` возвращаются в UI только как факт наличия и маска.
            </Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Сущность</TableCell>
                    <TableCell>Что настраивается</TableCell>
                    <TableCell>Как работает</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>Userbot аккаунт</TableCell>
                    <TableCell>телефон, Telegram app `api_id`, `api_hash`, включен/выключен</TableCell>
                    <TableCell>кнопка "Отправить код" запускает login; "Завершить вход" сохраняет Telethon `StringSession`</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Чат-источник</TableCell>
                    <TableCell>userbot account, `input_ref`, resolved chat id, cursor</TableCell>
                    <TableCell>`input_ref` может быть username или id; userbot хранит `last_message_id` и не импортирует историю без явного batch-runner</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Статус чата-источника</TableCell>
                    <TableCell>`draft`, `resolved`, `error`</TableCell>
                    <TableCell>`draft` означает, что запись сохранена, но userbot еще не резолвил `input_ref`; `resolved` означает, что найден Telegram chat id и сохранен cursor; "Обновить статус" перечитывает актуальное состояние из backend</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Очередь анализа</TableCell>
                    <TableCell>создается обычный enrichment job</TableCell>
                    <TableCell>userbot не анализирует текст сам; он сохраняет сообщение и публикует задачу в существующую Celery/Redis очередь</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Как выбирать режим</Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Ситуация</TableCell>
                    <TableCell>Что выбрать</TableCell>
                    <TableCell>Почему</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>Русская предметная фраза</TableCell>
                    <TableCell>Лемматическое совпадение</TableCell>
                    <TableCell>Поймает формы слов без перечисления падежей.</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Аббревиатура, бренд, техническая запись</TableCell>
                    <TableCell>Точное совпадение</TableCell>
                    <TableCell>Такие токены часто нельзя надежно лемматизировать.</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Новое правило непонятно как сработает</TableCell>
                    <TableCell>Preview draft</TableCell>
                    <TableCell>Проверяет черновик без сохранения новой ревизии.</TableCell>
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
