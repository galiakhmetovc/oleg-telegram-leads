import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";

const originalScrollIntoView = window.HTMLElement.prototype.scrollIntoView;
const defaultRouteMessageTemplate = [
  "Лид ПУР",
  "",
  "Оценка: {score} ({temperature})",
  "Очередь: {review_lane_label}",
  "Зоны решения: {solution_areas}",
  "Сегменты: {customer_segments}",
  "",
  "Почему сработало:",
  "{reasons_detailed}",
  "",
  "Текст:",
  "{text_preview}"
].join("\n");

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
  window.history.replaceState(null, "", "/");
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-color-scheme");
  document.documentElement.style.colorScheme = "";
  window.HTMLElement.prototype.scrollIntoView = originalScrollIntoView;
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    if (String(input) === "/api/v1/auth/me") {
      return jsonResponse({ authenticated: true, username: "admin" });
    }
    if (String(input) === "/api/v1/settings") {
      return jsonResponse(sampleSettingsSnapshot());
    }
    if (String(input) === "/api/v1/analytics/runs") {
      return jsonResponse({ runs: [] });
    }
    throw new Error(`Unhandled fetch: ${String(input)}`);
  }));
});

afterEach(() => {
  cleanup();
  window.HTMLElement.prototype.scrollIntoView = originalScrollIntoView;
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-color-scheme");
  document.documentElement.style.colorScheme = "";
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

test("opens analytics by default and renders text testing workspace", async () => {
  render(<App />);

  expect(await screen.findByRole("heading", { name: "Аналитика лидов" })).toBeInTheDocument();
  expect(screen.getByText("Нет данных аналитики. Подключите Telegram-источники или импортируйте тестовый batch.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: "Тестирование" }));

  expect(screen.getByLabelText("Произвольный текст")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /запустить обогащение/i })).toBeInTheDocument();
});

test("uses scrollable top navigation for narrow screens", () => {
  render(<App />);

  const tabList = screen.getByRole("tablist", { name: "Основная навигация" });

  expect(tabList.closest(".MuiTabs-scroller")).toHaveClass("MuiTabs-scrollableX");
});

test("opens the rule configurator from the top navigation", async () => {
  render(<App />);

  fireEvent.click(screen.getByRole("tab", { name: "Конфигуратор" }));

  expect(await screen.findByRole("heading", { name: "Rule IDE" })).toBeInTheDocument();
  expect(screen.getByText("Конфигуратор правил")).toBeInTheDocument();
  expect(screen.getByText("NLP-ревизия #1")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Умный дом 1 сигнал 0 фактов/i })).toBeInTheDocument();
});

test("toggles dark theme and persists the operator preference", async () => {
  const { unmount } = render(<App />);

  fireEvent.click(await screen.findByRole("button", { name: "Включить темную тему" }));

  expect(document.documentElement.dataset.colorScheme).toBe("dark");
  expect(document.documentElement.style.colorScheme).toBe("dark");
  expect(window.localStorage.getItem("pur-leads-theme-mode")).toBe("dark");
  expect(screen.getByRole("button", { name: "Включить светлую тему" })).toBeInTheDocument();

  unmount();
  render(<App />);

  expect(await screen.findByRole("button", { name: "Включить светлую тему" })).toBeInTheDocument();
  expect(document.documentElement.dataset.colorScheme).toBe("dark");
});

test("requires login when backend reports anonymous session", async () => {
  let loginBody: unknown = null;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/v1/auth/me") {
      return jsonResponse({ authenticated: false, username: null });
    }
    if (url === "/api/v1/auth/login" && init?.method === "POST") {
      loginBody = JSON.parse(String(init.body));
      return jsonResponse({ authenticated: true, username: "admin" });
    }
    if (url === "/api/v1/settings") {
      return jsonResponse(sampleSettingsSnapshot());
    }
    if (url === "/api/v1/analytics/runs") {
      return jsonResponse({ runs: [] });
    }
    throw new Error(`Unhandled fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);

  expect(await screen.findByText("Вход в операторский интерфейс")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Пароль"), { target: { value: "pur-dev-password" } });
  fireEvent.click(screen.getByRole("button", { name: "Войти" }));

  await waitFor(() =>
    expect(loginBody).toEqual({ username: "admin", password: "pur-dev-password" })
  );
  expect(await screen.findByRole("heading", { name: "Аналитика лидов" })).toBeInTheDocument();
});

test("renders runtime logs and system status tabs", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/v1/auth/me") {
      return jsonResponse({ authenticated: true, username: "admin" });
    }
    if (url === "/api/v1/settings") {
      return jsonResponse(sampleSettingsSnapshot());
    }
    if (url === "/api/v1/analytics/runs") {
      return jsonResponse({ runs: [] });
    }
    if (url === "/api/v1/runtime/logs?limit=50&offset=0") {
      return jsonResponse({
        total: 75,
        limit: 50,
        offset: 0,
        items: [
          {
            created_at: "2026-05-08T12:00:00Z",
            service: "userbot",
            level: "info",
            message: "Получено сообщение Telegram",
            payload: { telegram_message_id: 10 }
          }
        ]
      });
    }
    if (url === "/api/v1/runtime/logs?limit=50&offset=0&service=userbot&level=error&q=FloodWait") {
      return jsonResponse({
        total: 75,
        limit: 50,
        offset: 0,
        items: [
          {
            created_at: "2026-05-08T12:05:00Z",
            service: "userbot",
            level: "error",
            message: "Telegram FloodWait",
            payload: { seconds: 1554 }
          }
        ]
      });
    }
    if (url === "/api/v1/runtime/logs?limit=50&offset=50&service=userbot&level=error&q=FloodWait") {
      return jsonResponse({
        total: 75,
        limit: 50,
        offset: 50,
        items: [
          {
            created_at: "2026-05-08T12:06:00Z",
            service: "userbot",
            level: "error",
            message: "Telegram FloodWait next page",
            payload: { seconds: 900 }
          }
        ]
      });
    }
    if (url === "/api/v1/runtime/status") {
      return jsonResponse({
        services: [
          {
            service: "backend",
            status: "ok",
            details: {
              environment: "development",
              code_version: "dev",
              active_nlp_config_revision: 31,
              active_nlp_config_revision_id: "6fad33ee-7cd2-49f0-92d3-1a21d07c6480",
              auth_enabled: true,
              public_base_url: "https://secclaw.qlbc.ru:19443"
            }
          },
          {
            service: "worker",
            status: "ok",
            details: {
              backend_code_version: "dev",
              latest_worker_code_version: "dev",
              worker_code_stale: false,
              active_nlp_config_revision: 31,
              latest_worker_nlp_config_revision: 31,
              worker_config_stale: false
            }
          },
          {
            service: "userbot",
            status: "warning",
            details: {
              accounts_total: 2,
              accounts_enabled: 1,
              source_chats_total: 4,
              source_chats_by_status: { resolved: 3, error: 1 },
              messages_total: 125,
              latest_message_at: "2026-05-08T12:10:00Z",
              errored_sources: [{ title: "AeternalLead MessagesTest", last_error: "Telegram FloodWait: 1649s" }]
            }
          }
        ]
      });
    }
    throw new Error(`Unhandled fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);

  fireEvent.click(screen.getByRole("tab", { name: "Логи" }));
  expect(await screen.findByText("Получено сообщение Telegram")).toBeInTheDocument();
  fireEvent.mouseDown(screen.getByRole("combobox", { name: "Сервис" }));
  fireEvent.click(await screen.findByRole("option", { name: "userbot" }));
  fireEvent.mouseDown(screen.getByRole("combobox", { name: "Уровень" }));
  fireEvent.click(await screen.findByRole("option", { name: "error" }));
  fireEvent.change(screen.getByLabelText("Поиск"), { target: { value: "FloodWait" } });
  fireEvent.click(screen.getByRole("button", { name: "Применить фильтры" }));

  expect(await screen.findByText("Telegram FloodWait")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Следующая страница" }));

  expect(await screen.findByText("Telegram FloodWait next page")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("tab", { name: "Статус системы" }));
  expect(await screen.findByText("Свежесть правил и кода")).toBeInTheDocument();
  expect(screen.getAllByText("Активная NLP-ревизия").length).toBeGreaterThan(0);
  expect(screen.getAllByText("#31").length).toBeGreaterThan(0);
  expect(screen.getByText("Worker использует активную ревизию")).toBeInTheDocument();
  expect(screen.getByText("Код worker актуален")).toBeInTheDocument();
  expect(await screen.findByText("backend")).toBeInTheDocument();
  expect(screen.getByText("worker")).toBeInTheDocument();
  expect(screen.getByText("userbot")).toBeInTheDocument();
  expect(screen.getByText("Окружение")).toBeInTheDocument();
  expect(screen.getByText("development")).toBeInTheDocument();
  expect(screen.getAllByText("Версия кода").length).toBeGreaterThan(0);
  expect(screen.getByText("Аккаунтов всего")).toBeInTheDocument();
  expect(screen.getByText("2")).toBeInTheDocument();
  expect(screen.getByText("Чаты по статусам")).toBeInTheDocument();
  expect(screen.getByText("resolved: 3, error: 1")).toBeInTheDocument();
  expect(screen.getByText("Проблемные источники")).toBeInTheDocument();
  expect(screen.getByText(/AeternalLead MessagesTest/)).toBeInTheDocument();
});

