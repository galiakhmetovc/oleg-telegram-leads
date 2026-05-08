import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";

class FakeEventSource {
  static instances: FakeEventSource[] = [];

  listeners = new Map<string, (event: MessageEvent<string>) => void>();
  url: string;

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(eventName: string, listener: (event: MessageEvent<string>) => void) {
    this.listeners.set(eventName, listener);
  }

  close() {}
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("renders text enrichment workspace", () => {
  render(<App />);

  expect(screen.getByRole("heading", { name: /обогащение текста/i })).toBeInTheDocument();
  expect(screen.getByLabelText("Произвольный текст")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /запустить обогащение/i })).toBeInTheDocument();
});

test("uses scrollable top navigation for narrow screens", () => {
  render(<App />);

  const tabList = screen.getByRole("tablist", { name: "Основная навигация" });

  expect(tabList.closest(".MuiTabs-scroller")).toHaveClass("MuiTabs-scrollableX");
});

test("starts enrichment job and subscribes to SSE progress", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      id: "1e310b02-48b9-4652-ab32-e0d2a370d1f9",
      status: "queued",
      progress_percent: 0,
      current_stage: null,
      stage_index: 0,
      stage_count: 0,
      stage_progress_percent: 0,
      message: "Задача поставлена в очередь",
      result: null,
      error: null
    })
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);

  fireEvent.click(screen.getAllByRole("button", { name: /запустить обогащение/i })[0]);

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  expect(FakeEventSource.instances[0]?.url).toContain(
    "/api/v1/enrichments/1e310b02-48b9-4652-ab32-e0d2a370d1f9/events"
  );
});

test("renders lead assessment from completed enrichment event", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        id: "1e310b02-48b9-4652-ab32-e0d2a370d1f9",
        status: "queued",
        progress_percent: 0,
        current_stage: null,
        stage_index: 0,
        stage_count: 0,
        stage_progress_percent: 0,
        message: "Задача поставлена в очередь",
        result: null,
        error: null
      })
    })
    .mockResolvedValue({
      ok: true,
      json: async () => ({
        id: "1e310b02-48b9-4652-ab32-e0d2a370d1f9",
        status: "completed",
        progress_percent: 100,
        current_stage: "metrics",
        stage_index: 1,
        stage_count: 1,
        stage_progress_percent: 100,
        message: "Готово",
        result: sampleResult(),
        error: null
      })
    });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);

  fireEvent.click(screen.getAllByRole("button", { name: /запустить обогащение/i })[0]);
  await waitFor(() => expect(FakeEventSource.instances.length).toBe(1));
  FakeEventSource.instances[0].listeners.get("job_completed")?.(
    new MessageEvent("job_completed", {
      data: JSON.stringify({
        event_type: "job_completed",
        progress_percent: 100,
        current_stage: "metrics",
        stage_index: 1,
        stage_count: 1,
        stage_progress_percent: 100,
        message: "Готово",
        payload: { result: sampleResult() }
      })
    })
  );

  expect(await screen.findByText("Горячий лид")).toBeInTheDocument();
  expect(screen.getByText("95 баллов")).toBeInTheDocument();
  expect(screen.getByText("Умный дом / автоматизация")).toBeInTheDocument();
});

