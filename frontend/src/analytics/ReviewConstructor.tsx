import SaveIcon from "@mui/icons-material/Save";
import {
  Alert,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField
} from "@mui/material";
import type { AliasCatalogName } from "./types";

type AliasType = "vendor" | "protocol" | "device" | "software" | "model";

export type ReviewNlpRule = {
  type: string;
  label: string;
};

export type ReviewNlpAlias = {
  key: string;
  canonical: string;
  type: AliasType;
  fact_types: string[];
};

export type ReviewNlpSettings = {
  signals: ReviewNlpRule[];
  facts: ReviewNlpRule[];
  vendors: ReviewNlpAlias[];
  protocols: ReviewNlpAlias[];
  devices: ReviewNlpAlias[];
  software: ReviewNlpAlias[];
};

type ConstructorPhraseKind = "exact" | "semantic";
export type ConstructorKind = "alias" | "fact" | "signal";

export type ConstructorDialogState =
  | {
      kind: "alias";
      text: string;
      catalog: AliasCatalogName;
      key: string;
      canonical: string;
      alias_type: AliasType;
      fact_types: string;
      confidence: string;
    }
  | {
      kind: "fact" | "signal";
      text: string;
      target_type: string;
      target_label: string;
      group: string;
      phrase_kind: ConstructorPhraseKind;
      color: string;
      confidence: string;
    };

type ConstructorNoiseResponse = {
  text: string;
  signal_type: string;
  signal_label: string;
  phrase: string[];
  created_phrase: boolean;
  nlp: unknown;
};

type ConstructorSettingsRef = {
  section: string;
  key: string;
  label: string;
  catalog?: AliasCatalogName | null;
};

type ConstructorAliasResponse = {
  text: string;
  catalog: AliasCatalogName;
  key: string;
  canonical: string;
  settings_ref: ConstructorSettingsRef;
  nlp: unknown;
};

type ConstructorRuleResponse = {
  text: string;
  collection: "signals" | "facts";
  rule_type: string;
  rule_label: string;
  settings_ref: ConstructorSettingsRef;
  nlp: unknown;
};

export type ConstructorSaveResult = {
  draft: string;
  message: string;
  nlp: unknown;
};

const aliasCatalogChoices: Array<{ value: AliasCatalogName; label: string }> = [
  { value: "vendors", label: "Вендоры" },
  { value: "protocols", label: "Протоколы" },
  { value: "devices", label: "Устройства" },
  { value: "software", label: "ПО" }
];

const constructorAliasTypeChoices: AliasType[] = ["vendor", "protocol", "device", "software", "model"];

export function createConstructorDialog(kind: ConstructorKind, text: string): ConstructorDialogState {
  if (kind === "alias") {
    const catalog: AliasCatalogName = "vendors";
    const aliasType = aliasTypeForCatalog(catalog);
    return {
      kind,
      text,
      catalog,
      key: constructorKeyFromText(text),
      canonical: text,
      alias_type: aliasType,
      fact_types: aliasType,
      confidence: "0.7"
    };
  }

  return {
    kind,
    text,
    target_type: constructorKeyFromText(text),
    target_label: text,
    group: kind === "signal" ? "Операторские сигналы" : "Операторские факты",
    phrase_kind: "exact",
    color: "#0b57d0",
    confidence: "0.5"
  };
}