test("shows active NLP revision in settings and links saved settings to golden checks", async () => {
  const savedSnapshot = {
    ...sampleSettingsSnapshot().nlp,
    source: {
      type: "postgres",
      path: "nlp_config_revisions.config",
      editable: true,
      revision: 2
    }
  };
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/v1/auth/me") {
      return jsonResponse({ authenticated: true, username: "admin" });
    }
    if (url === "/api/v1/settings") {
      return jsonResponse(sampleSettingsSnapshot());
    }
    if (url === "/api/v1/analytics/runs") {
      return jsonResponse({ runs: [] });
    }
    if (url === "/api/v1/settings/nlp" && init?.method === "PUT") {
      return jsonResponse(savedSnapshot);
    }
    throw new Error(`Unhandled fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);

  fireEvent.click(screen.getByRole("tab", { name: "Настройки" }));
  expect(await screen.findByText("Активная NLP-ревизия #1")).toBeInTheDocument();
  fireEvent.click(screen.getByText("Pipeline"));
  fireEvent.click(screen.getByLabelText("segmentation включен"));
  fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));

  expect(await screen.findByText(/NLP-настройки сохранены как ревизия #2/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Проверить Golden" })).toHaveAttribute("href", "#/golden");
  expect(screen.getByText("Активная NLP-ревизия #2")).toBeInTheDocument();
});

test("renders project documentation grouped by files", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/v1/auth/me") {
      return jsonResponse({ authenticated: true, username: "admin" });
    }
    if (url === "/api/v1/settings") {
      return jsonResponse(sampleSettingsSnapshot());
    }
    if (url === "/api/v1/analytics/runs") {
      return jsonResponse({ runs: [] });
    }
    if (url === "/api/v1/project-docs") {
      return jsonResponse({
        items: [
          {
            path: "AGENTS.md",
            title: "Project Rules",
            size_bytes: 10,
            updated_at: "2026-05-08T12:00:00Z"
          },
          {
            path: "README.md",
            title: "PUR Leads v2",
            size_bytes: 20,
            updated_at: "2026-05-08T12:00:01Z"
          }
        ]
      });
    }
    if (url === "/api/v1/project-docs/README.md") {
      return jsonResponse({
        path: "README.md",
        title: "PUR Leads v2",
        size_bytes: 20,
        updated_at: "2026-05-08T12:00:01Z",
        content: "# PUR Leads v2\n\nДокументация проекта."
      });
    }
    throw new Error(`Unhandled fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);

  fireEvent.click(await screen.findByRole("tab", { name: "Проектная документация" }));
  expect(await screen.findByRole("heading", { name: "Проектная документация" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /README.md/ }));

  expect(await screen.findByText("Документация проекта.")).toBeInTheDocument();
});

test("shows background settings loading while startup settings are loading", async () => {
  let resolveSettings!: (response: ReturnType<typeof jsonResponse>) => void;
  const settingsPromise = new Promise<ReturnType<typeof jsonResponse>>((resolve) => {
    resolveSettings = resolve;
  });
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    if (String(input) === "/api/v1/settings") {
      return settingsPromise;
    }
    throw new Error(`Unhandled fetch: ${String(input)}`);
  }));

  render(<App />);

  expect(screen.getByText("Загружаю настройки и словари")).toBeInTheDocument();

  resolveSettings(jsonResponse(sampleSettingsSnapshot()));

  await waitFor(() => expect(screen.queryByText("Загружаю настройки и словари")).not.toBeInTheDocument());
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

  fireEvent.click(screen.getByRole("tab", { name: "Тестирование" }));
  fireEvent.click(screen.getAllByRole("button", { name: /запустить обогащение/i })[0]);

  await waitFor(() =>
    expect(fetchMock.mock.calls.some(([calledUrl]) => String(calledUrl) === "/api/v1/enrichments")).toBe(true)
  );
  expect(FakeEventSource.instances[0]?.url).toContain(
    "/api/v1/enrichments/1e310b02-48b9-4652-ab32-e0d2a370d1f9/events"
  );
});

test("renders lead assessment from completed enrichment event", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/v1/settings") {
      return jsonResponse(sampleSettingsSnapshot());
    }
    if (url === "/api/v1/enrichments") {
      return jsonResponse({
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
      });
    }
    if (url === "/api/v1/enrichments/1e310b02-48b9-4652-ab32-e0d2a370d1f9") {
      return jsonResponse({
        id: "1e310b02-48b9-4652-ab32-e0d2a370d1f9",
        status: "completed",
        progress_percent: 100,
        current_stage: "metrics",
        stage_index: 1,
        stage_count: 1,
        stage_progress_percent: 100,
        message: "Готово",
        nlp_config_revision_id: "6fad33ee-7cd2-49f0-92d3-1a21d07c6480",
        nlp_config_revision: 31,
        result: sampleResult(),
        error: null
      });
    }
    throw new Error(`Unhandled fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);

  fireEvent.click(screen.getByRole("tab", { name: "Тестирование" }));
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

  expect((await screen.findAllByText("Горячий лид")).length).toBeGreaterThan(0);
  expect(screen.getByText("NLP-ревизия #31")).toBeInTheDocument();
  expect(screen.getAllByText("95 баллов").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Умный дом / автоматизация").length).toBeGreaterThan(0);
  expect(screen.getByText("Точный расчет оценки лида")).toBeInTheDocument();
  expect(screen.getByText(/score = max/)).toBeInTheDocument();
  expect(screen.getByText("Расчет очереди разбора")).toBeInTheDocument();
  expect(screen.getAllByText("Прямой лид ПУР").length).toBeGreaterThan(0);
  expect(screen.getByText("Визуальная цепочка анализа")).toBeInTheDocument();
  expect(screen.getAllByText("Фрагмент текста").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Словарь / правило").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Факт").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Сигнал").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Вклад в score").length).toBeGreaterThan(0);
  expect(screen.getAllByText("+35").length).toBeGreaterThan(0);
});

test("renders annotation ranges correctly after emoji", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/v1/settings") {
      return jsonResponse(sampleSettingsSnapshot());
    }
    if (url === "/api/v1/enrichments") {
      return jsonResponse({
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
      });
    }
    if (url === "/api/v1/enrichments/1e310b02-48b9-4652-ab32-e0d2a370d1f9") {
      return jsonResponse({
        id: "1e310b02-48b9-4652-ab32-e0d2a370d1f9",
        status: "completed",
        progress_percent: 100,
        current_stage: "metrics",
        stage_index: 1,
        stage_count: 1,
        stage_progress_percent: 100,
        message: "Готово",
        result: sampleResultWithEmojiRange(),
        error: null
      });
    }
    throw new Error(`Unhandled fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);

  fireEvent.click(screen.getByRole("tab", { name: "Тестирование" }));
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
        payload: { result: sampleResultWithEmojiRange() }
      })
    })
  );

  expect((await screen.findAllByText("электрокарниз")).length).toBeGreaterThan(0);
  expect(screen.queryByText(", электрокарн")).not.toBeInTheDocument();
});

test("opens settings sections from enrichment overview shortcuts", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/v1/enrichments") {
      return jsonResponse({
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
      });
    }
    if (url === "/api/v1/enrichments/1e310b02-48b9-4652-ab32-e0d2a370d1f9") {
      return jsonResponse({
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
      });
    }
    if (url === "/api/v1/settings") {
      return jsonResponse(sampleSettingsSnapshot());
    }
    throw new Error(`Unhandled fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);

  fireEvent.click(screen.getByRole("tab", { name: "Тестирование" }));
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

  fireEvent.click(await screen.findByRole("button", { name: /открыть словари/i }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/settings"));
  expect(await screen.findByText("Alias-словари")).toBeInTheDocument();
});

test("opens setting links as modal on left click and keeps cached settings for full page", async () => {
  let settingsCalls = 0;
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/v1/settings") {
      settingsCalls += 1;
      return jsonResponse(sampleSettingsSnapshot());
    }
    if (url === "/api/v1/enrichments") {
      return jsonResponse({
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
      });
    }
    if (url === "/api/v1/enrichments/1e310b02-48b9-4652-ab32-e0d2a370d1f9") {
      return jsonResponse({
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
      });
    }
    throw new Error(`Unhandled fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);

  await waitFor(() => expect(settingsCalls).toBe(1));

  fireEvent.click(screen.getByRole("tab", { name: "Тестирование" }));
  fireEvent.change(screen.getByLabelText("Произвольный текст"), {
    target: { value: "Контекст входного текста должен сохраниться" }
  });
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

  expect(await screen.findByRole("table", { name: "Точный расчет оценки лида" })).toBeInTheDocument();
  const aliasLink = screen
    .getAllByRole("link", { name: "Устройство: Хаб умного дома" })
    .find((link) => link.getAttribute("href") === "#/settings/aliases/devices/smart_home_hub");
  expect(aliasLink).toBeDefined();
  expect(aliasLink).toHaveAttribute("href", "#/settings/aliases/devices/smart_home_hub");

  fireEvent.click(aliasLink!);

  expect(await screen.findByRole("dialog", { name: "Настройка: Хаб умного дома" })).toBeInTheDocument();
  expect(screen.getByText("Каталог: devices")).toBeInTheDocument();
  expect(document.querySelector(".result-card")).toBeInTheDocument();
  expect(settingsCalls).toBe(1);

  fireEvent.click(screen.getByRole("link", { name: "Открыть страницу настройки" }));

  expect(await screen.findByRole("heading", { name: "Центр настроек" })).toBeInTheDocument();
  expect(screen.queryByRole("dialog", { name: "Настройка: Хаб умного дома" })).not.toBeInTheDocument();
  expect(document.querySelector(".settings-shell")).toBeInTheDocument();
  expect(document.querySelector(".settings-target-shell")).not.toBeInTheDocument();
  expect(document.getElementById("settings-target-aliases-devices-smart_home_hub")).toHaveClass("settings-target-highlight");
  expect(settingsCalls).toBe(1);

  fireEvent.click(screen.getByRole("tab", { name: "Тестирование" }));

  expect(screen.getByLabelText("Произвольный текст")).toHaveValue("Контекст входного текста должен сохраниться");
});