test("loads settings center on demand", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      nlp: {
        pipeline: { stages: [{ name: "segmentation", enabled: true }] },
        signals: [
          {
            type: "video_surveillance",
            label: "Видеонаблюдение",
            group: "Безопасность",
            color: "#455a64",
            confidence: 0.84,
            phrases: [["с", "ндс"]],
            patterns: [
              {
                source_text: "Нужна консультация",
                tokens: [
                  { predicate: "normalized", value: "нужный" },
                  { predicate: "normalized", value: "консультация" }
                ]
              }
            ],
            match: {
              aliases: [{ catalog: "vendors", keys: ["aqara"], kinds: ["vendor"] }],
              facts: [{ types: ["vendor"] }]
            }
          }
        ],
        facts: [],
        alias_matching: {
          normalize_separators: true,
          normalize_yo: true,
          normalize_latin_confusables: true,
          fuzzy_enabled: true,
          fuzzy_min_length: 5,
          fuzzy_max_distance: 1,
          fuzzy_long_min_length: 10,
          fuzzy_long_max_distance: 2,
          fuzzy_excluded_aliases: ["sst", "knx"]
        },
        vendors: [
          {
            key: "aqara",
            canonical: "Aqara",
            type: "vendor",
            aliases: ["Aqara", "Акара"],
            fact_types: ["vendor"]
          }
        ],
        protocols: [],
        devices: [],
        software: [],
        lead_scoring: sampleLeadScoringSettings(),
        source: {
          type: "postgres",
          path: "nlp_config_revisions.config",
          editable: true,
          revision: 1
        }
      },
      system: [{ key: "environment", value: "development", editable: false, source: "env" }]
    })
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);

  fireEvent.click(screen.getByText("Настройки"));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/settings"));
  await waitFor(() => expect(screen.getAllByText("Безопасность").length).toBeGreaterThan(0));
  expect(await screen.findByText("Видеонаблюдение")).toBeInTheDocument();
  fireEvent.click(screen.getByText("Видеонаблюдение"));
  expect(screen.getByLabelText("Папка")).toHaveValue("Безопасность");
  expect(screen.getByText("Точные фразы")).toBeInTheDocument();
  expect(screen.getByLabelText("Добавить точную фразу")).toBeInTheDocument();
  expect(screen.getByLabelText("Редактировать точную фразу: с ндс")).toBeInTheDocument();
  expect(screen.getByLabelText("Удалить точную фразу: с ндс")).toBeInTheDocument();
  expect(screen.getByText("Лемматические фразы")).toBeInTheDocument();
  expect(screen.getByText("Нужна консультация")).toBeInTheDocument();
  expect(screen.getByText("нужный консультация")).toBeInTheDocument();
  expect(screen.getByText("Зависимости от словарей")).toBeInTheDocument();
  expect(screen.getByLabelText("Добавить зависимость от словаря")).toBeInTheDocument();
  expect(screen.getByLabelText("Удалить зависимость от словаря: vendors")).toBeInTheDocument();
  expect(screen.getByLabelText("Каталог зависимости")).toHaveValue("vendors");
  expect(screen.getByText("aqara — Aqara")).toBeInTheDocument();
  expect(screen.getAllByText("vendor").length).toBeGreaterThan(0);
  expect(screen.getByText("Зависимости от фактов")).toBeInTheDocument();
  expect(screen.getByLabelText("Добавить зависимость от факта")).toBeInTheDocument();
  expect(screen.getByLabelText("Удалить зависимость от факта")).toBeInTheDocument();
  fireEvent.click(screen.getByLabelText("Добавить зависимость от словаря"));
  expect(screen.getAllByLabelText(/Удалить зависимость от словаря/)).toHaveLength(2);
  expect(screen.queryByText(/normalized:/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByText("Оценка лида"));
  expect(screen.getByText("Пороги оценки")).toBeInTheDocument();
  expect(screen.getByText("Очереди разбора")).toBeInTheDocument();
  expect(screen.getByText("Прямой лид ПУР")).toBeInTheDocument();
  fireEvent.click(screen.getByText("Словари"));
  expect(screen.getByText("Alias-словари")).toBeInTheDocument();
  expect(screen.getAllByText("Aqara").length).toBeGreaterThan(0);
  expect(screen.getByText("Акара")).toBeInTheDocument();
  expect(screen.getByLabelText("Добавить alias в Вендоры")).toBeInTheDocument();
  fireEvent.click(screen.getByText("Pipeline"));
  expect(screen.getByText("Alias matching")).toBeInTheDocument();
  expect(screen.getByLabelText("Fuzzy alias matching")).toBeChecked();
  expect(screen.getByLabelText("Минимальная длина fuzzy")).toHaveValue(5);
  expect(screen.getByLabelText("Исключения fuzzy")).toHaveValue("sst\nknx");
  fireEvent.click(screen.getByText("Runtime"));
  expect(screen.getByText("environment")).toBeInTheDocument();
});

