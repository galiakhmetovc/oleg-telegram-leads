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