test("opens settings deeplink directly as full-width settings page", async () => {
  const scrollIntoView = vi.fn();
  window.HTMLElement.prototype.scrollIntoView = scrollIntoView;
  let settingsCalls = 0;
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    if (String(input) === "/api/v1/settings") {
      settingsCalls += 1;
      return jsonResponse(sampleSettingsSnapshot());
    }
    throw new Error(`Unhandled fetch: ${String(input)}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  window.location.hash = "#/settings/signals/smart_home_automation";

  render(<App />);

  expect(await screen.findByRole("heading", { name: "Центр настроек" })).toBeInTheDocument();
  expect(screen.getAllByText("Доменные сигналы").length).toBeGreaterThan(0);
  expect(screen.getByLabelText("type")).toHaveValue("smart_home_automation");
  expect(document.querySelector(".settings-shell")).toBeInTheDocument();
  expect(document.querySelector(".settings-target-shell")).not.toBeInTheDocument();
  expect(document.getElementById("settings-target-signals-smart_home_automation")).toHaveClass("settings-target-highlight");
  await waitFor(() => expect(scrollIntoView).toHaveBeenCalled());
  expect(settingsCalls).toBe(1);
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
              facts: [{ types: ["alias:vendors:aqara", "vendor"] }]
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
      notifications: sampleNotificationSettings(),
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
  expect(screen.getByText("Зависимости от фактов")).toBeInTheDocument();
  expect(screen.getByLabelText("Добавить зависимость от факта")).toBeInTheDocument();
  expect(screen.getByLabelText("Удалить зависимость от факта")).toBeInTheDocument();
  expect(screen.getByText("Вендоры: Aqara (aqara)")).toBeInTheDocument();
  expect(screen.getByText("vendor (vendor)")).toBeInTheDocument();
  fireEvent.click(screen.getByLabelText("Добавить зависимость от факта"));
  expect(screen.getAllByLabelText("Удалить зависимость от факта")).toHaveLength(2);
  expect(screen.queryByText(/normalized:/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByText("Оценка лида"));
  expect(screen.getByText("Пороги оценки")).toBeInTheDocument();
  expect(screen.getByText("Ограничители score")).toBeInTheDocument();
  expect(screen.getByText("Явный шум")).toBeInTheDocument();
  expect(screen.getByLabelText("noise_signal_types")).toHaveValue("diy_or_equipment_only");
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
}, 15000);

test("edits telegram bots chats and routes and sends chat test message", async () => {
  let savedBody: unknown = null;
  let testBody: unknown = null;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/v1/settings") {
      return jsonResponse(sampleSettingsSnapshot());
    }
    if (url === "/api/v1/settings/notifications" && init?.method === "PUT") {
      savedBody = JSON.parse(String(init.body));
      return jsonResponse({
        bots: [
          {
            id: "main_bot",
            name: "Основной бот",
            enabled: true,
            has_token: true,
            token_masked: "123456:***CRET"
          }
        ],
        chats: [
          {
            id: "sales_chat",
            name: "Продажи",
            enabled: true,
            telegram_chat_id: "-100123"
          }
        ],
        routes: [
          {
            id: "hot_leads",
            name: "Горячие лиды",
            enabled: true,
            priority: 100,
            bot_id: "main_bot",
            chat_id: "sales_chat",
            match_mode: "all",
            conditions: { is_lead: true, score_min: 80, review_lanes: ["direct_pur_lead"] },
            message_template: "Лид {score}: {text}"
          }
        ],
        updated_at: "2026-05-08T00:00:00Z"
      });
    }
    if (url === "/api/v1/settings/notifications/telegram/chats/sales_chat/test" && init?.method === "POST") {
      testBody = JSON.parse(String(init.body));
      return jsonResponse({
        ok: true,
        message: "Тестовое сообщение отправлено",
        telegram_message_id: 777,
        chat_id: "-100123"
      });
    }
    throw new Error(`Unhandled fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);

  fireEvent.click(screen.getByText("Настройки"));
  fireEvent.click(await screen.findByText("Уведомления"));
  expect(await screen.findByRole("heading", { name: "Уведомления" })).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Добавить бота" }));
  fireEvent.change(screen.getByLabelText("ID бота"), { target: { value: "main_bot" } });
  fireEvent.change(screen.getByLabelText("Название бота"), { target: { value: "Основной бот" } });
  fireEvent.change(screen.getByLabelText("Токен бота"), {
    target: { value: "123456:ABCDEFSECRET" }
  });

  fireEvent.click(screen.getByRole("tab", { name: "Чаты" }));
  fireEvent.click(screen.getByRole("button", { name: "Добавить чат" }));
  fireEvent.change(screen.getByLabelText("ID чата"), { target: { value: "sales_chat" } });
  fireEvent.change(screen.getByLabelText("Название чата"), { target: { value: "Продажи" } });
  fireEvent.change(screen.getByLabelText("Telegram chat_id"), { target: { value: "-100123" } });

  fireEvent.click(screen.getByRole("tab", { name: "Маршруты" }));
  fireEvent.click(screen.getByRole("button", { name: "Добавить маршрут" }));
  fireEvent.change(screen.getByLabelText("ID маршрута"), { target: { value: "hot_leads" } });
  fireEvent.change(screen.getByLabelText("Название маршрута"), { target: { value: "Горячие лиды" } });
  fireEvent.change(screen.getByLabelText("Минимальный score"), { target: { value: "80" } });
  fireEvent.click(screen.getByRole("button", { name: "Сохранить уведомления" }));

  await waitFor(() =>
    expect(savedBody).toEqual({
      bots: [{ id: "main_bot", name: "Основной бот", enabled: true, token: "123456:ABCDEFSECRET" }],
      chats: [{ id: "sales_chat", name: "Продажи", enabled: true, telegram_chat_id: "-100123" }],
      routes: [
        {
          id: "hot_leads",
          name: "Горячие лиды",
          enabled: true,
          priority: 100,
          bot_id: "main_bot",
          chat_id: "sales_chat",
          match_mode: "all",
          conditions: {
            is_lead: true,
            score_min: 80,
            score_max: null,
            temperatures: [],
            review_lanes: [],
            solution_areas: [],
            customer_segments: [],
            domain_signals: [],
            facts: [],
            reasons: [],
            noise_signals: []
          },
          message_template: defaultRouteMessageTemplate
        }
      ]
    })
  );
  fireEvent.click(screen.getByRole("tab", { name: "Боты" }));
  expect(await screen.findByText(/123456:\*\*\*CRET/)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("tab", { name: "Чаты" }));
  fireEvent.change(screen.getByLabelText("Текст тестового сообщения"), {
    target: { value: "Проверка связи" }
  });
  fireEvent.click(screen.getByRole("button", { name: "Отправить тест в чат Продажи" }));

  await waitFor(() => expect(testBody).toEqual({ bot_id: "main_bot", message: "Проверка связи" }));
  expect(await screen.findByText("Тестовое сообщение отправлено")).toBeInTheDocument();
}, 20000);