test("loads analytics dashboard on demand", async () => {
  const run = sampleAnalyticsRun();
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/v1/analytics/runs") {
      return jsonResponse({ runs: [run] });
    }
    if (url === `/api/v1/analytics/runs/${run.id}/summary`) {
      return jsonResponse({
        run,
        aggregates: {
          score_bucket: [
            { kind: "score_bucket", key: "35-59", label: "35-59", count: 10765, payload: {} },
            { kind: "score_bucket", key: "60-89", label: "60-89", count: 3982, payload: {} },
            { kind: "score_bucket", key: "90-129", label: "90-129", count: 1064, payload: {} },
            { kind: "score_bucket", key: "130+", label: "130+", count: 190, payload: {} }
          ],
          signal: [
            {
              kind: "signal",
              key: "designer_context",
              label: "designer_context",
              count: 4525,
              payload: { examples: ["дизайнеры"] }
            }
          ],
          reason: [
            {
              kind: "reason",
              key: "smart_home_platform",
              label: "smart_home_platform",
              count: 3200,
              payload: { examples: ["умный дом"], weight: 35 }
            }
          ],
          solution_area: [
            { kind: "solution_area", key: "automation", label: "Автоматизация", count: 2700, payload: {} }
          ],
          customer_segment: [
            { kind: "customer_segment", key: "designers", label: "Дизайнеры", count: 1800, payload: {} }
          ],
          review_lane: [
            {
              kind: "review_lane",
              key: "direct_pur_lead",
              label: "Прямой лид ПУР",
              count: 339,
              payload: { description: "Сначала смотреть руками" }
            }
          ]
        }
      });
    }
    if (url.startsWith(`/api/v1/analytics/runs/${run.id}/candidates`)) {
      return jsonResponse({
        total: 1,
        limit: 50,
        offset: 0,
        items: [
          {
            message_id: "672162",
            text: "Коллеги, такой запрос от клиента. К кому идти? Посоветуйте контакты по Москве 🙏🏻 Установить и подключить zigbee шлюз для управления через приложение/алису. Свет, розетки, входной замок, ТВ, кондиционер, электрокарниз (если будет), система защиты от протечек.",
            score: 454,
            temperature: "hot",
            review_lane: "direct_pur_lead",
            solution_areas: [
              { type: "automation", label: "Автоматизация", matched_types: ["protocol_gateway"] },
              { type: "security", label: "Безопасность", matched_types: ["water_leak_protection"] }
            ],
            customer_segments: [{ type: "active_request", label: "Активный запрос", matched_types: ["provider_search"] }],
            intent_signals: [{ type: "provider_search", label: "provider_search", matched_types: ["provider_search"] }],
            noise_signals: [],
            reasons: [
              {
                source: "domain_signal",
                key: "protocol_gateway",
                label: "protocol_gateway",
                weight: 20,
                matched_texts: ["zigbee шлюз"]
              },
              {
                source: "domain_signal",
                key: "provider_search",
                label: "provider_search",
                weight: 35,
                matched_texts: ["Посоветуйте контакты"]
              }
            ],
            domain_signals: [
              {
                type: "protocol_gateway",
                label: "Протоколы / шлюзы / интеграции",
                text: "zigbee шлюз",
                source: "yargy",
                color: "#3949ab"
              },
              {
                type: "water_leak_protection",
                label: "Защита от протечек",
                text: "система защиты от протечек",
                source: "yargy",
                color: "#00695c"
              }
            ],
            facts: [
              {
                type: "controlled_device",
                label: "Управляемое устройство",
                text: "розетки",
                source: "yargy"
              }
            ]
          }
        ]
      });
    }
    throw new Error(`Unhandled fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);

  fireEvent.click(screen.getByRole("tab", { name: /аналитика/i }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/analytics/runs"));
  expect(await screen.findByRole("heading", { name: "Аналитика лидов" })).toBeInTheDocument();
  expect(screen.getByText((content) => content.replace(/\s/g, "") === "528953")).toBeInTheDocument();
  expect(screen.getByText((content) => content.replace(/\s/g, "") === "16001")).toBeInTheDocument();
  expect(screen.getByText("3.03%")).toBeInTheDocument();
  expect(screen.getByText("designer_context")).toBeInTheDocument();
  expect(screen.getByText("Прямой лид ПУР")).toBeInTheDocument();
  expect(screen.getByText(/Коллеги, такой запрос от клиента/i)).toBeInTheDocument();
  expect(screen.queryByText("Раскрашенное сообщение")).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Показать разбор сообщения 672162" }));

  expect(await screen.findByText("Раскрашенное сообщение")).toBeInTheDocument();
  expect(screen.getAllByText("Причины score").length).toBeGreaterThan(1);
  expect(screen.getAllByText("Доменные сигналы").length).toBeGreaterThan(1);
  expect(screen.getByText("Факты")).toBeInTheDocument();
  expect(screen.getByText("protocol_gateway")).toBeInTheDocument();
  expect(screen.getAllByText("zigbee шлюз").length).toBeGreaterThan(0);
  expect(screen.getByText(/Управляемое устройство: розетки/)).toBeInTheDocument();
});

test("pages analytics candidates with backend limit and offset", async () => {
  const run = sampleAnalyticsRun();
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/v1/analytics/runs") {
      return jsonResponse({ runs: [run] });
    }
    if (url === `/api/v1/analytics/runs/${run.id}/summary`) {
      return jsonResponse({
        run,
        aggregates: {
          score_bucket: [],
          signal: [],
          reason: [],
          solution_area: [],
          customer_segment: [],
          review_lane: []
        }
      });
    }
    if (url.startsWith(`/api/v1/analytics/runs/${run.id}/candidates`)) {
      const parsed = new URL(url, "http://localhost");
      const offset = Number(parsed.searchParams.get("offset") ?? "0");
      return jsonResponse({
        total: 75,
        limit: 50,
        offset,
        items: [
          {
            message_id: offset === 0 ? "page-1" : "page-2",
            text: offset === 0 ? "Первая страница кандидатов" : "Вторая страница кандидатов",
            score: offset === 0 ? 90 : 80,
            temperature: "warm",
            review_lane: "domain_interest",
            solution_areas: [],
            customer_segments: [],
            intent_signals: [],
            noise_signals: [],
            reasons: [],
            domain_signals: [],
            facts: []
          }
        ]
      });
    }
    throw new Error(`Unhandled fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);

  fireEvent.click(screen.getByRole("tab", { name: /аналитика/i }));
  expect(await screen.findByText("Первая страница кандидатов")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Следующая страница" }));

  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/v1/analytics/runs/${run.id}/candidates?limit=50&offset=50`
    )
  );
  expect(await screen.findByText("Вторая страница кандидатов")).toBeInTheDocument();
});

test("selects analytics filters from summary aggregates", async () => {
  const run = sampleAnalyticsRun();
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/v1/analytics/runs") {
      return jsonResponse({ runs: [run] });
    }
    if (url === `/api/v1/analytics/runs/${run.id}/summary`) {
      return jsonResponse({
        run,
        aggregates: {
          score_bucket: [],
          signal: [
            {
              kind: "signal",
              key: "designer_context",
              label: "designer_context",
              count: 4525,
              payload: {}
            }
          ],
          reason: [
            {
              kind: "reason",
              key: "smart_home_platform",
              label: "smart_home_platform",
              count: 3200,
              payload: {}
            }
          ],
          solution_area: [
            { kind: "solution_area", key: "automation", label: "Автоматизация", count: 2700, payload: {} }
          ],
          customer_segment: [
            { kind: "customer_segment", key: "designers", label: "Дизайнеры", count: 1800, payload: {} }
          ],
          review_lane: [
            { kind: "review_lane", key: "direct_pur_lead", label: "Прямой лид ПУР", count: 339, payload: {} }
          ]
        }
      });
    }
    if (url.startsWith(`/api/v1/analytics/runs/${run.id}/candidates`)) {
      return jsonResponse({
        total: 1,
        limit: 50,
        offset: 0,
        items: [
          {
            message_id: "filtered",
            text: "Отфильтрованный кандидат",
            score: 140,
            temperature: "hot",
            review_lane: "direct_pur_lead",
            solution_areas: [],
            customer_segments: [],
            intent_signals: [],
            noise_signals: [],
            reasons: [],
            domain_signals: [],
            facts: []
          }
        ]
      });
    }
    throw new Error(`Unhandled fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);

  fireEvent.click(screen.getByRole("tab", { name: /аналитика/i }));
  expect(await screen.findByText("Отфильтрованный кандидат")).toBeInTheDocument();

  chooseMuiOption("Сигнал", /designer_context/);
  chooseMuiOption("Причина score", /smart_home_platform/);
  chooseMuiOption("Зона решения", /Автоматизация/);
  chooseMuiOption("Сегмент клиента", /Дизайнеры/);
  chooseMuiOption("Очередь", /Прямой лид ПУР/);

  await waitFor(() =>
    expect(
      fetchMock.mock.calls.some(
        ([calledUrl]) =>
          String(calledUrl) ===
          `/api/v1/analytics/runs/${run.id}/candidates?limit=50&offset=0&signal=designer_context&reason=smart_home_platform&solution_area=automation&customer_segment=designers&lane=direct_pur_lead`
      )
    ).toBe(true)
  );
});

