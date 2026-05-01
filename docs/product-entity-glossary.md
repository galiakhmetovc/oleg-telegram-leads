# PUR Leads Product Entity Glossary

This document fixes the product-level language for PUR Leads.

## Naming Decision

Do not use `resource` as a product term.

It is too broad and conflates three different things:

- a configured ability to use an external system;
- a data source to analyze;
- a destination for notifications.

Use these terms instead:

- **Connection** (`Подключение`) - configured access to an external system.
- **Data Source** (`Источник данных`) - content the system should analyze.
- **Delivery Channel** (`Канал доставки`) - destination for operational
  notifications.

The current UI may still contain `/resources` or "Ресурсы" while the product
language is being migrated. Product-facing language should move to
`Подключения`.

## High-Level Model

```text
User
-> External Systems
-> Connections
-> Input Data
-> Internal Systems
-> Interest Context
-> Results
```

More precisely:

```text
User configures Connections to External Systems.
User adds Data Sources for analysis.
Internal Systems process Data Sources through the Interest Context.
Results are shown to the User or delivered back to External Systems.
Trace and Audit explain the whole chain.
```

## Core Layers

### 1. User

The person working in the system: the built-in `admin`, Oleg, or future
operators.

User records are connected to:

- authentication sessions;
- roles;
- audit entries;
- trace subjects;
- uploads and manual decisions.

### 2. External System

Something outside PUR Leads that the product interacts with.

Examples:

- Telegram;
- Z.AI;
- OpenAI;
- GigaChat;
- S3 or another object storage;
- OCR service;
- email or webhook service;
- user's local file upload as an external input.

An external system answers: **where does an outside capability or outside data
live?**

### 3. Connection

Configured access to an external system.

Examples:

- Telegram userbot session;
- Telegram bot token;
- Z.AI provider account with API key;
- OpenAI provider account with API key;
- S3 credentials;
- OCR provider account.

A connection answers: **how can PUR Leads use an external system?**

Important examples:

```text
External System: Telegram
Connections:
- userbot account for reading chats/channels;
- bot token for notifications and bot operations.
```

```text
External System: Z.AI
Connections:
- provider account #1 with API key;
- provider account #2 with another API key.
```

### 4. Data Source

Content the system should analyze.

Examples:

- Telegram channel or chat;
- Telegram Desktop archive;
- PDF, ZIP, DOCX, XLSX, image;
- web page or Telegraph link;
- manual text;
- correspondence with a client or employee.

A data source answers: **what information should PUR Leads analyze?**

### 5. Delivery Channel

Where the system sends operational notifications.

Examples:

- Telegram group for lead alerts;
- Telegram topic/thread;
- email inbox;
- webhook endpoint.

A delivery channel answers: **where should urgent results be delivered?**

Telegram group rule:

- a Telegram group used for reading is a **Data Source**;
- a Telegram group used for notifications is a **Delivery Channel**.

### 6. Delivery Route

A rule connecting events to delivery channels.

Examples:

```text
lead_alerts -> Telegram bot X -> group Y
task_alerts -> Telegram bot X -> group Y
quality_alerts -> webhook Z
```

A delivery route answers: **which event goes where and through which
connection?**

### 7. Internal System

A subsystem inside PUR Leads.

Examples:

- ingest pipeline;
- parser;
- text normalizer;
- FTS/Chroma indexer;
- AI model registry;
- LLM router;
- prompt manager;
- scheduler;
- workers;
- retry/circuit breaker;
- trace/audit;
- interest context builder;
- lead detector;
- CRM memory.

An internal system answers: **how does PUR Leads process data and make
decisions?**

### 8. Task / Run

Work the system should execute, plus the actual execution instance.

Examples:

- ingest archive;
- read Telegram source;
- parse document;
- normalize text;
- build embeddings;
- classify leads;
- validate with LLM;
- send notification.

A task answers: **what should be done?**

A run answers: **what actually happened this time?**

### 9. Executor

The thing that performs a task.

Examples:

- worker process;
- Telegram userbot;
- Telegram bot;
- local parser;
- OCR engine;
- LLM execution option;
- model profile.

An executor answers: **who or what performed the work?**

### 10. Artifact

A saved file or generated processing result.

Examples:

- original uploaded ZIP;
- downloaded PDF;
- extracted `result.json`;
- `messages.jsonl`;
- `messages.parquet`;
- `attachments.parquet`;
- `texts.parquet`;
- EDA report;
- FTS or Chroma index;
- LLM request/response dump;
- screenshot, report, or export.