test("edits telegram userbot ingestion settings and starts login flow", async () => {
  let savedBody: any = null;
  let sendCodeCalled = false;
  let statusRefreshed = false;
  let settingsRequestCount = 0;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/v1/settings") {
      settingsRequestCount += 1;
      return jsonResponse(sampleSettingsSnapshot());
    }
    if (url === "/api/v1/settings/telegram-ingestion" && init === undefined) {
      statusRefreshed = true;
      return jsonResponse({
        accounts: [
          {
            id: savedBody.accounts[0].id,
            name: "Основной userbot",
            phone: "+79990000000",
            api_id: 12345,
            enabled: true,
            status: "authorized",
            has_api_hash: true,
            api_hash_masked: "api-***cret",
            has_session: true,
            last_error: null,
            telegram_user_id: "42",
            telegram_username: "krab_ai_agent",
            created_at: "2026-05-08T00:00:00Z",
            updated_at: "2026-05-08T00:01:00Z"
          }
        ],
        chats: [
          {
            id: savedBody.chats[0].id,
            account_id: savedBody.accounts[0].id,
            title: "Дизайнеры",
            input_ref: "@designers_chat",
            telegram_chat_id: "1292716582",
            enabled: true,
            status: "resolved",
            last_message_id: 720417,
            last_error: null,
            created_at: "2026-05-08T00:00:00Z",
            updated_at: "2026-05-08T00:01:00Z"
          }
        ]
      });
    }
    if (url === "/api/v1/settings/telegram-ingestion" && init?.method === "PUT") {
      savedBody = JSON.parse(String(init.body));
      return jsonResponse({
        accounts: [
          {
            id: savedBody.accounts[0].id,
            name: "Основной userbot",
            phone: "+79990000000",
            api_id: 12345,
            enabled: true,
            status: "draft",
            has_api_hash: true,
            api_hash_masked: "api-***cret",
            has_session: false,
            last_error: null,
            telegram_user_id: null,
            telegram_username: null,
            created_at: "2026-05-08T00:00:00Z",
            updated_at: "2026-05-08T00:00:00Z"
          }
        ],
        chats: [
          {
            id: savedBody.chats[0].id,
            account_id: savedBody.accounts[0].id,
            title: "Дизайнеры",
            input_ref: "@designers_chat",
            telegram_chat_id: null,
            enabled: true,
            status: "draft",
            last_message_id: null,
            last_error: null,
            created_at: "2026-05-08T00:00:00Z",
            updated_at: "2026-05-08T00:00:00Z"
          }
        ]
      });
    }
    if (url.includes("/api/v1/settings/telegram-ingestion/accounts/") && url.endsWith("/send-code")) {
      sendCodeCalled = true;
      return jsonResponse({
        status: "code_sent",
        account: {
          id: savedBody.accounts[0].id,
          name: "Основной userbot",
          phone: "+79990000000",
          api_id: 12345,
          enabled: true,
          status: "code_sent",
          has_api_hash: true,
          api_hash_masked: "api-***cret",
          has_session: true,
          last_error: null,
          telegram_user_id: null,
          telegram_username: null,
          created_at: "2026-05-08T00:00:00Z",
          updated_at: "2026-05-08T00:00:00Z"
        }
      });
    }
    throw new Error(`Unhandled fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);

  fireEvent.click(screen.getByText("Настройки"));
  fireEvent.click(await screen.findByText("Telegram вход"));
  expect(await screen.findByRole("heading", { name: "Telegram вход" })).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Добавить userbot" }));
  fireEvent.change(screen.getByLabelText("Телефон"), { target: { value: "+79990000000" } });
  fireEvent.change(screen.getByLabelText("Telegram app api_id"), { target: { value: "12345" } });
  fireEvent.change(screen.getByLabelText("Telegram app api_hash"), { target: { value: "api-hash-secret" } });

  fireEvent.click(screen.getByRole("tab", { name: "Чаты-источники" }));
  fireEvent.click(screen.getByRole("button", { name: "Добавить чат-источник" }));
  fireEvent.change(screen.getByLabelText("Название источника"), { target: { value: "Дизайнеры" } });
  fireEvent.change(screen.getByLabelText("Telegram input_ref"), { target: { value: "@designers_chat" } });
  fireEvent.click(screen.getByRole("button", { name: "Сохранить Telegram вход" }));

  await waitFor(() => expect(savedBody.accounts[0]).toMatchObject({
    name: "Основной userbot",
    phone: "+79990000000",
    api_id: 12345,
    api_hash: "api-hash-secret"
  }));
  expect(savedBody.accounts[0].id).toMatch(
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
  );
  expect(savedBody.chats[0]).toMatchObject({
    title: "Дизайнеры",
    input_ref: "@designers_chat"
  });
  expect(savedBody.chats[0].id).toMatch(
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
  );

  fireEvent.click(screen.getByRole("tab", { name: "Аккаунты" }));
  fireEvent.click(await screen.findByRole("button", { name: "Отправить код" }));

  await waitFor(() => expect(sendCodeCalled).toBe(true));
  expect(await screen.findByText("Код Telegram отправлен")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Обновить статус" }));

  await waitFor(() => expect(statusRefreshed).toBe(true));
  fireEvent.click(screen.getByRole("tab", { name: "Чаты-источники" }));
  expect(await screen.findByText(/cursor 720417/)).toBeInTheDocument();
  expect(settingsRequestCount).toBeGreaterThan(0);
}, 20000);

test("loads analytics dashboard on demand", async () => {
  const run = sampleAnalyticsRun();
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/v1/settings") {
      return jsonResponse(sampleSettingsSnapshot());
    }
    if (url === "/api/v1/analytics/runs") {
      return jsonResponse({ runs: [run] });
    }
    if (url === "/api/v1/analytics/review-eval") {
      return jsonResponse(sampleReviewEvalReport());
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
          source_chat: [
            { kind: "source_chat", key: "chat-designers", label: "Чат дизайнеров", count: 120, payload: {} }
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
            ],
            received_at: "2026-05-08T12:30:00Z",
            source_chat_id: "chat-designers",
            source_chat_title: "Чат дизайнеров"
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
  expect(screen.getByRole("tab", { name: "Кандидаты" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("tab", { name: "Обзор" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "Качество ревью" })).toBeInTheDocument();
  expect(screen.queryByText("Качество по ревью")).not.toBeInTheDocument();
  expect(screen.queryByText("Доменные сигналы")).not.toBeInTheDocument();
  expect(screen.getAllByText("Чат дизайнеров").length).toBeGreaterThan(0);
  expect(screen.getByText((content) => content.includes("08.05.2026"))).toBeInTheDocument();
  expect(screen.getByText(/Коллеги, такой запрос от клиента/i)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("tab", { name: "Качество ревью" }));
  expect(window.location.hash).toMatch(/^#\/analytics\/quality/);
  expect(await screen.findByText("Качество по ревью")).toBeInTheDocument();
  expect(screen.getByText("Размечено: 2")).toBeInTheDocument();
  expect(screen.getByText("FP: 1")).toBeInTheDocument();
  expect(screen.getByText("FN: 1")).toBeInTheDocument();
  expect(screen.getByText("False Positives")).toBeInTheDocument();
  expect(screen.getByText("Добро пожаловать в чат Dahua Support")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "479071" })).toHaveAttribute("href", "#/analytics/review/fp-1");
  expect(screen.queryByText(/Коллеги, такой запрос от клиента/i)).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("tab", { name: "Обзор" }));
  expect(window.location.hash).toMatch(/^#\/analytics\/overview/);
  expect(screen.getByText((content) => content.replace(/\s/g, "") === "528953")).toBeInTheDocument();
  expect(screen.getByText((content) => content.replace(/\s/g, "") === "16001")).toBeInTheDocument();
  expect(screen.getByText("3.03%")).toBeInTheDocument();
  expect(screen.getByText("Доменные сигналы")).toBeInTheDocument();
  expect(screen.getByText("Очереди разбора")).toBeInTheDocument();
  expect(screen.queryByText("designer_context")).not.toBeInTheDocument();
  expect(screen.queryByText("Сначала смотреть руками")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Показать блок Score" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Показать блок Доменные сигналы" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Показать блок Причины score" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Показать блок Сегменты" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Показать блок Очереди разбора" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Показать блок Доменные сигналы" }));
  expect(screen.getByText("designer_context")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Скрыть блок Доменные сигналы" }));
  await waitFor(() => expect(screen.queryByText("designer_context")).not.toBeInTheDocument());
  expect(screen.queryByText(/Коллеги, такой запрос от клиента/i)).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("tab", { name: "Кандидаты" }));
  expect(window.location.hash).toMatch(/^#\/analytics(\?|$)/);
  expect(await screen.findByText(/Коллеги, такой запрос от клиента/i)).toBeInTheDocument();
  expect(screen.queryByText("Раскрашенное сообщение")).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Показать разбор сообщения 672162" }));

  expect(await screen.findByText("Раскрашенное сообщение")).toBeInTheDocument();
  expect(screen.getByText("Визуальная цепочка анализа")).toBeInTheDocument();
  expect(screen.getAllByText("Причины score").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Доменные сигналы").length).toBeGreaterThan(0);
  expect(screen.getByText("Факты")).toBeInTheDocument();
  expect(screen.getAllByText("protocol_gateway").length).toBeGreaterThan(0);
  expect(screen.getAllByText("zigbee шлюз").length).toBeGreaterThan(0);
  expect(screen.getByText(/Управляемое устройство: розетки/)).toBeInTheDocument();
});

test("opens golden examples panel and runs selected example", async () => {
  const exampleId = "7b353178-7b60-4f7e-a329-6f926a8ff1af";
  const jobId = "6c49f5d2-a5bc-4d7b-bec8-51d8db0606d1";
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/v1/settings") {
      return jsonResponse(sampleSettingsSnapshot());
    }
    if (url === "/api/v1/analytics/runs") {
      return jsonResponse({ runs: [] });
    }
    if (url === "/api/v1/golden-examples") {
      return jsonResponse({
        total: 1,
        limit: 50,
        offset: 0,
        items: [
          {
            id: exampleId,
            title: "Горячий smart home",
            text: "Нужен подрядчик на zigbee шлюз",
            expected_verdict: "lead",
            comment: "Должен быть лидом",
            source_message_id: null,
            source_chat_title: null,
            telegram_message_id: null,
            telegram_message_url: null,
            last_enrichment_job_id: null,
            created_at: "2026-05-09T12:00:00Z",
            updated_at: "2026-05-09T12:00:00Z"
          }
        ]
      });
    }
    if (url === `/api/v1/golden-examples/${exampleId}/run` && init?.method === "POST") {
      return jsonResponse({
        example: {
          id: exampleId,
          title: "Горячий smart home",
          text: "Нужен подрядчик на zigbee шлюз",
          expected_verdict: "lead",
          comment: "Должен быть лидом",
          source_message_id: null,
          source_chat_title: null,
          telegram_message_id: null,
          telegram_message_url: null,
          last_enrichment_job_id: jobId,
          created_at: "2026-05-09T12:00:00Z",
          updated_at: "2026-05-09T12:01:00Z"
        },
        job: {
          id: jobId,
          status: "queued",
          progress_percent: 0,
          current_stage: null,
          stage_index: 0,
          stage_count: 0,
          stage_progress_percent: 0,
          message: "Задача поставлена в очередь",
          result: null,
          error: null
        }
      });
    }
    if (url === `/api/v1/enrichments/${jobId}`) {
      return jsonResponse({
        id: jobId,
        status: "completed",
        progress_percent: 100,
        current_stage: "completed",
        stage_index: 0,
        stage_count: 0,
        stage_progress_percent: 100,
        message: "Обработка завершена",
        result: sampleResult(),
        error: null
      });
    }
    throw new Error(`Unhandled fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);

  fireEvent.click(screen.getByRole("tab", { name: "Golden" }));

  expect(await screen.findByRole("heading", { name: "Golden-примеры" })).toBeInTheDocument();
  expect(screen.getByText("Горячий smart home")).toBeInTheDocument();
  expect(screen.getByLabelText("Произвольный текст")).toHaveValue("Нужен подрядчик на zigbee шлюз");

  fireEvent.click(screen.getByRole("button", { name: /запустить golden/i }));

  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(`/api/v1/golden-examples/${exampleId}/run`, { method: "POST" })
  );
  await waitFor(() => expect(FakeEventSource.instances[0]?.url).toBe(`/api/v1/enrichments/${jobId}/events`));
  FakeEventSource.instances[0].listeners.get("job_completed")?.(
    new MessageEvent("job_completed", {
      data: JSON.stringify({
        event_type: "job_completed",
        progress_percent: 100,
        current_stage: "completed",
        stage_index: 0,
        stage_count: 0,
        stage_progress_percent: 100,
        message: "Обработка завершена",
        payload: { result: sampleResult() }
      })
    })
  );

  expect(await screen.findByRole("table", { name: "Точный расчет оценки лида" })).toBeInTheDocument();
});