test("adds semantic pattern through backend lemmatization", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        nlp: {
          pipeline: { stages: [{ name: "segmentation", enabled: true }] },
          signals: [
            {
              type: "video_surveillance",
              label: "Видеонаблюдение",
              color: "#455a64",
              confidence: 0.84,
              phrases: [],
              patterns: []
            }
          ],
        facts: [],
        vendors: [],
        protocols: [],
        devices: [],
        software: [],
        lead_scoring: sampleLeadScoringSettings(),
          source: {
            type: "postgres",
            path: "nlp_config_revisions.config",
            editable: true,
            revision: 1
          }
        },
        system: []
      })
    })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        source_text: "Нужна консультация",
        lemma_text: "нужный консультация",
        tokens: [
          { predicate: "normalized", value: "нужный" },
          { predicate: "normalized", value: "консультация" }
        ]
      })
    });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);

  fireEvent.click(screen.getByRole("tab", { name: /настройки/i }));
  expect(await screen.findByText("Видеонаблюдение")).toBeInTheDocument();
  fireEvent.click(screen.getByText("Видеонаблюдение"));
  fireEvent.click(screen.getByRole("button", { name: "Добавить лемматическую фразу" }));
  fireEvent.change(screen.getByLabelText("Текст правила"), {
    target: { value: "Нужна консультация" }
  });
  fireEvent.click(screen.getByRole("button", { name: "Сохранить правило" }));

  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/settings/nlp/semantic-pattern",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ text: "Нужна консультация" })
      })
    )
  );
  expect(await screen.findByText("Нужна консультация")).toBeInTheDocument();
  expect(screen.getByText("нужный консультация")).toBeInTheDocument();
});