An artifact answers: **which saved result can be opened and verified?**

### 11. Fragment

The smallest preserved content unit the system can reference.

Examples:

- Telegram message;
- attachment;
- parsed document chunk;
- web page chunk;
- manual note.

A fragment answers: **which exact piece of content produced knowledge, a lead,
or feedback?**

### 12. Interest Context

The central domain object of the product.

Interest Context answers: **what does the user want to find, understand, and
develop?**

It is broader than a product catalog.

It contains:

- interest directions;
- products, services, topics, and problems;
- terms and synonyms;
- demand signals;
- exclusions;
- geography;
- price ranges;
- priorities;
- seasonality;
- criteria for "this is a lead";
- criteria for "this is not a lead";
- lead and non-lead examples;
- operator feedback;
- versions and snapshots.

Example:

```text
Interest Context: PUR / smart home and low-current systems

Inside:
- video surveillance;
- Dahua cameras;
- smart home;
- electrical automation;
- sensors;
- installation and support;
- exclusions: toilets, furniture, unrelated classifieds;
- example lead: "need a camera for a dacha";
- example non-lead: "selling a toilet".
```

Old terms map into this object:

- `Catalog` is part of the Interest Context.
- `CRM memory` surrounds and enriches the Interest Context.
- `Feedback` improves the Interest Context.
- `Lead Detector` applies the Interest Context to new data.

### 13. Knowledge

Normalized meaning extracted from fragments and accepted into the Interest
Context.

Examples:

- entity;
- term;
- category;
- product;
- service;
- topic;
- synonym;
- exclusion;
- demand signal;
- evidence link.

Knowledge answers: **what did the system learn?**

### 14. Lead

Application of the Interest Context to a fragment or group of fragments.

Lead-related records include:

- lead event;
- lead cluster;
- lead match;
- confidence;
- reason;
- status;
- evidence;
- feedback such as "why this is not a lead".

A lead answers: **where does the current data match the user's interest
context?**

### 15. CRM Memory

Memory about customers and follow-up work.

Examples:

- client;
- contact;
- object;
- interest;
- opportunity;
- support case;
- contact reason;
- touchpoint.

CRM memory answers: **who is involved, what do they have, and when should we
contact them again?**

### 16. Feedback

Operator correction that improves future decisions.

Examples:

- lead / not lead / maybe;
- reason why a candidate is not a lead;
- catalog correction;
- entity merge/split;
- new exclusion;
- new example;
- prompt/model evaluation feedback.

Feedback answers: **how should the system improve?**

### 17. Snapshot / Version

A frozen state used to reproduce decisions.

Examples:

- Interest Context snapshot;
- catalog version;
- prompt version;
- model profile version;
- classifier version;
- settings hash;
- data export run.

A snapshot answers: **what exact state was used when this decision was made?**

### 18. Trace / Audit

The explanation and accountability layer.

Trace records include:

- trace;
- span;
- span event;
- span link.

Audit records include:

- user action;
- operational event;
- changed entity;
- old/new values with secrets redacted.

Trace and audit answer: **who did what, where did a result come from, and why
did the system decide that?**

## AI Model

AI is part of **Internal Systems** and **Executors**, not a separate product
world.

### AI Provider

Metadata about an AI vendor.

Examples:

- Z.AI;
- OpenAI;
- GigaChat;
- local Ollama.

### AI Provider Account

A **Connection** to an AI provider.

Stores:

- display name;
- base URL;
- secret ref for API key;
- plan type;
- enabled flag;
- priority;
- timeout defaults;
- policy notes.

### AI Model

A model exposed by a provider.

Stores:

- provider model name;
- model type: language, OCR, image, video;
- context window;
- max output;
- capabilities: structured output, thinking, tools, streaming, image/document
  input;
- status;
- verification source/date.

### AI Model Limit

Concurrency/rate limits for a model under a specific provider/account/plan.

Example:

```text
Z.AI account #1 / GLM-4-Plus / raw concurrency=20 / utilization=0.8 / effective=16
```

### AI Model Profile

How exactly to use a model for a task.

One model can have many profiles:

```text
GLM-4-Plus / catalog-json-strict
GLM-4-Plus / fast-summary
GLM-5.1 / deep-validation
GLM-OCR / scanned-pdf
```