test("adds analytics candidate to golden examples", async () => {
  const run = sampleAnalyticsRun();
  const candidate = {
    message_id: "38aee5ca-2604-4892-bafe-af01172711c2",
    text: "Подскажите контакты по видеонаблюдению",
    score: 95,
    temperature: "hot",
    review_lane: "direct_pur_lead",
    solution_areas: [],
    customer_segments: [],
    intent_signals: [],
    noise_signals: [],
    reasons: [],
    domain_signals: [],
    facts: [],
    received_at: "2026-05-08T12:30:00Z",
    source_chat_id: "chat-designers",
    source_chat_title: "Чат дизайнеров"
  };
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/v1/settings") {
      return jsonResponse(sampleSettingsSnapshot());
    }
    if (url === "/api/v1/analytics/runs") {
      return jsonResponse({ runs: [run] });
    }
    if (url === `/api/v1/analytics/runs/${run.id}/summary`) {
      return jsonResponse({ run, aggregates: {} });
    }
    if (url.startsWith(`/api/v1/analytics/runs/${run.id}/candidates`)) {
      return jsonResponse({ total: 1, limit: 50, offset: 0, items: [candidate] });
    }
    if (url === `/api/v1/golden-examples/from-message/${candidate.message_id}` && init?.method === "POST") {
      return jsonResponse({
        id: "7b353178-7b60-4f7e-a329-6f926a8ff1af",
        title: "Чат дизайнеров #",
        text: candidate.text,
        expected_verdict: null,
        comment: "",
        source_message_id: candidate.message_id,
        source_chat_title: "Чат дизайнеров",
        telegram_message_id: null,
        telegram_message_url: null,
        last_enrichment_job_id: null,
        created_at: "2026-05-09T12:00:00Z",
        updated_at: "2026-05-09T12:00:00Z"
      });
    }
    throw new Error(`Unhandled fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);

  fireEvent.click(screen.getByRole("tab", { name: /аналитика/i }));

  expect(await screen.findByText("Подскажите контакты по видеонаблюдению")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: `Добавить в golden ${candidate.message_id}` }));

  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/v1/golden-examples/from-message/${candidate.message_id}`,
      { method: "POST" }
    )
  );
  expect(await screen.findByText("Сообщение добавлено в golden-примеры")).toBeInTheDocument();
});

test("opens analytics deeplink by expanding and scrolling to candidate row", async () => {
  window.history.replaceState(null, "", "/#/analytics/message/focus-1");
  const scrollIntoView = vi.fn();
  window.HTMLElement.prototype.scrollIntoView = scrollIntoView;
  const run = sampleAnalyticsRun();
  const candidate = {
    message_id: "focus-1",
    text: "Нужен проект умного дома и контакты подрядчика.",
    score: 150,
    temperature: "hot",
    review_lane: "direct_pur_lead",
    solution_areas: [{ type: "automation", label: "Автоматизация", matched_types: ["smart_home_automation"] }],
    customer_segments: [],
    intent_signals: [],
    noise_signals: [],
    reasons: [
      {
        source: "domain_signal",
        key: "smart_home_automation",
        label: "Умный дом / автоматизация",
        weight: 35,
        matched_texts: ["умного дома"]
      }
    ],
    domain_signals: [
      {
        type: "smart_home_automation",
        label: "Умный дом / автоматизация",
        text: "умного дома",
        source: "yargy"
      }
    ],
    facts: []
  };
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/v1/auth/me") {
      return jsonResponse({ authenticated: true, username: "admin" });
    }
    if (url === "/api/v1/settings") {
      return jsonResponse(sampleSettingsSnapshot());
    }
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
    if (url === "/api/v1/analytics/messages/focus-1") {
      return jsonResponse(candidate);
    }
    if (url.startsWith(`/api/v1/analytics/runs/${run.id}/candidates`)) {
      return jsonResponse({
        total: 1,
        limit: 50,
        offset: 0,
        items: [candidate]
      });
    }
    throw new Error(`Unhandled fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);

  expect(
    await screen.findByRole("button", { name: "Скрыть разбор сообщения focus-1" }, { timeout: 5000 })
  ).toBeInTheDocument();
  expect(screen.getByText("Раскрашенное сообщение")).toBeInTheDocument();
  await waitFor(() => expect(scrollIntoView).toHaveBeenCalled());
});

test("links expanded analytics evidence to settings targets", async () => {
  const run = sampleAnalyticsRun();
  const candidate = {
    message_id: "linked-1",
    text: "Нужно установить zigbee шлюз и электрокарниз.",
    score: 95,
    temperature: "hot",
    review_lane: "direct_pur_lead",
    solution_areas: [
      { type: "smart_home", label: "Умный дом / автоматизация", matched_types: ["smart_home_automation"] }
    ],
    customer_segments: [
      { type: "provider_request", label: "Активный запрос", matched_types: ["installation_request"] }
    ],
    intent_signals: [{ type: "installation_request", label: "Запрос на установку" }],
    noise_signals: [],
    reasons: [
      {
        source: "domain_signal",
        key: "smart_home_automation",
        label: "Умный дом / автоматизация",
        weight: 35,
        matched_texts: ["zigbee шлюз"]
      },
      {
        source: "fact",
        key: "automation_component",
        label: "Компонент автоматизации",
        weight: 12,
        matched_texts: ["электрокарниз"]
      }
    ],
    domain_signals: [
      {
        type: "smart_home_automation",
        label: "Умный дом / автоматизация",
        text: "zigbee шлюз",
        source: "alias_catalog",
        range: { start: 18, stop: 29 },
        settings_refs: [
          {
            section: "signals",
            key: "smart_home_automation",
            label: "Умный дом / автоматизация",
            kind: "rule"
          },
          {
            section: "aliases",
            catalog: "devices",
            key: "smart_home_hub",
            label: "Устройство: Хаб умного дома",
            kind: "alias"
          }
        ]
      }
    ],
    facts: [
      {
        type: "automation_component",
        label: "Компонент автоматизации",
        text: "электрокарниз",
        source: "alias_catalog",
        range: { start: 32, stop: 45 },
        settings_refs: [
          {
            section: "aliases",
            catalog: "devices",
            key: "electric_curtain",
            label: "Устройство: Электрокарниз",
            kind: "alias"
          }
        ]
      }
    ],
    review: null
  };
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/v1/auth/me") {
      return jsonResponse({ authenticated: true, username: "admin" });
    }
    if (url === "/api/v1/settings") {
      return jsonResponse(sampleSettingsSnapshot());
    }
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
          source_chat: [],
          review_lane: []
        }
      });
    }
    if (url.startsWith(`/api/v1/analytics/runs/${run.id}/candidates`)) {
      return jsonResponse({ total: 1, limit: 50, offset: 0, items: [candidate] });
    }
    throw new Error(`Unhandled fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);

  expect(await screen.findByText("Нужно установить zigbee шлюз и электрокарниз.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Показать разбор сообщения linked-1" }));

  await screen.findByText("Раскрашенное сообщение");
  expect(settingsLinkHrefs()).toEqual(
    expect.arrayContaining([
      expect.stringContaining("#/settings/signals/smart_home_automation"),
      expect.stringContaining("#/settings/aliases/devices/smart_home_hub"),
      expect.stringContaining("#/settings/aliases/devices/electric_curtain"),
      expect.stringContaining("#/settings/lead-scoring/signal-weight/smart_home_automation"),
      expect.stringContaining("#/settings/lead-scoring/fact-weight/automation_component"),
      expect.stringContaining("#/settings/lead-scoring/solution-area/smart_home"),
      expect.stringContaining("#/settings/lead-scoring/customer-segment/provider_request"),
      expect.stringContaining("#/settings/lead-scoring/review-lane/direct_pur_lead")
    ])
  );
});