test("renders expanded settings help page for all editable NLP settings", () => {
  render(<App />);

  fireEvent.click(screen.getByRole("tab", { name: /справка/i }));

  expect(screen.getByRole("heading", { name: "Справка по настройкам" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Pipeline" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Доменные сигналы" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Факты" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Словари" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Alias matching" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Оценка лида" })).toBeInTheDocument();
  expect(screen.getAllByText("Точное совпадение").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Лемматическое совпадение").length).toBeGreaterThan(0);
  expect(screen.getByText(/type пишем латиницей в snake_case/i)).toBeInTheDocument();
  expect(screen.getByText(/label - русское название/i)).toBeInTheDocument();
  expect(screen.getByText(/confidence - доверие к правилу/i)).toBeInTheDocument();
  expect(screen.getByText(/group - папка/i)).toBeInTheDocument();
  expect(screen.getByText(/Связь сигналов и словарей/i)).toBeInTheDocument();
  expect(screen.getByText(/каталог `vendors` и alias `neptun`/i)).toBeInTheDocument();
  expect(screen.getByText(/casefold/i)).toBeInTheDocument();
  expect(screen.getByText(/fuzzy_min_length/i)).toBeInTheDocument();
  expect(screen.getAllByText(/короткие alias/i).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/match.aliases/i).length).toBeGreaterThan(0);
  expect(screen.getByText(/source=alias_catalog/i)).toBeInTheDocument();
  expect(screen.getAllByText(/weights.signals/i).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/weights.facts/i).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/review_lanes/i).length).toBeGreaterThan(0);
  expect(screen.getByText(/score = сумма весов/i)).toBeInTheDocument();
  expect(screen.getByText(/negative weights/i)).toBeInTheDocument();
  expect(screen.getByText("нужна консультация")).toBeInTheDocument();
  expect(screen.getByText("нужный консультация")).toBeInTheDocument();
  expect(screen.queryByText(/caseless:/)).not.toBeInTheDocument();
  expect(screen.queryByText(/normalized:/)).not.toBeInTheDocument();
});

