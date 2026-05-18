# LLM Verifier

LLM verifier is a second verification layer for Telegram lead messages. It does not replace aliases, facts, signals, scoring, or review lanes. It receives a compact message analysis pack, current taxonomy labels, and returns strict JSON with a recommendation.

## Local Models

Recommended first local runtime: Ollama with GGUF models.

Current practical status: `lead-lfm`, `lead-nemotron`, and GigaChat Lightning
GGUF are diagnostic only, not approved as a production decision layer. On the
contractor-cooperation case, `lead-lfm` returned a contradictory answer after
about 151 seconds, `lead-nemotron` needed about 305 seconds and still missed
the possible partner lead, and GigaChat Lightning GGUF answered after about 188
seconds but returned schema-invalid `confidence: 35`. Loading GigaChat and Qwen
together also OOM-killed Ollama on the current 11 GiB RAM host. The current
working local candidate is `lead-qwen-ru`, an Ollama alias for
`qwen2.5:3b-instruct`: it is small enough for the current host disk and is a
better fit for Russian lead verification in this setup. A larger Qwen2.5 7B Q4
model is the next upgrade path when the host has enough free disk/RAM.

If LLM disagrees with the deterministic trace, first check facts, signals,
scoring, and golden coverage; do not treat the model answer as source of truth
until it passes a separate golden validation pass.

The production dev server currently uses Ollama on the host and Hugging Face GGUF references directly:

```bash
ollama pull hf.co/nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF:Q4_K_M
ollama pull hf.co/lmstudio-community/LFM2.5-1.2B-Instruct-GGUF:Q4_K_M
ollama pull qwen2.5:3b-instruct
ollama cp hf.co/nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF:Q4_K_M lead-nemotron
ollama cp hf.co/lmstudio-community/LFM2.5-1.2B-Instruct-GGUF:Q4_K_M lead-lfm
ollama cp qwen2.5:3b-instruct lead-qwen-ru
```

For Docker backend access, Ollama should listen on the Docker host gateway, not only on `127.0.0.1`:

```ini
# /etc/systemd/system/ollama.service.d/override.conf
[Service]
Environment="OLLAMA_HOST=172.17.0.1:11434"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
```

Then reload the service and allow only Docker private subnets to reach Ollama:

```bash
sudo systemctl daemon-reload
sudo systemctl restart ollama
sudo ufw allow in from 172.16.0.0/12 to any port 11434 proto tcp comment 'Ollama from Docker networks'
```

## Backend Configuration

When backend runs in Docker, it reaches host Ollama through:

```bash
PUR_LLM_VERIFICATION_ENDPOINT=http://host.docker.internal:11434/api/chat
PUR_LLM_VERIFICATION_MODEL=lead-qwen-ru
PUR_LLM_VERIFICATION_TIMEOUT_SECONDS=600
```

`docker-compose.yml` maps `host.docker.internal` to the host gateway for both `backend` and `llm-worker`.

The verifier uses a dedicated Celery worker:

```bash
docker compose up -d llm-worker
```

The regular worker keeps processing enrichment jobs. The `llm-worker` consumes only the `llm` queue and should be treated as the slow, optional final verification layer.

## API

Read runtime configuration shown in the web UI:

```bash
curl -b /tmp/pur-cookies.txt \
  https://secclaw.qlbc.ru:19443/api/v1/llm-verifications/config
```

Read or update editable LLM settings:

```bash
curl -b /tmp/pur-cookies.txt \
  https://secclaw.qlbc.ru:19443/api/v1/settings/llm
```

Run LLM verification for a source Telegram message:

```bash
curl -X POST \
  -b /tmp/pur-cookies.txt \
  https://secclaw.qlbc.ru:19443/api/v1/llm-verifications/messages/<source_message_id>
```

List saved verification runs:

```bash
curl -b /tmp/pur-cookies.txt \
  https://secclaw.qlbc.ru:19443/api/v1/llm-verifications/messages/<source_message_id>
```

List all saved verification runs for the top-level LLM monitor:

```bash
curl -b /tmp/pur-cookies.txt \
  'https://secclaw.qlbc.ru:19443/api/v1/llm-verifications?limit=50&offset=0'
```

`POST /llm-verifications/messages/<source_message_id>` now queues a run and returns a `queued` row. The `llm-worker` later claims the row, calls Ollama, and marks it `completed` or `failed`.

