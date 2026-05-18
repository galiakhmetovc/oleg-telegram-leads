import ConstructionIcon from "@mui/icons-material/Construction";
import HelpOutlineIcon from "@mui/icons-material/HelpOutlineOutlined";
import InsightsIcon from "@mui/icons-material/Insights";
import RefreshIcon from "@mui/icons-material/Refresh";
import ScienceIcon from "@mui/icons-material/Science";
import SettingsIcon from "@mui/icons-material/Settings";
import StarIcon from "@mui/icons-material/Star";
import {
  Alert,
  Box,
  Button,
  Chip,
  LinearProgress,
  Paper,
  Stack,
  Typography
} from "@mui/material";
import { useCallback, useEffect, useMemo, useState } from "react";

import { MarkdownPreview, encodeDocumentPath, extractMarkdownHeadings, type MarkdownHeading } from "../runtime/RuntimePages";

const guideDocumentPath = "docs/how-to-work-in-system.md";

export type OperatorGuideRouteTarget =
  | "testing"
  | "analytics"
  | "golden"
  | "constructor"
  | "settings"
  | "help";

type OperatorGuidePageProps = {
  apiBaseUrl: string;
  onNavigate: (target: OperatorGuideRouteTarget) => void;
};

type ProjectDocumentContent = {
  path: string;
  title: string;
  size_bytes: number;
  updated_at: string;
  content: string;
};

export function OperatorGuidePage({ apiBaseUrl, onNavigate }: OperatorGuidePageProps) {
  const [document, setDocument] = useState<ProjectDocumentContent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadGuide = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/project-docs/${encodeDocumentPath(guideDocumentPath)}`);
      if (!response.ok) {
        throw new Error(`Backend вернул ${response.status}`);
      }
      const payload = (await response.json()) as ProjectDocumentContent;
      setDocument(payload);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось загрузить операторский guide");
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl]);

  useEffect(() => {
    void loadGuide();
  }, [loadGuide]);

  const guideContent = useMemo(() => stripLeadingMarkdownTitle(document?.content ?? ""), [document?.content]);
  const headings = useMemo(() => extractGuideHeadings(guideContent), [guideContent]);

  return (
    <Stack spacing={2}>
      <Paper variant="outlined" className="operator-guide-header">
        <Stack spacing={2}>
          <Stack direction={{ xs: "column", lg: "row" }} spacing={1.5} sx={{ justifyContent: "space-between", alignItems: { lg: "flex-start" } }}>
            <Box>
              <Typography variant="h5" component="h2" sx={{ fontWeight: 700 }}>
                Как работать в системе
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Канонический операторский алгоритм: как разбирать сообщения, когда
                обновлять словари, факты, сигналы и как валидировать изменения через
                Testing и Golden.
              </Typography>
            </Box>
            <Button variant="outlined" startIcon={<RefreshIcon />} onClick={() => void loadGuide()} disabled={loading}>
              Обновить guide
            </Button>
          </Stack>

          <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap" }}>
            <Chip size="small" label={guideDocumentPath} />
            {document ? <Chip size="small" label={`${document.size_bytes} bytes`} /> : null}
            {document ? <Chip size="small" label={formatDateTime(document.updated_at)} /> : null}
          </Stack>

          <Alert severity="info">
            Это основной playbook оператора. Вкладка `Справка` остается техническим
            reference по полям настроек, а не заменой рабочего алгоритма.
          </Alert>

          <Box className="operator-guide-actions">
            <Button variant="contained" startIcon={<ScienceIcon />} onClick={() => onNavigate("testing")}>
              Открыть Тестирование
            </Button>
            <Button variant="outlined" startIcon={<InsightsIcon />} onClick={() => onNavigate("analytics")}>
              Открыть Аналитику
            </Button>
            <Button variant="outlined" startIcon={<StarIcon />} onClick={() => onNavigate("golden")}>
              Открыть Golden
            </Button>
            <Button variant="outlined" startIcon={<ConstructionIcon />} onClick={() => onNavigate("constructor")}>
              Открыть Конструктор
            </Button>
            <Button variant="outlined" startIcon={<SettingsIcon />} onClick={() => onNavigate("settings")}>
              Открыть Настройки
            </Button>
            <Button variant="outlined" startIcon={<HelpOutlineIcon />} onClick={() => onNavigate("help")}>
              Открыть Справку
            </Button>
          </Box>
        </Stack>
      </Paper>

      {loading && <LinearProgress />}
      {error && <Alert severity="error">{error}</Alert>}

      <Box className="operator-guide-shell">
        <Paper variant="outlined" className="operator-guide-sidebar">
          <Stack spacing={1.5}>
            <Box>
              <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700, textTransform: "uppercase" }}>
                Содержание
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Работай по шагам: owner текста, facts, signals, Golden, потом scoring.
              </Typography>
            </Box>
            <Stack spacing={0.75}>
              {headings.map((heading) => (
                <Button
                  key={heading.id}
                  variant="text"
                  color="inherit"
                  className={`operator-guide-toc-button operator-guide-toc-level-${heading.level}`}
                  onClick={() => scrollToHeading(heading.id)}
                >
                  {heading.text}
                </Button>
              ))}
            </Stack>
            {!loading && headings.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                В документе пока нет секций.
              </Typography>
            ) : null}
          </Stack>
        </Paper>

        <Paper variant="outlined" className="operator-guide-reader">
          {document ? (
            <Stack spacing={2}>
              <Box>
                <Typography variant="h5" component="h3" sx={{ fontWeight: 700 }}>
                  {document.title}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Один источник истины для ежедневной настройки lead-логики.
                </Typography>
              </Box>
              <MarkdownPreview content={guideContent} headings={headings} />
            </Stack>
          ) : (
            <Typography variant="body2" color="text.secondary">
              Документ пока не загружен.
            </Typography>
          )}
        </Paper>
      </Box>
    </Stack>
  );
}

function extractGuideHeadings(content: string): MarkdownHeading[] {
  return extractMarkdownHeadings(content, "guide").filter((heading) => heading.level >= 2);
}

function stripLeadingMarkdownTitle(content: string): string {
  const lines = content.split("\n");
  let index = 0;
  while (index < lines.length && lines[index].trim() === "") {
    index += 1;
  }
  if (index < lines.length && lines[index].trim().startsWith("# ")) {
    index += 1;
    while (index < lines.length && lines[index].trim() === "") {
      index += 1;
    }
  }
  return lines.slice(index).join("\n");
}

function scrollToHeading(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short"
  });
}