function sampleLeadScoringSettings() {
  return {
    lead_threshold: 35,
    warm_threshold: 60,
    hot_threshold: 90,
    signal_weights: { video_surveillance: 35 },
    fact_weights: { solution_area: 15 },
    solution_areas: {
      security: {
        label: "Безопасность",
        signal_types: ["video_surveillance"],
        fact_types: ["solution_area"]
      }
    },
    customer_segments: {},
    intent_signal_types: ["provider_search"],
    noise_signal_types: ["diy_or_equipment_only"],
    review_lanes: [
      {
        key: "direct_pur_lead",
        label: "Прямой лид ПУР",
        description: "Сначала смотреть руками",
        priority: 200,
        match_groups: [
          { solution_area_types: ["security"], reason_keys: [] },
          { reason_keys: ["provider_search"], solution_area_types: [] }
        ],
        excluded_signal_types: [],
        excluded_noise_signal_types: ["diy_or_equipment_only"]
      }
    ]
  };
}

function sampleAnalyticsRun() {
  return {
    id: "1ce74b24-4b8a-4f65-ac1d-3649b9e1e226",
    name: "designer-channel-2026-05-07-full-8workers",
    source: "batch",
    input_path: "artifacts/designer-channel/messages.jsonl",
    run_dir: "artifacts/designer-channel/runs/2026-05-07-full-8workers",
    processed: 528953,
    skipped: 0,
    failed: 0,
    leads: 16001,
    candidate_rate: 3.025032,
    started_at: "2026-05-07T18:00:00+00:00",
    finished_at: "2026-05-07T19:15:43+00:00",
    imported_at: "2026-05-07T19:20:00+00:00",
    summary: {}
  };
}

function jsonResponse(payload: unknown) {
  return {
    ok: true,
    json: async () => payload
  };
}

function chooseMuiOption(comboboxName: string, optionName: RegExp) {
  fireEvent.mouseDown(screen.getByRole("combobox", { name: comboboxName }));
  fireEvent.click(screen.getByRole("option", { name: optionName }));
}

function sampleResult() {
  return {
    original_text: "Нужен умный дом",
    normalized_text: "Нужен умный дом",
    entities: [],
    facts: [],
    domain_signals: [],
    tokens: [],
    syntax: [],
    metrics: {
      character_count: 16,
      sentence_count: 1,
      token_count: 3,
      entity_count: 0,
      fact_count: 0,
      domain_signal_count: 0
    },
    pipeline_trace: [],
    lead_assessment: {
      is_lead: true,
      score: 95,
      temperature: "hot",
      solution_areas: [
        {
          type: "smart_home",
          label: "Умный дом / автоматизация",
          matched_types: ["smart_home_automation"]
        }
      ],
      customer_segments: [],
      intent_signals: [],
      noise_signals: [],
      reasons: [
        {
          source: "domain_signal",
          key: "smart_home_automation",
          label: "smart_home_automation",
          weight: 35,
          matched_texts: ["умный дом"]
        }
      ]
    }
  };
}