test("opens analytics review page and saves verdict comment", async () => {
  window.history.replaceState(null, "", "/#/analytics/review/focus-1");
  const candidate = {
    message_id: "focus-1",
    text: "DSS Express или DSS Professional с лицензиями на каналы видео и модуль управления парковкой",
    score: 107,
    temperature: "hot",
    review_lane: "direct_pur_lead",
    solution_areas: [{ type: "smart_home", label: "Умный дом / автоматизация" }],
    customer_segments: [],
    intent_signals: [],
    noise_signals: [],
    reasons: [],
    domain_signals: [],
    facts: [],
    review: null
  };
  let reviewPayload: unknown = null;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/v1/auth/me") {
      return jsonResponse({ authenticated: true, username: "admin" });
    }
    if (url === "/api/v1/settings") {
      return jsonResponse(sampleSettingsSnapshot());
    }
    if (url === "/api/v1/analytics/messages/focus-1" && !init) {
      return jsonResponse(candidate);
    }
    if (url === "/api/v1/analytics/messages/focus-1/review" && init?.method === "PUT") {
      reviewPayload = JSON.parse(String(init.body));
      return jsonResponse({
        ...candidate,
        review: {
          source_message_id: "focus-1",
          verdict: "not_lead",
          comment: "Нет запроса на подрядчика",
          tags: [],
          created_at: "2026-05-08T13:00:00Z",
          updated_at: "2026-05-08T13:05:00Z"
        }
      });
    }
    throw new Error(`Unhandled fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);

  expect(await screen.findByRole("heading", { name: "Ревью сообщения" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Не лид" }));
  fireEvent.change(screen.getByLabelText("Комментарий ревью"), { target: { value: "Нет запроса на подрядчика" } });
  fireEvent.click(screen.getByRole("button", { name: "Сохранить ревью" }));

  await waitFor(() =>
    expect(reviewPayload).toEqual({ verdict: "not_lead", comment: "Нет запроса на подрядчика", tags: [] })
  );
  expect(await screen.findByText("Ревью сохранено")).toBeInTheDocument();
  expect(await screen.findAllByText("Не лид (ревью)")).toHaveLength(2);
  expect(screen.queryByText("Горячий лид")).not.toBeInTheDocument();
});

test("review constructor saves selected text as noise setting", async () => {
  window.history.replaceState(null, "", "/#/analytics/review/focus-1");
  const candidate = {
    message_id: "focus-1",
    text: "DSS Express или DSS Professional с лицензиями на каналы видео и модуль управления парковкой",
    score: 107,
    temperature: "hot",
    review_lane: "direct_pur_lead",
    solution_areas: [{ type: "smart_home", label: "Умный дом / автоматизация" }],
    customer_segments: [],
    intent_signals: [],
    noise_signals: [],
    reasons: [],
    domain_signals: [],
    facts: [],
    review: null
  };
  let noisePayload: unknown = null;
  const updatedNlp = {
    ...sampleSettingsSnapshot().nlp,
    source: {
      type: "postgres",
      path: "nlp_config_revisions.config",
      editable: true,
      revision: 2
    }
  };
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/v1/auth/me") {
      return jsonResponse({ authenticated: true, username: "admin" });
    }
    if (url === "/api/v1/settings") {
      return jsonResponse(sampleSettingsSnapshot());
    }
    if (url === "/api/v1/analytics/messages/focus-1" && !init) {
      return jsonResponse(candidate);
    }
    if (url === "/api/v1/settings/nlp/constructor/noise" && init?.method === "POST") {
      noisePayload = JSON.parse(String(init.body));
      return jsonResponse({
        text: "DSS Express",
        signal_type: "operator_noise",
        signal_label: "Операторский шум",
        phrase: ["dss", "express"],
        created_rule: true,
        created_phrase: true,
        nlp: updatedNlp
      });
    }
    throw new Error(`Unhandled fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(window, "getSelection").mockReturnValue({ toString: () => "DSS Express" } as Selection);

  render(<App />);

  expect(await screen.findByRole("heading", { name: "Ревью сообщения" })).toBeInTheDocument();
  fireEvent.mouseUp(screen.getAllByText(candidate.text)[0]);
  expect(await screen.findByText(/Выделено:/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "В шум" }));

  await waitFor(() =>
    expect(noisePayload).toEqual({
      text: "DSS Express",
      source_message_id: "focus-1"
    })
  );
  expect(await screen.findByText(/Добавлено в шумовой сигнал/)).toBeInTheDocument();
  expect(screen.getByText("operator_noise: dss express")).toBeInTheDocument();
});

