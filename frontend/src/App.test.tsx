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
            ]
          }
        ],
        facts: [],
        vendors: [
          {
            key: "aqara",
            canonical: "Aqara",
            type: "vendor",
            aliases: ["Aqara", "Акара"],
            signal_types: ["smart_home_platform"],
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

  fireEvent.click(screen.getByRole("tab", { name: /настройки/i }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/settings"));
  expect(await screen.findByText("Видеонаблюдение")).toBeInTheDocument();
  fireEvent.click(screen.getByText("Видеонаблюдение"));
  expect(screen.getByText("Точные фразы")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Добавить точную фразу" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Редактировать точную фразу: с ндс" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Удалить точную фразу: с ндс" })).toBeInTheDocument();
  expect(screen.getByText("Лемматические фразы")).toBeInTheDocument();
  expect(screen.getByText("Нужна консультация")).toBeInTheDocument();
  expect(screen.getByText("нужный консультация")).toBeInTheDocument();
  expect(screen.queryByText(/normalized:/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Оценка лида" }));
  expect(screen.getByText("Пороги оценки")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Словари" }));
  expect(screen.getByText("Alias-словари")).toBeInTheDocument();
  expect(screen.getAllByText("Aqara").length).toBeGreaterThan(0);
  expect(screen.getByText("Акара")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Добавить alias в Вендоры" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Runtime" }));
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
            text: "Подскажите на счет умного дома Яндекс, как подключить свет к Алисе?",
            score: 454,
            temperature: "hot",
            solution_areas: [{ type: "automation", label: "Автоматизация", matched_types: ["smart_home_platform"] }],
            customer_segments: [],
            intent_signals: [],
            noise_signals: [],
            reasons: [
              {
                source: "domain_signal",
                key: "smart_home_platform",
                label: "smart_home_platform",
                weight: 35,
                matched_texts: ["умного дома"]
              }
            ],
            domain_signals: [{ type: "smart_home_platform", label: "Умный дом", text: "умного дома" }],
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

  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/analytics/runs"));
  expect(await screen.findByRole("heading", { name: "Аналитика лидов" })).toBeInTheDocument();
  expect(screen.getByText((content) => content.replace(/\s/g, "") === "528953")).toBeInTheDocument();
  expect(screen.getByText((content) => content.replace(/\s/g, "") === "16001")).toBeInTheDocument();
  expect(screen.getByText("3.03%")).toBeInTheDocument();
  expect(screen.getByText("designer_context")).toBeInTheDocument();
  expect(screen.getByText(/Подскажите на счет умного дома Яндекс/i)).toBeInTheDocument();
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
          customer_segment: []
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

test("renders settings help page for rule matching modes", () => {
  render(<App />);

  fireEvent.click(screen.getByRole("tab", { name: /справка/i }));

  expect(screen.getByRole("heading", { name: "Справка по настройкам" })).toBeInTheDocument();
  expect(screen.getAllByText("Точное совпадение").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Лемматическое совпадение").length).toBeGreaterThan(0);
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
    noise_signal_types: ["diy_or_equipment_only"]
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