Profile fields:

- max input tokens;
- max output tokens;
- temperature;
- thinking mode;
- structured output requirement;
- response schema;
- provider options;
- timeout policy;
- retry/circuit breaker policy.

### AI Task Type / Agent

The logical job to perform.

Examples:

- catalog extractor;
- lead detector;
- OCR extractor;
- entity normalizer;
- weak result validator.

### AI Execution Option

The concrete route for a task:

```text
catalog_extractor
-> Z.AI account #1
-> GLM-4-Plus
-> profile: catalog-json-strict
-> role: primary
-> priority: 1
```

One task type can have many execution options:

- primary;
- fallback;
- shadow;
- idle validation;
- cheap first;
- strong review.

### AI Run / Output

The actual call and result.

Stores:

- task type;
- provider account;
- model;
- model profile;
- prompt version;
- input hash;
- raw request JSON;
- raw response JSON;
- parsed output JSON;
- status;
- tokens/cost/latency;
- trace ID.

## Examples

### Example 1: User Uploads A Telegram Archive

```text
User: admin
External System: user's local filesystem / uploaded file
Connection: built-in file upload capability
Data Source: ChatExport_2026-04-30.zip
Task/Run: import Telegram Desktop archive
Artifacts:
- original ZIP;
- extracted result.json;
- messages.jsonl;
- messages.parquet;
- attachments.parquet;
- EDA report;
- texts.parquet;
Fragments:
- individual Telegram messages;
- attachment records;
- document chunks.
Interest Context:
- may be updated if the archive is used for knowledge extraction;
- may be used to classify messages as leads.
Results:
- knowledge candidates;
- lead candidates;
- trace/audit.
```

Important distinction:

```text
The uploaded archive is a Data Source.
The saved ZIP and generated files are Artifacts.
The upload mechanism is a built-in Connection/capability.
```

### Example 2: User Adds A Userbot And A Channel Link

```text
User: admin
External System: Telegram
Connection: Telegram userbot account
Data Source: https://t.me/purmaster
Source settings:
- from beginning / from date / recent days / from message / checkpoint;
- media download policy;
- max media size;
- purpose: catalog ingestion, lead monitoring, or both.
Task/Run:
- export telegram raw;
- parse documents;
- normalize text;
- build search/vector indexes;
- extract knowledge;
- classify leads.
Artifacts:
- raw export JSONL/Parquet;
- downloaded documents;
- attachment metadata;
- reports;
- search/vector indexes.
Fragments:
- Telegram messages;
- document chunks.
Results:
- Interest Context updates;
- lead candidates;
- trace/audit.
```

Important distinction:

```text
The userbot is a Connection.
The Telegram channel/chat is a Data Source.
```

### Example 3: Telegram Bot And Notification Group

```text
External System: Telegram
Connection: Telegram bot token
Delivery Channel: "Leads Finder - Управление" Telegram group
Delivery Route:
- lead_alerts -> bot X -> group Y;
- task_alerts -> bot X -> group Y.
Result:
- notification event;
- Telegram message ID;
- trace link to the lead/task that produced it.
```

Important distinction:

```text
Telegram bot = Connection for sending/bot operations.
Telegram notification group = Delivery Channel.
Telegram group used for reading = Data Source.
```

### Example 4: Z.AI Provider, Models, And Profiles

```text
External System: Z.AI
Connection: Z.AI account #1 with API key
Internal System: AI registry + LLM router
Executor:
- provider account: Z.AI account #1;
- model: GLM-4-Plus;
- profile: catalog-json-strict.
Task/Run:
- catalog extraction;
- lead validation;
- idle strong-model review.
Artifacts:
- raw request JSON;
- raw response JSON;
- parsed output JSON.
Results:
- knowledge candidate;
- validation decision;
- metrics;
- trace/audit.
```

Important distinction:

```text
Provider account = Connection.
Model/profile = Executor configuration.
AI run/output = processing result and evidence.
```

## Short Rules

```text
External Systems = outside places/services.
Connections = our configured access to outside systems.
Data Sources = what we analyze.
Delivery Channels = where we send urgent results.
Internal Systems = how PUR Leads processes data.
Interest Context = what the user wants to find and why.
Artifacts = saved files and generated processing results.
Fragments = exact pieces of content.
Results = knowledge, leads, CRM memory, notifications, reports.
Trace/Audit = proof of how everything happened.
```