test("review constructor saves selected text to aliases facts and signals", async () => {
  window.history.replaceState(null, "", "/#/analytics/review/focus-1");
  const candidate = {
    message_id: "focus-1",
    text: "Аккара нужна до завтра. Камера DSS важна для проекта.",
    score: 35,
    temperature: "cold",
    review_lane: "domain_interest",
    solution_areas: [],
    customer_segments: [],
    intent_signals: [],
    noise_signals: [],
    reasons: [],
    domain_signals: [],
    facts: [],
    review: null
  };
  const updatedNlp = {
    ...sampleSettingsSnapshot().nlp,
    source: {
      type: "postgres",
      path: "nlp_config_revisions.config",
      editable: true,
      revision: 2
    }
  };
  const constructorPayloads: Record<string, unknown> = {};
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/v1/auth/me") {
      return jsonResponse({ authenticated: true, username: "admin" });
    }
    if (url === "/api/v1/settings") {
      return jsonResponse(sampleSettingsSnapshot());
    }
    if (url === "/api/v1/analytics/messages/focus-1" && !init) {
      return jsonResponse(candidate);
    }
    if (url === "/api/v1/settings/nlp/constructor/alias" && init?.method === "POST") {
      constructorPayloads.alias = JSON.parse(String(init.body));
      return jsonResponse({
        text: "Аккара",
        catalog: "vendors",
        key: "aqara",
        canonical: "Aqara",
        created_target: false,
        created_entry: true,
        settings_ref: { section: "aliases", catalog: "vendors", key: "aqara", label: "Aqara" },
        nlp: updatedNlp
      });
    }
    if (url === "/api/v1/settings/nlp/constructor/fact" && init?.method === "POST") {
      constructorPayloads.fact = JSON.parse(String(init.body));
      return jsonResponse({
        text: "до завтра",
        collection: "facts",
        rule_type: "deadline",
        rule_label: "Срок",
        phrase_kind: "exact",
        exact_phrase: ["до", "завтра"],
        created_target: false,
        created_entry: true,
        settings_ref: { section: "facts", key: "deadline", label: "Срок" },
        nlp: updatedNlp
      });
    }
    if (url === "/api/v1/settings/nlp/constructor/signal" && init?.method === "POST") {
      constructorPayloads.signal = JSON.parse(String(init.body));
      return jsonResponse({
        text: "Камера DSS",
        collection: "signals",
        rule_type: "operator_dss_context",
        rule_label: "DSS контекст",
        phrase_kind: "semantic",
        semantic_pattern: {
          source_text: "Камера DSS",
          tokens: [{ normalized: "камера" }, { normalized: "dss" }]
        },
        created_target: true,
        created_entry: true,
        settings_ref: { section: "signals", key: "operator_dss_context", label: "DSS контекст" },
        nlp: updatedNlp
      });
    }
    throw new Error(`Unhandled fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  const selectionSpy = vi.spyOn(window, "getSelection");

  render(<App />);

  expect(await screen.findByRole("heading", { name: "Ревью сообщения" })).toBeInTheDocument();
  selectionSpy.mockReturnValue({ toString: () => "Аккара" } as Selection);
  fireEvent.mouseUp(screen.getAllByText(candidate.text)[0]);
  fireEvent.click(screen.getByRole("button", { name: "В словарь" }));
  expect(await screen.findByRole("dialog", { name: "Добавить в словарь" })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("key"), { target: { value: "aqara" } });
  fireEvent.click(screen.getByRole("button", { name: "Сохранить в словарь" }));

  await waitFor(() =>
    expect(constructorPayloads.alias).toEqual({
      text: "Аккара",
      source_message_id: "focus-1",
      catalog: "vendors",
      key: "aqara",
      canonical: "Аккара",
      alias_type: "vendor",
      fact_types: ["vendor"],
      confidence: 0.7
    })
  );
  expect(await screen.findByText(/Добавлено в словарь/)).toBeInTheDocument();

  selectionSpy.mockReturnValue({ toString: () => "до завтра" } as Selection);
  fireEvent.mouseUp(screen.getAllByText(candidate.text)[0]);
  fireEvent.click(screen.getByRole("button", { name: "В факт" }));
  expect(await screen.findByRole("dialog", { name: "Добавить в факт" })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("type"), { target: { value: "deadline" } });
  fireEvent.click(screen.getByRole("button", { name: "Сохранить факт" }));

  await waitFor(() =>
    expect(constructorPayloads.fact).toEqual({
      text: "до завтра",
      source_message_id: "focus-1",
      target_type: "deadline",
      target_label: "до завтра",
      group: "Операторские факты",
      phrase_kind: "exact",
      confidence: 0.5
    })
  );
  expect(await screen.findByText(/Добавлено в факт/)).toBeInTheDocument();

  selectionSpy.mockReturnValue({ toString: () => "Камера DSS" } as Selection);
  fireEvent.mouseUp(screen.getAllByText(candidate.text)[0]);
  fireEvent.click(screen.getByRole("button", { name: "В доменный сигнал" }));
  expect(await screen.findByRole("dialog", { name: "Добавить в доменный сигнал" })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("type"), { target: { value: "operator_dss_context" } });
  fireEvent.change(screen.getByLabelText("label"), { target: { value: "DSS контекст" } });
  fireEvent.change(screen.getByLabelText("Тип совпадения"), { target: { value: "semantic" } });
  fireEvent.click(screen.getByRole("button", { name: "Сохранить сигнал" }));

  await waitFor(() =>
    expect(constructorPayloads.signal).toEqual({
      text: "Камера DSS",
      source_message_id: "focus-1",
      target_type: "operator_dss_context",
      target_label: "DSS контекст",
      group: "Операторские сигналы",
      phrase_kind: "semantic",
      color: "#0b57d0",
      confidence: 0.5
    })
  );
  expect(await screen.findByText(/Добавлено в доменный сигнал/)).toBeInTheDocument();
}, 20000);

test("review page supports hotkeys, structured tags, and save next", async () => {
  const run = sampleAnalyticsRun();
  const returnHash = `#/analytics?limit=50&offset=0&review_status=unreviewed&run=${run.id}`;
  window.history.replaceState(
    null,
    "",
    `/#/analytics/review/focus-1?return=${encodeURIComponent(returnHash)}`
  );
  const firstCandidate = {
    message_id: "focus-1",
    text: "Продам камеру Hikvision без монтажа",
    score: 70,
    temperature: "warm",
    review_lane: "noise",
    solution_areas: [],
    customer_segments: [],
    intent_signals: [],
    noise_signals: [{ type: "equipment_only", label: "Только оборудование" }],
    reasons: [
      {
        source: "domain_signal",
        key: "video_surveillance",
        label: "Видеонаблюдение",
        weight: 35,
        matched_texts: ["камера Hikvision"]
      }
    ],
    domain_signals: [],
    facts: [],
    review: null
  };
  const nextCandidate = {
    ...firstCandidate,
    message_id: "next-1",
    text: "Следующий кандидат без ревью",
    review_lane: "direct_pur_lead",
    noise_signals: [],
    review: null
  };
  let reviewPayload: unknown = null;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/v1/auth/me") {
      return jsonResponse({ authenticated: true, username: "admin" });
    }
    if (url === "/api/v1/settings") {
      return jsonResponse(sampleSettingsSnapshot());
    }
    if (url === "/api/v1/analytics/messages/focus-1" && !init) {
      return jsonResponse(firstCandidate);
    }
    if (url === "/api/v1/analytics/messages/focus-1/review" && init?.method === "PUT") {
      reviewPayload = JSON.parse(String(init.body));
      return jsonResponse({
        ...firstCandidate,
        review: {
          source_message_id: "focus-1",
          verdict: "not_lead",
          comment: "",
          tags: ["equipment_only"],
          created_at: "2026-05-08T13:00:00Z",
          updated_at: "2026-05-08T13:05:00Z"
        }
      });
    }
    if (url.startsWith(`/api/v1/analytics/runs/${run.id}/candidates`)) {
      const params = new URL(url, "http://localhost").searchParams;
      expect(params.get("review_status")).toBe("unreviewed");
      return jsonResponse({ total: 1, limit: 50, offset: 0, items: [nextCandidate] });
    }
    if (url === "/api/v1/analytics/messages/next-1" && !init) {
      return jsonResponse(nextCandidate);
    }
    throw new Error(`Unhandled fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);

  expect(await screen.findByRole("heading", { name: "Ревью сообщения" })).toBeInTheDocument();
  fireEvent.keyDown(window, { key: "2" });
  expect(screen.getByRole("button", { name: "Не лид" })).toHaveClass("MuiButton-contained");
  fireEvent.click(screen.getByRole("button", { name: "Только оборудование" }));
  fireEvent.click(screen.getByRole("button", { name: "Сохранить и следующий" }));

  await waitFor(() =>
    expect(reviewPayload).toEqual({ verdict: "not_lead", comment: "", tags: ["equipment_only"] })
  );
  expect((await screen.findAllByText("Следующий кандидат без ревью")).length).toBeGreaterThan(0);
});

test("pages analytics candidates with backend limit and offset", async () => {
  const run = sampleAnalyticsRun();
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/v1/settings") {
      return jsonResponse(sampleSettingsSnapshot());
    }
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
    if (url === "/api/v1/settings") {
      return jsonResponse(sampleSettingsSnapshot());
    }
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
          source_chat: [
            { kind: "source_chat", key: "chat-designers", label: "Чат дизайнеров", count: 7, payload: {} }
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
            facts: [],
            received_at: "2026-05-08T12:30:00Z",
            source_chat_id: "chat-designers",
            source_chat_title: "Чат дизайнеров"
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
  chooseMuiOption("Канал", /Чат дизайнеров/);
  fireEvent.change(screen.getByLabelText("Дата с"), { target: { value: "2026-05-08T00:00" } });
  fireEvent.change(screen.getByLabelText("Дата по"), { target: { value: "2026-05-08T23:59" } });
  fireEvent.click(screen.getByRole("button", { name: "Применить" }));

  await waitFor(() =>
    expect(
      fetchMock.mock.calls.some(([calledUrl]) => {
        const called = String(calledUrl);
        if (!called.startsWith(`/api/v1/analytics/runs/${run.id}/candidates`)) {
          return false;
        }
        const params = new URL(called, "http://localhost").searchParams;
        return (
          params.get("limit") === "50" &&
          params.get("offset") === "0" &&
          params.get("signal") === "designer_context" &&
          params.get("source_chat_id") === "chat-designers" &&
          params.get("received_from") === "2026-05-08T00:00:00.000Z" &&
          params.get("received_to") === "2026-05-08T23:59:00.000Z"
        );
      })
    ).toBe(true)
  );
});

test("filters analytics candidates by review status and verdict", async () => {
  const run = sampleAnalyticsRun();
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/v1/settings") {
      return jsonResponse(sampleSettingsSnapshot());
    }
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
          source_chat: [],
          review_lane: [
            { kind: "review_lane", key: "direct_pur_lead", label: "Прямой лид ПУР", count: 1, payload: {} }
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
            message_id: "reviewed",
            text: "Разобранный кандидат",
            score: 90,
            temperature: "warm",
            review_lane: "direct_pur_lead",
            solution_areas: [],
            customer_segments: [],
            intent_signals: [],
            noise_signals: [],
            reasons: [],
            domain_signals: [],
            facts: [],
            review: {
              source_message_id: "reviewed",
              verdict: "not_lead",
              comment: "Нет запроса на подрядчика",
              tags: [],
              created_at: "2026-05-08T13:00:00Z",
              updated_at: "2026-05-08T13:05:00Z"
            }
          }
        ]
      });
    }
    throw new Error(`Unhandled fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);

  fireEvent.click(screen.getByRole("tab", { name: /аналитика/i }));
  expect(await screen.findByText("Разобранный кандидат")).toBeInTheDocument();
  expect(screen.getByText("Не лид")).toBeInTheDocument();
  expect(screen.getByText("Прямой лид ПУР")).toBeInTheDocument();
  const reviewLink = screen.getByRole("link", { name: /ревью/i });
  expect(reviewLink).toHaveAttribute("href", expect.stringContaining("#/analytics/review/reviewed?return="));

  chooseMuiOption("Статус ревью", /С ревью/);
  chooseMuiOption("Вердикт", /Не лид/);

  await waitFor(() =>
    expect(
      fetchMock.mock.calls.some(([calledUrl]) => {
        const called = String(calledUrl);
        if (!called.startsWith(`/api/v1/analytics/runs/${run.id}/candidates`)) {
          return false;
        }
        const params = new URL(called, "http://localhost").searchParams;
        return params.get("review_status") === "reviewed" && params.get("verdict") === "not_lead";
      })
    ).toBe(true)
  );
});