## Context Pack

The backend sends:

- only the checked message text in `message.text`;
- deterministic `verdict`, `score`, `temperature`, and compact arrays of Russian labels:
  `fact_labels`, `signal_labels`, `reason_labels`, `solution_area_labels`,
  `customer_segment_labels`, `intent_signal_labels`, and `noise_signal_labels`;
- `available_taxonomy` as short human-readable labels only:
  `signal_labels`, `fact_rule_labels`, and `dictionary_labels`;
  dictionaries are grouped by Russian catalog names, for example
  `Вендоры: Яндекс, Xiaomi; Устройства: Камера видеонаблюдения, Домофон`;
  the prompt must not include full alias lists such as `Xiaomi / Сяоми / Ксяоми`;
  concrete deterministic hits are represented only by Russian labels.

The backend does not send Telegram ids, source chat title, config revision ids,
golden examples, fact spans, internal fact/signal types, source fields, matched
texts, or review lane to the model. Those details stay in the saved run/database
for operator debugging, not for model analysis.

The model must return only JSON matching `llm_verification.v1`. `confidence`
is always `0.0..1.0`, not deterministic `score`. If a model returns an obvious
percentage such as `35`, backend normalizes it to `0.35` before validation.
Invalid JSON or schema mismatch is saved as a failed verification and does not
change deterministic lead status.

Golden examples are not part of the LLM request. Golden remains a regression
tool for operators and deterministic settings, not model context. The model must
return `matched_golden_ids: []`.

Evidence fields are allowed to reference only the checked message text. The
backend also filters `evidence` and `anti_evidence` after model parsing:
ungrounded strings without term overlap with the checked message are dropped
before saving the completed run. If the model says
`agrees_with_rule_engine=true`, backend clears contradictory
`missing_fact_types`, `suspicious_fact_types`, and `missing_signal_types` in the
cleaned `response`; the unmodified model output remains visible in
`raw_response`.

## Routing

LLM routing is configured in `Настройки -> LLM`.

Global settings:

- `enabled` turns automatic LLM routing on or off.
- `model` is the Ollama model name. The production default is `lead-qwen-ru`.
  `lead-nemotron` and `lead-lfm` are only diagnostic fallbacks.
- `endpoint` is the Ollama chat endpoint.
- `timeout_seconds` is the model call timeout.
- `system_prompt` is the strict instruction sent as the system message.

Prompt assembly is explicit:

- `system_prompt` is saved in settings and sent as the system message;
- the backend builds a per-message `context_pack` JSON from message text,
  compact deterministic labels, and short taxonomy labels;
- the final model input is `System prompt + User JSON context_pack`;
- saved runs expose both layers, plus cleaned `response` and raw `raw_response`.

Each route has:

- `source_chat_ids`;
- `score_min` / `score_max`;
- `temperatures`;
- `review_lanes`;
- include/exclude lists for signal types, fact types, reason keys, solution areas, and customer segments.

Use exclude filters for noise gates, for example `exclude_signal_types=operator_noise`. This sends only already-promising messages to LLM and keeps obvious operator noise out of the slow queue.

The UI has a shortcut `Добавить пример маршрута для дизайнерских чатов`. It creates route `designers_non_noise`, pulls `source_chat_ids` from source chats whose title or input reference looks like a design/interior chat, sets `score_min=20`, `temperatures=warm,hot`, `review_lanes=direct_pur_lead`, and excludes `operator_noise`.

## Web UI

Top-level `LLM` shows saved runs across messages: status, model, route, source message, and linked enrichment job.

Expanding a run shows the stored `System prompt`, `context_pack`, cleaned `response`, and raw `raw_response`.

`Настройки -> LLM` edits model, endpoint, prompt, timeout, and routing rules.

In the candidates table, use the explicit `LLM` button in the message row. It opens the message review page, where the `LLM-проверка` panel shows the linked source message, current runtime settings, execution mode, saved runs, `context_pack` sent to the model, cleaned `response`, raw `raw_response`, and stored errors.

Execution mode is `celery_queue:llm`. Manual runs from the review page and automatic matched runs both go through the same `llm` queue.

`Статус системы` exposes `llm-worker`: model, endpoint, enabled flag, execution mode, Redis `llm` queue depth, total runs, run counts by status, oldest queued/running timestamps, latest completed timestamp, and latest failed error.