export async function saveConstructorDialogRequest({
  apiBaseUrl,
  messageId,
  dialog
}: {
  apiBaseUrl: string;
  messageId: string;
  dialog: ConstructorDialogState;
}): Promise<ConstructorSaveResult> {
  if (dialog.kind === "alias") {
    const response = await fetch(`${apiBaseUrl}/api/v1/settings/nlp/constructor/alias`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: dialog.text,
        source_message_id: messageId,
        catalog: dialog.catalog,
        key: dialog.key,
        canonical: dialog.canonical,
        alias_type: dialog.alias_type,
        fact_types: stringListFromMultiline(dialog.fact_types),
        confidence: numberOrNull(dialog.confidence)
      })
    });
    if (!response.ok) {
      throw new Error(`Backend вернул ${response.status}`);
    }
    const payload = (await response.json()) as ConstructorAliasResponse;
    return {
      nlp: payload.nlp,
      draft: `${payload.catalog}:${payload.key} <- ${payload.text}`,
      message: `Добавлено в словарь «${payload.canonical}»: ${payload.text}`
    };
  }

  const endpoint = dialog.kind === "signal" ? "signal" : "fact";
  const response = await fetch(`${apiBaseUrl}/api/v1/settings/nlp/constructor/${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text: dialog.text,
      source_message_id: messageId,
      target_type: dialog.target_type,
      target_label: dialog.target_label,
      group: dialog.group,
      phrase_kind: dialog.phrase_kind,
      ...(dialog.kind === "signal" ? { color: dialog.color } : {}),
      confidence: numberOrNull(dialog.confidence)
    })
  });
  if (!response.ok) {
    throw new Error(`Backend вернул ${response.status}`);
  }
  const payload = (await response.json()) as ConstructorRuleResponse;
  return {
    nlp: payload.nlp,
    draft: `${payload.collection}:${payload.rule_type} <- ${payload.text}`,
    message: `Добавлено в ${dialog.kind === "signal" ? "доменный сигнал" : "факт"} «${payload.rule_label}»: ${payload.text}`
  };
}

export async function saveNoiseConstructorRequest({
  apiBaseUrl,
  messageId,
  text
}: {
  apiBaseUrl: string;
  messageId: string;
  text: string;
}): Promise<ConstructorSaveResult> {
  const response = await fetch(`${apiBaseUrl}/api/v1/settings/nlp/constructor/noise`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text,
      source_message_id: messageId
    })
  });
  if (!response.ok) {
    throw new Error(`Backend вернул ${response.status}`);
  }
  const payload = (await response.json()) as ConstructorNoiseResponse;
  const phraseText = payload.phrase.join(" ");
  return {
    nlp: payload.nlp,
    draft: `${payload.signal_type}: ${phraseText}`,
    message: payload.created_phrase
      ? `Добавлено в шумовой сигнал «${payload.signal_label}»: ${phraseText}`
      : `Шумовой сигнал «${payload.signal_label}» уже содержит: ${phraseText}`
  };
}

export function ConstructorDialog({
  dialog,
  nlpSettings,
  saving,
  onChange,
  onClose,
  onSave
}: {
  dialog: ConstructorDialogState | null;
  nlpSettings?: ReviewNlpSettings | null;
  saving: boolean;
  onChange: (dialog: ConstructorDialogState) => void;
  onClose: () => void;
  onSave: () => void;
}) {
  if (!dialog) {
    return null;
  }

  const title =
    dialog.kind === "alias"
      ? "Добавить в словарь"
      : dialog.kind === "fact"
        ? "Добавить в факт"
        : "Добавить в доменный сигнал";
  const saveLabel =
    dialog.kind === "alias"
      ? "Сохранить в словарь"
      : dialog.kind === "fact"
        ? "Сохранить факт"
        : "Сохранить сигнал";

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm" aria-labelledby="constructor-dialog-title">
      <DialogTitle id="constructor-dialog-title">{title}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <Alert severity="info">
            Выделено: <strong>{dialog.text}</strong>
          </Alert>
          {dialog.kind === "alias" ? (
            <AliasConstructorFields dialog={dialog} nlpSettings={nlpSettings} onChange={onChange} />
          ) : (
            <RuleConstructorFields dialog={dialog} nlpSettings={nlpSettings} onChange={onChange} />
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={saving}>
          Отмена
        </Button>
        <Button
          variant="contained"
          onClick={onSave}
          disabled={saving}
          startIcon={saving ? <CircularProgress size={18} color="inherit" /> : <SaveIcon />}
        >
          {saveLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function AliasConstructorFields({
  dialog,
  nlpSettings,
  onChange
}: {
  dialog: Extract<ConstructorDialogState, { kind: "alias" }>;
  nlpSettings?: ReviewNlpSettings | null;
  onChange: (dialog: ConstructorDialogState) => void;
}) {
  const aliases = nlpSettings?.[dialog.catalog] ?? [];
  return (
    <>
      <TextField
        label="Каталог"
        select
        value={dialog.catalog}
        onChange={(event) => {
          const catalog = aliasCatalogNameFromText(event.target.value);
          const aliasType = aliasTypeForCatalog(catalog);
          onChange({
            ...dialog,
            catalog,
            alias_type: aliasType,
            fact_types: aliasType
          });
        }}
        slotProps={{ select: { native: true } }}
        fullWidth
      >
        {aliasCatalogChoices.map((choice) => (
          <option key={choice.value} value={choice.value}>
            {choice.label}
          </option>
        ))}
      </TextField>
      <TextField
        label="Существующая запись"
        select
        value=""
        onChange={(event) => {
          const selected = aliases.find((item) => item.key === event.target.value);
          if (!selected) {
            return;
          }
          onChange({
            ...dialog,
            key: selected.key,
            canonical: selected.canonical,
            alias_type: selected.type,
            fact_types: selected.fact_types.join("\n")
          });
        }}
        slotProps={{ select: { native: true } }}
        fullWidth
      >
        <option value="">Новая или ручной ввод</option>
        {aliases.map((alias) => (
          <option key={alias.key} value={alias.key}>
            {alias.key} — {alias.canonical}
          </option>
        ))}
      </TextField>
      <TextField label="key" value={dialog.key} onChange={(event) => onChange({ ...dialog, key: event.target.value })} fullWidth />
      <TextField
        label="canonical"
        value={dialog.canonical}
        onChange={(event) => onChange({ ...dialog, canonical: event.target.value })}
        fullWidth
      />
      <TextField
        label="alias_type"
        select
        value={dialog.alias_type}
        onChange={(event) => onChange({ ...dialog, alias_type: aliasTypeFromText(event.target.value) })}
        slotProps={{ select: { native: true } }}
        fullWidth
      >
        {constructorAliasTypeChoices.map((value) => (
          <option key={value} value={value}>
            {value}
          </option>
        ))}
      </TextField>
      <TextField
        label="fact_types"
        value={dialog.fact_types}
        onChange={(event) => onChange({ ...dialog, fact_types: event.target.value })}
        helperText="По одному fact_type на строку."
        multiline
        minRows={2}
        fullWidth
      />
      <TextField
        label="confidence"
        type="number"
        value={dialog.confidence}
        onChange={(event) => onChange({ ...dialog, confidence: event.target.value })}
        slotProps={{ htmlInput: { min: 0, max: 1, step: 0.01 } }}
        fullWidth
      />
    </>
  );
}

function RuleConstructorFields({
  dialog,
  nlpSettings,
  onChange
}: {
  dialog: Extract<ConstructorDialogState, { kind: "fact" | "signal" }>;
  nlpSettings?: ReviewNlpSettings | null;
  onChange: (dialog: ConstructorDialogState) => void;
}) {
  const rules = dialog.kind === "signal" ? (nlpSettings?.signals ?? []) : (nlpSettings?.facts ?? []);
  return (
    <>
      <TextField
        label="Существующее правило"
        select
        value=""
        onChange={(event) => {
          const selected = rules.find((item) => item.type === event.target.value);
          if (!selected) {
            return;
          }
          onChange({
            ...dialog,
            target_type: selected.type,
            target_label: selected.label
          });
        }}
        slotProps={{ select: { native: true } }}
        fullWidth
      >
        <option value="">Новое или ручной ввод</option>
        {rules.map((rule) => (
          <option key={rule.type} value={rule.type}>
            {rule.type} — {rule.label}
          </option>
        ))}
      </TextField>
      <TextField
        label="type"
        value={dialog.target_type}
        onChange={(event) => onChange({ ...dialog, target_type: event.target.value })}
        fullWidth
      />
      <TextField
        label="label"
        value={dialog.target_label}
        onChange={(event) => onChange({ ...dialog, target_label: event.target.value })}
        fullWidth
      />
      <TextField
        label="Папка"
        value={dialog.group}
        onChange={(event) => onChange({ ...dialog, group: event.target.value })}
        fullWidth
      />
      <TextField
        label="Тип совпадения"
        select
        value={dialog.phrase_kind}
        onChange={(event) => onChange({ ...dialog, phrase_kind: phraseKindFromText(event.target.value) })}
        slotProps={{ select: { native: true } }}
        fullWidth
      >
        <option value="exact">Точная фраза</option>
        <option value="semantic">Лемматическая фраза</option>
      </TextField>
      {dialog.kind === "signal" && (
        <TextField
          label="color"
          type="color"
          value={dialog.color}
          onChange={(event) => onChange({ ...dialog, color: event.target.value })}
          fullWidth
        />
      )}
      <TextField
        label="confidence"
        type="number"
        value={dialog.confidence}
        onChange={(event) => onChange({ ...dialog, confidence: event.target.value })}
        slotProps={{ htmlInput: { min: 0, max: 1, step: 0.01 } }}
        fullWidth
      />
    </>
  );
}

function constructorKeyFromText(text: string) {
  const normalized = text
    .trim()
    .toLocaleLowerCase("ru-RU")
    .replace(/[^\p{L}\p{N}]+/gu, "_")
    .replace(/^_+|_+$/g, "");
  return normalized || "operator_rule";
}

function aliasCatalogNameFromText(value: string): AliasCatalogName {
  return aliasCatalogChoices.some((choice) => choice.value === value) ? (value as AliasCatalogName) : "vendors";
}

function aliasTypeForCatalog(catalog: AliasCatalogName): Exclude<AliasType, "model"> {
  if (catalog === "protocols") {
    return "protocol";
  }
  if (catalog === "devices") {
    return "device";
  }
  if (catalog === "software") {
    return "software";
  }
  return "vendor";
}

function aliasTypeFromText(value: string): AliasType {
  return constructorAliasTypeChoices.includes(value as AliasType) ? (value as AliasType) : "device";
}

function phraseKindFromText(value: string): ConstructorPhraseKind {
  return value === "semantic" ? "semantic" : "exact";
}

function stringListFromMultiline(value: string): string[] {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function numberOrNull(value: string): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}