test("adds semantic pattern through backend lemmatization", async () => {
  const settingsPayload = {
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
    notifications: sampleNotificationSettings(),
    system: []
  };
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/v1/settings") {
      return jsonResponse(settingsPayload);
    }
    if (url === "/api/v1/settings/nlp/semantic-pattern" && init?.method === "POST") {
      return jsonResponse({
        source_text: "Нужна консультация",
        lemma_text: "нужный консультация",
        tokens: [
          { predicate: "normalized", value: "нужный" },
          { predicate: "normalized", value: "консультация" }
        ]
      });
    }
    throw new Error(`Unhandled fetch: ${url}`);
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
  expect(screen.getAllByText(/alias:vendors:neptun/i).length).toBeGreaterThan(0);
  expect(screen.getByText(/casefold/i)).toBeInTheDocument();
  expect(screen.getByText(/fuzzy_min_length/i)).toBeInTheDocument();
  expect(screen.getAllByText(/короткие alias/i).length).toBeGreaterThan(0);
  expect(screen.queryByText(/match.aliases/i)).not.toBeInTheDocument();
  expect(screen.getAllByText(/source=fact_dependency/i).length).toBeGreaterThan(0);
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
    lead_veto_signal_types: ["diy_or_equipment_only"],
    score_caps: [
      {
        key: "hard_noise",
        label: "Явный шум",
        max_score: 0,
        signal_types: [],
        fact_types: [],
        reason_keys: [],
        noise_signal_types: ["diy_or_equipment_only"],
        excluded_signal_types: [],
        excluded_fact_types: [],
        excluded_reason_keys: [],
        excluded_noise_signal_types: []
      }
    ],
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

function sampleSettingsSnapshot() {
  return {
    nlp: {
      pipeline: { stages: [{ name: "segmentation", enabled: true }] },
      alias_matching: {
        normalize_separators: true,
        normalize_yo: true,
        normalize_latin_confusables: true,
        fuzzy_enabled: true,
        fuzzy_min_length: 5,
        fuzzy_max_distance: 1,
        fuzzy_long_min_length: 10,
        fuzzy_long_max_distance: 2,
        fuzzy_excluded_aliases: []
      },
      signals: [
        {
          type: "smart_home_automation",
          label: "Умный дом / автоматизация",
          group: "Умный дом",
          color: "#0b57d0",
          confidence: 0.9,
          phrases: [],
          patterns: [],
          match: { facts: [{ types: ["alias:devices:smart_home_hub"] }] }
        }
      ],
      facts: [
        {
          type: "controlled_device",
          label: "Управляемое устройство",
          group: "Устройства",
          color: null,
          confidence: 0.8,
          phrases: [],
          patterns: [],
          match: { facts: [] }
        }
      ],
      vendors: [
        {
          key: "aqara",
          canonical: "Aqara",
          type: "vendor",
          aliases: ["Aqara"],
          fact_types: ["vendor"]
        }
      ],
      protocols: [],
      devices: [
        {
          key: "smart_home_hub",
          canonical: "Хаб умного дома",
          type: "device",
          aliases: ["zigbee шлюз"],
          fact_types: ["controlled_device"]
        }
      ],
      software: [],
      lead_scoring: sampleLeadScoringSettings(),
      source: {
        type: "postgres",
        path: "nlp_config_revisions.config",
        editable: true,
        revision: 1
      }
    },
    notifications: sampleNotificationSettings(),
    telegram_ingestion: sampleTelegramIngestionSettings(),
    system: []
  };
}

function sampleNotificationSettings() {
  return {
    bots: [],
    chats: [],
    routes: [],
    updated_at: null
  };
}

function sampleTelegramIngestionSettings() {
  return {
    accounts: [],
    chats: []
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

function sampleReviewEvalReport() {
  return {
    reviewed: 2,
    evaluated: 2,
    skipped_uncertain: 0,
    skipped_missing_prediction: 0,
    true_positive: 0,
    false_positive: 1,
    true_negative: 0,
    false_negative: 1,
    precision: 0,
    recall: 0,
    specificity: 0,
    accuracy: 0,
    f1: 0,
    by_verdict: { noise: 1, lead: 1 },
    false_positives: [
      {
        source_message_id: "fp-1",
        telegram_message_id: 479071,
        source_chat_title: "Dahua Support",
        verdict: "noise",
        predicted_is_lead: true,
        score: 105,
        temperature: "hot",
        review_lane: "domain_interest",
        text_preview: "Добро пожаловать в чат Dahua Support"
      }
    ],
    false_negatives: [
      {
        source_message_id: "fn-1",
        telegram_message_id: 479072,
        source_chat_title: "Designers",
        verdict: "lead",
        predicted_is_lead: false,
        score: 10,
        temperature: "cold",
        review_lane: "other_candidate",
        text_preview: "Нужен подрядчик на видеонаблюдение"
      }
    ]
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

function settingsLinkHrefs() {
  return screen
    .getAllByRole("link")
    .map((link) => link.getAttribute("href") ?? "")
    .filter((href) => href.includes("#/settings/"));
}

function sampleResult() {
  return {
    original_text: "Нужен zigbee шлюз",
    normalized_text: "Нужен zigbee шлюз",
    entities: [],
    facts: [
      {
        id: "fact-smart-home-hub",
        text: "zigbee шлюз",
        type: "controlled_device",
        label: "Устройство: Хаб умного дома",
        source: "alias_catalog",
        range: { start: 6, stop: 17 },
        explanation: "Найден alias «Хаб умного дома» в каталоге devices (smart_home_hub).",
        settings_refs: [
          {
            section: "aliases",
            catalog: "devices",
            key: "smart_home_hub",
            label: "Устройство: Хаб умного дома",
            kind: "alias"
          }
        ]
      }
    ],
    domain_signals: [
      {
        id: "signal-smart-home",
        text: "zigbee шлюз",
        type: "smart_home_automation",
        label: "Умный дом / автоматизация",
        source: "fact_dependency",
        range: { start: 6, stop: 17 },
        explanation: "Сигнал «Умный дом / автоматизация» зависит от найденного факта «Устройство: Хаб умного дома»: «zigbee шлюз».",
        settings_refs: [
          {
            section: "signals",
            key: "smart_home_automation",
            label: "Умный дом / автоматизация",
            kind: "rule"
          },
          {
            section: "aliases",
            catalog: "devices",
            key: "smart_home_hub",
            label: "Устройство: Хаб умного дома",
            kind: "alias"
          }
        ]
      }
    ],
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
          label: "Умный дом / автоматизация",
          weight: 35,
          matched_texts: ["zigbee шлюз"]
        },
        {
          source: "fact",
          key: "controlled_device",
          label: "Устройство: Хаб умного дома",
          weight: 60,
          matched_texts: ["zigbee шлюз"]
        }
      ],
      review_lane: {
        key: "direct_pur_lead",
        label: "Прямой лид ПУР",
        description: "Есть домен и активное намерение",
        matched_group_indexes: [0, 1]
      }
    }
  };
}

function sampleResultWithEmojiRange() {
  const text =
    "Коллеги 🙏🏻 Установить zigbee шлюз. Свет, розетки, входной замок, ТВ, кондиционер, электрокарниз.";
  const start = Array.from(text).indexOf("э");
  const stop = start + Array.from("электрокарниз").length;
  return {
    original_text: text,
    normalized_text: text,
    entities: [],
    facts: [
      {
        id: "fact-electric-curtain",
        text: "электрокарниз",
        type: "automation_component",
        label: "Компонент автоматизации",
        source: "yargy",
        range: { start, stop }
      }
    ],
    domain_signals: [],
    tokens: [],
    syntax: [],
    metrics: {
      character_count: Array.from(text).length,
      sentence_count: 2,
      token_count: 10,
      entity_count: 0,
      fact_count: 1,
      domain_signal_count: 0
    },
    pipeline_trace: [],
    lead_assessment: {
      is_lead: false,
      score: 12,
      temperature: "none",
      solution_areas: [],
      customer_segments: [],
      intent_signals: [],
      noise_signals: [],
      reasons: []
    }
  };
}
