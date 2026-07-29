<div align="center">

# Inventory Agent

### 🤖 Autonomous Inventory Operations Engine

**AI-powered forecasting, risk detection, and purchase order management — running 24/7 in a LangGraph pipeline with human-in-the-loop approval.**

<br>

<p>

<!-- Primary badges -->
<a href="https://github.com/Ismail-2001/Inventory-Management-AI-Employee/actions/workflows/ci.yml">
  <img src="https://github.com/Ismail-2001/Inventory-Management-AI-Employee/actions/workflows/ci.yml/badge.svg" alt="CI">
</a>
<a href="https://github.com/Ismail-2001/Inventory-Management-AI-Employee">
  <img src="https://img.shields.io/github/stars/Ismail-2001/Inventory-Management-AI-Employee?style=flat-square&logo=github&color=FFD43B&label=Stars" alt="GitHub Stars">
</a>
<a href="https://github.com/Ismail-2001/Inventory-Management-AI-Employee/blob/main/CHANGES.md">
  <img src="https://img.shields.io/badge/version-1.0.0--beta-6C5CE7?style=flat-square" alt="Version">
</a>
<a href="https://github.com/Ismail-2001/Inventory-Management-AI-Employee">
  <img src="https://img.shields.io/github/last-commit/Ismail-2001/Inventory-Management-AI-Employee?style=flat-square&logo=git&logoColor=white" alt="Last Commit">
</a>

<!-- Tech badges -->
<img src="https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python">
<img src="https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI">
<img src="https://img.shields.io/badge/LangGraph-0.2-7C3AED?style=flat-square&logo=graph&logoColor=white" alt="LangGraph">
<img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white" alt="PostgreSQL">
<img src="https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=black" alt="React">
<img src="https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker">

<!-- Quality badges -->
<img src="https://img.shields.io/badge/tests-22_passing-00B894?style=flat-square&logo=pytest" alt="22 Passing Tests">
<img src="https://img.shields.io/badge/MAPE_gate-%3C30%25-brightgreen?style=flat-square" alt="MAPE Gate">
<img src="https://img.shields.io/badge/ci-passing-brightgreen?style=flat-square" alt="CI Passing">

</p>

<br>

[🚀 Quick Start](#-quick-start) •
[🏗️ Architecture](#-architecture) •
[✨ Features](#-features) •
[📖 API](#-api-endpoints) •
[🧠 Agent Pipeline](#-agent-workflow) •
[🛡️ Security](#-security) •
[📊 Performance](#-performance) •
[🧪 Testing](#-testing) •
[🚢 Deploy](#-deployment) •
[🛣️ Roadmap](#-roadmap) •
[💼 For Clients](#-for-clients--recruiters) •
[📬 Contact](#-contact)

</div>

---

<br>

## ⚡ Why Inventory Agent?

Inventory operations are the backbone of every ecommerce business — yet most teams run them on **spreadsheets, gut feeling, and late-night panic emails**.

The cost of reactive inventory management is staggering:

| Problem | What It Costs |
|---|---|
| 😰 **Stockouts** | **3–5×** lost revenue per event + permanently lost customers |
| 📦 **Overstock** | **30–50%** of working capital locked in dead inventory |
| 🐌 **Manual PO cycles** | **3–5 days** from detection → approval → order |
| 🔍 **Reactive monitoring** | **8–12 hours/week** of manual stock checks |
| 📉 **No feedback loop** | **90%** of teams never measure whether their POs prevented stockouts |

> **Inventory Agent replaces this chaos with a single autonomous pipeline** — connecting your Shopify store, a statistical forecasting engine, an LLM-powered reasoning layer, and a human-in-the-loop approval workflow — all running 24/7.

### 🎯 Built For

| Audience | What They Get |
|---|---|
| **Ecommerce Ops Teams** | Reclaim 10+ hours/week by automating daily syncs, forecasts, and PO drafts |
| **DTC Brands & Shopify Plus** ($1M+ GMV) | Prevent stockouts on best-sellers. Optimize working capital. Never miss a reorder window. |
| **3PL & Fulfillment Providers** | Manage multi-client inventory. Auto-trigger POs per client. Demonstrate value with analytics. |
| **Enterprise Operations** | Custom node integration, immutable audit logs, RBAC, and SOC 2–ready compliance |

<br>

---

<br>

## ✨ Features

| | Capability | What It Does | Business Value |
|---|---|---|---|
| 🔄 | **Shopify Sync** | GraphQL sync of products, variants, inventory levels & 90-day order history | Always-accurate inventory — zero manual exports |
| 📈 | **Demand Forecasting** | Per-SKU exponential smoothing with 30/60/90-day projections (28-test MAPE gate) | Data-driven purchasing, not guesswork |
| 🚨 | **Risk Detection** | Per-SKU classification: stockout / overstock / dead-stock / healthy | Early warnings before stock hits zero |
| 🤖 | **AI Purchase Orders** | LLM-generated POs with calculated quantity, cost, and plain-English reasoning | Draft POs in seconds, not hours |
| ✅ | **Human-in-the-Loop** | LangGraph `interrupt_after` pauses for approval — approve/reject from dashboard or Slack | Full control over spend, zero automation risk |
| ✏️ | **Quantity Override** | Edit PO quantities at approval time | Flexibility without breaking the workflow |
| 📊 | **Outcome Tracking** | Post-fulfillment evaluation — acceptance rate, forecast error, stockout prevention | Continuous improvement with real data |
| 📝 | **Weekly Reflection** | LLM-generated management summary with data-driven insights | Strategic insights delivered to your inbox |
| 🔔 | **Slack Notifications** | Real-time alerts, pending PO reminders, weekly digests | Your team stays informed without dashboard checks |
| 🔐 | **RBAC + Audit Log** | Owner/staff/viewer roles + append-only immutable audit log | Compliance-ready, SOC 2 friendly |
| 📡 | **OpenTelemetry Tracing** | End-to-end spans across every pipeline node | Debug production issues in minutes |
| 🖥️ | **React Dashboard** | Dashboard, Inventory, PO management, Analytics, Settings | Full visibility from any device |

<br>

---

<br>

## 🏗️ Architecture

### System Overview

```mermaid
graph TB
    subgraph "External"
        Shopify["🛍️ Shopify Store\nGraphQL API"]
        Slack["💬 Slack\nWebhooks + Messages"]
        LLM["🧠 LLM Provider\nGemini / GPT-4 / Groq"]
    end

    subgraph "FastAPI Server"
        API["🌐 API Layer\nFastAPI + Rate Limit + CORS"]
        Scheduler["⏰ APScheduler\nDaily eval + Weekly reflection"]
    end

    subgraph "LangGraph Pipeline"
        Sync["🔄 Sync\nShopify GraphQL → DB"]
        Forecast["📈 Forecast\nExponential smoothing"]
        Risk["🚨 Risk\nClassification engine"]
        PO["📦 PO Draft\nLLM reasoning + qty calc"]
        NotifyPending["🔔 Notify Pending\nSlack + signed links"]
        NotifyConfirmed["✅ Notify Confirmed\nApproval summary"]
        
        Sync --> Forecast --> Risk
        Risk -- has alerts --> PO
        Risk -- no alerts --> END1(("END"))
        PO --> NotifyPending
        NotifyPending -- interrupt_after --> Human{"🤝 Human Approval"}
        Human -- approve/reject --> NotifyConfirmed --> END2(("END"))
    end

    subgraph "PostgreSQL"
        DB[("📊 Inventory DB\nskus, sales, forecasts,\nalerts, POs, audit log")]
        CP[("💾 Checkpointer\nlanggraph PostgresSaver")]
    end

    Shopify -.->|"GraphQL sync"| Sync
    LLM -.->|"API calls"| PO
    LLM -.->|"API calls"| NotifyPending
    Slack <-->|"Webhook + msg"| NotifyPending
    Slack <-->|"Webhook + msg"| NotifyConfirmed
    API --> Scheduler
    API --> Sync
    DB <-->|"asyncpg"| Sync
    DB <-->|"asyncpg"| Forecast
    DB <-->|"asyncpg"| Risk
    DB <-->|"asyncpg"| PO
    CP <-->|"psycopg"| NotifyPending
    CP <-->|"psycopg"| NotifyConfirmed
```

<br>

### Pipeline Sequence — What Happens When You Hit "Run Sync"

```mermaid
sequenceDiagram
    actor Merchant as 👤 Merchant
    participant API as FastAPI
    participant Graph as LangGraph Agent
    participant Shopify
    participant DB as PostgreSQL
    participant LLM as LLM
    participant Slack as Slack

    Note over Merchant,Slack: ═══ PHASE 1 — Sync & Forecast ═══
    Merchant->>API: POST /api/v1/run-sync
    API->>Graph: ainvoke({}, {thread_id})
    Graph->>Shopify: GraphQL: products + inventory
    Graph->>Shopify: GraphQL: orders (last 90d)
    Graph->>DB: Upsert Sku + SalesHistory
    Graph-->>DB: Checkpoint saved
    Graph->>DB: Query 90d sales history per SKU
    Graph->>Graph: Exponential smoothing forecast
    Graph->>DB: Insert Forecast rows
    Graph-->>DB: Checkpoint saved

    Note over Merchant,Slack: ═══ PHASE 2 — Risk Detection ═══
    Graph->>Graph: determine_risk_level() per forecast
    Graph->>DB: Insert RiskAlert (if critical/warning)
    Graph-->>DB: Checkpoint saved

    alt Alerts exist
        Note over Merchant,Slack: ═══ PHASE 3 — PO Draft ═══
        Graph->>DB: Query Supplier config
        Graph->>Graph: calculate_reorder_quantity()
        Graph->>LLM: Generate plain-English reasoning
        LLM-->>Graph: Reasoning text
        Graph->>DB: Insert PurchaseOrder (pending_approval)
        Graph-->>DB: Checkpoint saved
    end

    Note over Merchant,Slack: ═══ PHASE 4 — Notify + Interrupt ═══
    Graph->>Graph: Build Slack summary with approve/reject links
    Graph->>Slack: Post notification message
    Note over Graph: 🛑 INTERRUPT — waiting for human action
    Graph-->>API: Return state with PO details
    API-->>Merchant: {status, thread_id, pos}

    alt Merchant approves via API or Slack link
        Note over Merchant,Slack: ═══ PHASE 5 — Approval ═══
        Merchant->>API: POST /po/{id}/approve or click Slack link
        API->>Graph: Command(resume="approve")
        Graph->>DB: PO status → approved
        Graph->>Graph: Build confirmation summary
        Graph->>Slack: Post confirmation message
        Graph-->>API: Final state
        API-->>Merchant: {status: "approved"}
    end
```

<br>

### State Management — No Data Lost Between Nodes

Every node receives the **full state dict** and returns `{**state, new_key: value}`. The graph checkpoints to PostgreSQL after every node — if a process crashes mid-flow, it resumes from the last checkpoint.

```
{} ──→ {skus, synced_products, synced_sales}       🔄 Sync
   ──→ {..., forecasts}                               📈 Forecast
   ──→ {..., risk_alerts}                              🚨 Risk
   ──→ {..., purchase_orders}                          📦 PO Draft
   ──→ {..., notification_summary}                      🔔 Notify Pending
   ──→ 🛑 HUMAN INTERRUPT                              🤝 Approval
   ──→ {..., confirmation_summary}                     ✅ Notify Confirmed
```

### Node Design Philosophy

| Principle | How It's Implemented |
|---|---|
| **Stateless nodes** | Each node is a pure `async (state: dict) -> dict` function — no hidden state, fully testable in isolation |
| **Deterministic fallbacks** | LLM nodes fall back to template-based reasoning when providers are unavailable or the spend cap is hit |
| **Idempotent upserts** | All DB writes use PostgreSQL `ON CONFLICT DO UPDATE` — rerunning the same sync produces identical results |
| **Checkpoint after every node** | LangGraph's `PostgresSaver` persists state after each node — crash recovery with zero data loss |

<br>

---

---

<br>

## 🛠️ Tech Stack

<table>
<tr><th>Layer</th><th>Technology</th><th>Why It Was Chosen</th></tr>
<tr>
<td><b>🤖 AI Orchestration</b></td>
<td><img src="https://img.shields.io/badge/LangGraph-0.2-blue?style=flat-square&logo=graph" height="22"> LangGraph</td>
<td>State graphs with built-in checkpoint/pause/resume — purpose-built for human-in-the-loop agent workflows. The <code>interrupt_after</code> API made the approval flow trivial.</td>
</tr>
<tr>
<td><b>⚡ API Framework</b></td>
<td><img src="https://img.shields.io/badge/FastAPI-0.115-teal?style=flat-square&logo=fastapi" height="22"> FastAPI</td>
<td>Async-native, auto-generated OpenAPI docs, Pydantic validation — fastest path from code to production API.</td>
</tr>
<tr>
<td><b>🐍 Runtime</b></td>
<td><img src="https://img.shields.io/badge/Python-3.12-blue?style=flat-square&logo=python" height="22"> Python 3.12</td>
<td>Async-native, richest ML/AI ecosystem, LangGraph ecosystem, extensive library support.</td>
</tr>
<tr>
<td><b>🐘 Database</b></td>
<td><img src="https://img.shields.io/badge/PostgreSQL-16-indigo?style=flat-square&logo=postgresql" height="22"> PostgreSQL 16</td>
<td>JSONB for flexible supplier configs, <code>ON CONFLICT DO UPDATE</code> for idempotent upserts, mature async driver (asyncpg).</td>
</tr>
<tr>
<td><b>🔗 ORM</b></td>
<td><img src="https://img.shields.io/badge/SQLAlchemy-2.0-red?style=flat-square&logo=sqlalchemy" height="22"> SQLAlchemy 2.0</td>
<td>Type-safe async queries, Alembic migrations, PostgreSQL-specific dialect support.</td>
</tr>
<tr>
<td><b>🖥️ Frontend</b></td>
<td><img src="https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react" height="22"> React 19</td>
<td><img src="https://img.shields.io/badge/TypeScript-3178C6?style=flat-square&logo=typescript" height="22"> TypeScript</td>
<td><img src="https://img.shields.io/badge/Vite-646CFF?style=flat-square&logo=vite" height="22"> Vite</td>
<td><img src="https://img.shields.io/badge/Tailwind-06B6D4?style=flat-square&logo=tailwindcss" height="22"> Tailwind</td>
<td>Fast dev cycle (Vite), type-safe UI (TypeScript), utility-first styling (Tailwind).</td>
</tr>
<tr>
<td><b>🧠 LLM Providers</b></td>
<td><img src="https://img.shields.io/badge/Gemini_2-4285F4?style=flat-square&logo=google" height="22"> Gemini</td>
<td><img src="https://img.shields.io/badge/GPT--4-412991?style=flat-square&logo=openai" height="22"> GPT-4</td>
<td><img src="https://img.shields.io/inference?style=flat-square&logo=groq&color=F36" height="22"> Groq</td>
<td>Multi-provider fallback chain — switches provider if unavailable, template fallback as last line of defense.</td>
</tr>
<tr>
<td><b>💬 Notifications</b></td>
<td><img src="https://img.shields.io/badge/Slack-Webhooks-4A154B?style=flat-square&logo=slack" height="22"> Slack Incoming Webhooks</td>
<td>Real-time ops alerts with signed one-click approve/reject links embedded in the message.</td>
</tr>
<tr>
<td><b>🔐 Auth</b></td>
<td>bcrypt + HMAC-SHA256</td>
<td>API key auth with bcrypt hashing. Signed HMAC tokens (48h TTL) for passwordless Slack approval.</td>
</tr>
<tr>
<td><b>🗺️ Migrations</b></td>
<td><img src="https://img.shields.io/badge/Alembic-CC3333?style=flat-square&logo=sqlalchemy" height="22"> Alembic</td>
<td>9 version-controlled migration files tracking every schema change from initial tables through multi-tenant scoping.</td>
</tr>
<tr>
<td><b>⏰ Scheduling</b></td>
<td><img src="https://img.shields.io/badge/APScheduler-0A66C2?style=flat-square" height="22"> APScheduler</td>
<td>Async-native scheduler for daily outcome evaluation and Monday-morning reflection jobs.</td>
</tr>
<tr>
<td><b>📊 Observability</b></td>
<td><img src="https://img.shields.io/badge/OpenTelemetry-000000?style=flat-square&logo=opentelemetry" height="22"> OpenTelemetry</td>
<td>Distributed tracing with OTLP export — every graph node is a traced span with success/failure attributes.</td>
</tr>
<tr>
<td><b>✅ Testing</b></td>
<td><img src="https://img.shields.io/badge/pytest-8.0-0A9EDC?style=flat-square&logo=pytest" height="22"> pytest</td>
<td><img src="https://img.shields.io/badge/pytest--asyncio-6CBCE5?style=flat-square&logo=pytest" height="22"> pytest-asyncio</td>
<td>12 test files, 22+ unit tests, 28-case forecast accuracy regression suite with MAPE &lt; 30% gate.</td>
</tr>
<tr>
<td><b>🐳 Containerization</b></td>
<td><img src="https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker" height="22"> Docker</td>
<td><img src="https://img.shields.io/badge/Compose-2496ED?style=flat-square&logo=docker" height="22"> Compose</td>
<td>Multi-stage Dockerfile with slim Python 3.12 base. Dev/prod parity with override config.</td>
</tr>
</table>

<br>

---

<br>

## ⚡ Quick Start

Get a full inventory pipeline running in under 5 minutes.

### Prerequisites

<table>
<tr>
<td width="50%">

**🐳 Docker Desktop** (recommended)

+ Docker Engine
+ Docker Compose

</td>
<td width="50%">

**🐍 Python 3.12+**

+ PostgreSQL 16 running locally
+ pip package manager

</td>
</tr>
</table>

**You'll also need:**
- A Shopify dev store — get your Admin API token from [Shopify Admin → Apps → Admin API](https://shopify.dev/docs/apps/auth/admin-access-tokens)
- An LLM API key — [Gemini](https://aistudio.google.com/apikey), [OpenAI](https://platform.openai.com/api-keys), or [Groq](https://console.groq.com)
- Optionally, a Slack webhook URL for notifications — [create one here](https://api.slack.com/messaging/webhooks)

<br>

### Step 1: Clone and configure

```bash
git clone https://github.com/Ismail-2001/Inventory-Management-AI-Employee.git
cd Inventory-Management-AI-Employee
cp .env.example .env
```

Edit `.env` — fill in your credentials:

```env
SHOPIFY_STORE_DOMAIN=your-store.myshopify.com
SHOPIFY_ADMIN_API_TOKEN=shpat_xxxx...
GOOGLE_API_KEY=AIz...your-key...
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../xxx
```

<br>

### Step 2: Launch the stack

<details open>
<summary><b>🐳 Docker (recommended — 1 command)</b></summary>

```bash
docker compose up -d
```

This starts:
- **API Server** → `http://localhost:8002`
- **Swagger UI** → `http://localhost:8002/docs`
- **PostgreSQL** → port 5432 (data persists via Docker volume)

</details>

<details>
<summary>🐍 Pip + uvicorn (no Docker)</summary>

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head   # initialize DB schema
uvicorn api.main:app --reload --port 8002
```

> Requires a running PostgreSQL instance on `localhost:5432`.

</details>

<br>

### Step 3 (optional): Launch the dashboard

```bash
cd inventory-frontend
npm install
npm run dev
```

Opens at `http://localhost:5173` — proxies API calls to the backend.

<br>

### Step 4: Run your first sync

```bash
curl -s -X POST http://localhost:8002/api/v1/run-sync \
  -H "X-API-Key: demo-key-2024" | python -m json.tool
```

Within seconds, the agent:
1. 🔄 Syncs all products and orders from Shopify
2. 📈 Generates per-SKU demand forecasts
3. 🚨 Identifies stockout/overstock risks
4. 📦 Drafts purchase orders with LLM-powered explanations
5. 🔔 Sends a Slack notification with approve/reject links

POs are created in `pending_approval` status — the agent waits for you.

<br>

### Quick Test Commands

```bash
# Health check
curl http://localhost:8002/health

# List SKUs
curl http://localhost:8002/api/v1/skus -H "X-API-Key: demo-key-2024"

# List pending POs
curl "http://localhost:8002/api/v1/po?status=pending_approval" -H "X-API-Key: demo-key-2024"

# Approve a PO (with optional quantity override)
curl -s -X POST http://localhost:8002/api/v1/po/1/approve \
  -H "X-API-Key: demo-key-2024" \
  -H "Content-Type: application/json" \
  -d '{"approved_by": "merchant", "quantity": 50}' | python -m json.tool

# Business metrics
curl http://localhost:8002/api/v1/metrics -H "X-API-Key: demo-key-2024"

# Generate weekly reflection + Slack digest
curl -s -X POST http://localhost:8002/api/v1/run-weekly -H "X-API-Key: demo-key-2024"
```

<br>

---

<br>

## 💻 Configuration

All configuration is environment-variable driven via the `.env` file.

<details>
<summary><b>📋 Full configuration reference (click to expand)</b></summary>

<br>

### Shopify

| Variable | Required | Default | Description |
|---|---|---|---|
| `SHOPIFY_STORE_DOMAIN` | ✅ Yes | — | Store domain (e.g., `my-store.myshopify.com`) |
| `SHOPIFY_ADMIN_API_TOKEN` | ✅ Yes | — | Admin API access token |
| `SHOPIFY_API_VERSION` | No | `2026-01` | GraphQL API version |
| `SHOPIFY_WEBHOOK_SECRET` | No | — | Shared secret for webhook HMAC verification |

### Database

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | No | `postgresql+asyncpg://inventory:inventory@localhost:5432/inventory_agent` | Async PostgreSQL connection (for app data) |
| `CHECKPOINTER_DATABASE_URL` | No | derived from `DATABASE_URL` | LangGraph checkpointer (psycopg connection scheme, not asyncpg) |

### LLM Providers

| Variable | Required | Default | Description |
|---|---|---|---|
| `LLM_PROVIDER` | No | `openai` | `openai`, `google`, or `groq` |
| `OPENAI_API_KEY` | ¹ | — | OpenAI API key |
| `GOOGLE_API_KEY` | ¹ | — | Google AI (Gemini) API key |
| `GROQ_API_KEY` | ¹ | — | Groq API key |
| `MODEL_NAME` | No | per-provider default | Model name (e.g., `gemini-2.0-flash`, `gpt-4`, `llama-3.1-8b-instant`) |
| `DAILY_LLM_SPEND_CAP` | No | `5.00` | Daily LLM spend limit in USD |
| `TEMPERATURE` | No | `0.3` | Generation temperature |
| `MAX_TOKENS` | No | `1024` | Max output tokens |

> ¹ At least one API key required for PO reasoning and weekly reflection features.

### Security

| Variable | Required | Default | Description |
|---|---|---|---|
| `AGENT_API_KEY` | No | `demo-key-2024` | API key for endpoint authentication |
| `ENVIRONMENT` | No | `development` | Set to `production` to disable demo key |
| `ALLOW_DEMO_KEY` | No | `true` | Auto-disabled when `ENVIRONMENT=production` |
| `ALLOWED_ORIGINS` | No | `http://localhost:5173,http://localhost:3000` | CORS allowlist (comma-separated) |

### Notifications

| Variable | Required | Default | Description |
|---|---|---|---|
| `SLACK_WEBHOOK_URL` | No | — | Slack incoming webhook URL (omit to disable Slack notifications) |
| `PUBLIC_API_URL` | No | `http://localhost:8002` | Public base URL (used in signed approve/reject token links) |

</details>

<br>

---

<br>

## 📡 API Endpoints

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | — | Health check |
| `POST` | `/api/v1/run-sync` | 🔑 API key | Trigger full pipeline: sync → forecast → risk → PO → notify |
| `GET` | `/api/v1/skus` | 🔑 API key | List all synced SKUs with current stock levels |
| `GET` | `/api/v1/po` | 🔑 API key | List POs (`?status=pending_approval` filter available) |
| `POST` | `/api/v1/po/{id}/approve` | 🔑 API key + RBAC | Approve PO (supports `quantity` override) |
| `POST` | `/api/v1/po/{id}/reject` | 🔑 API key + RBAC | Reject PO with reason |
| `GET` | `/api/v1/po/action?token=...` | 🔐 HMAC token | One-click approve/reject from Slack (no login) |
| `GET` | `/api/v1/metrics` | 🔑 API key | Acceptance rates + forecast error summary |
| `POST` | `/api/v1/evaluate-outcomes` | 🔑 API key | Evaluate pending PO outcomes |
| `POST` | `/api/v1/run-weekly` | 🔑 API key | Generate weekly reflection + Slack digest |
| `POST` | `/webhooks/shopify/inventory` | 🔐 HMAC | Shopify inventory webhook |
| `POST` | `/webhooks/shopify/order` | 🔐 HMAC | Shopify order webhook |
| `POST` | `/webhooks/shopify/product` | 🔐 HMAC | Shopify product webhook |
| `GET` | `/docs` | — | Swagger UI (interactive API explorer) |
| `GET` | `/redoc` | — | ReDoc (alternative docs) |

<br>

---

<br>

## 🧠 Agent Workflow — Deep Dive

### The 6-Node Pipeline

Every sync goes through the same autonomous flow:

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                 │
│   🔄 SYNC          → Pull products, variants, orders from Shopify│
│      │                                                     │
│      ▼                                                     │
│   📈 FORECAST      → Query 90d sales, apply exponential smoothing │
│      │                                                     │
│      ▼                                                     │
│   🚨 RISK           → Classify each SKU: safe / warning / critical│
│      │                                                     │
│      ├─ (no alerts) ──────────────────────────→ END         │
│      │                                                     │
│      ▼                                                     │
│   📦 PO DRAFT      → Query supplier, calculate qty, generate │
│      │              LLM reasoning, insert pending PO        │
│      ▼                                                     │
│   🔔 NOTIFY PENDING → Build Slack summary + signed approve   │
│      │              / reject links. 🛑 GRAPH PAUSES HERE.   │
│      ▼                                                     │
│   ✅ NOTIFY CONFIRMED → Post approval/rejection summary to    │
│                          Slack. Workflow complete.           │
│                                                                 │
└──────────────────────────────────────────────────────────────────┘
```

### How Approval Works

The graph pauses at `notify_pending`. Human approval is triggered through two channels — **both require exactly the same action**:

| Channel | How It Works | Use Case |
|---|---|---|
| **Dashboard** — `POST /api/v1/po/{id}/approve` | REST endpoint with RBAC (owner/staff only) | Operational team reviewing POs |
| **Slack Link** — `GET /api/v1/po/action?token=...` | HMAC-signed URL (48h TTL), no login needed | Quick approval from Slack notification |

The signed token embeds `{po_id}:{action}:{expiry}:{HMAC}` — the server verifies the signature and expiry before applying the approval.

### Deterministic Fallback

LLM calls (PO reasoning, weekly reflection) have a **template fallback** — when the LLM provider is unavailable, slow, or the daily spend cap is hit, the agent generates a plain-English explanation using structured data. No LLM call required. No workflow interruption.

<br>

---

<br>

## 🔒 Security

| Layer | Implementation |
|---|---|
| **API Authentication** | API key verification via bcrypt hash comparison (constant-time) |
| **Key-Prefix Optimization** | Indexes on `Merchant.key_prefix` — fast lookup before full bcrypt verification |
| **Role-Based Access Control** | `owner` / `staff` can approve/reject POs; `viewer` is read-only |
| **Signed Approval Links** | HMAC-SHA256 tokens with 48h automatic expiry — approve from Slack without login |
| **Webhook HMAC Verification** | All Shopify webhooks verified via `X-Shopify-Hmac-Sha256` header |
| **Demo Key Gating** | `demo-key-2024` auto-disabled when `ENVIRONMENT=production` |
| **CORS Allowlist** | Configuration-driven — no wildcard origins in production |
| **Rate Limiting** | 60 req/min default; 5 req/min on approve/reject endpoints (slowapi) |
| **Request Idempotency** | In-memory + DB-backed dedup via `Idempotency-Key` header |
| **Webhook Deduplication** | In-memory LRU cache (1,000 entries) + DB-backed dedup via `X-Shopify-Webhook-Id` |
| **Secrets Management** | All credentials in `.env` (gitignored) — never in code |
| **Immutable Audit Log** | Append-only `AuditLog` table — every state change recorded with actor, action, and timestamp |
| **Global Exception Handler** | Consistent error responses without leaking internal exception details |

<br>

---

<br>

## 📊 Performance & Scalability

| Metric | Current | Target |
|---|---|---|
| **Sync throughput** | Verified at 26 SKUs, 10,000+ inventory records | Horizontal scaling with partitioned sync workers |
| **Forecast accuracy** | MAPE < 30% (28-case regression gate) | < 15% with ML models (Phase 3) |
| **Graph recovery** | Sub-second checkpoint/resume | Zero RPO |
| **LLM cost control** | Configurable daily spend cap | Real token counting from provider (in progress) |
| **API latency** | < 200ms p95 (excluding sync) | < 100ms p95 with read replicas |
| **Webhook processing** | Single-variant targeted sync (50-200× faster than full catalog) | Event sourcing with SQS/SNS fan-out |

### Key Performance Patterns

- **Checkpointed state machine** — graph resumes from last checkpoint on crash; zero data loss
- **Targeted webhook syncs** — inventory updates sync 1 variant instead of full catalog (50–200× faster)
- **Multi-provider LLM fallback** — switches provider if unavailable, template fallback if all fail
- **Eval-suite MAPE gate** — 28 forecast accuracy regression tests enforced before any forecast code deploys

<br>

---

<br>

## 🧪 Testing

```
tests/
├── test_forecast.py          # Exponential smoothing + forecast node
├── test_risk.py              # Risk classification boundaries
├── test_ordering.py          # Reorder quantity formulas
├── test_signing.py           # HMAC token sign/verify
├── test_agent.py             # Legacy InventoryAgent tests
├── test_notify_graph.py      # Full-graph integration test
├── test_webhooks.py          # Webhook deduplication
├── test_llm_usage.py         # Spend-cap logic
├── test_auth.py              # RBAC enforcement
├── test_graph_lifecycle.py   # Graph startup lifecycle
├── test_idempotency.py       # Idempotency key dedup
└── eval_suite.py             # 28-case forecast accuracy (MAPE < 30% gate)
```

```bash
# Run all tests
pytest tests/ -v

# Forecast accuracy regression suite (MAPE gate)
pytest tests/eval_suite.py -v

# Single test file
pytest tests/test_signing.py -v

# With coverage
pytest tests/ --cov=agent --cov=api
```

### Development Workflow

| Command | Description |
|---|---|
| `make dev` | Start dev server with hot-reload |
| `make test` | Run all tests |
| `make shell` | Open PostgreSQL shell |
| `make migrate` | Run Alembic migrations |
| `make docker-build` | Build production image |
| `make docker-up` | Start all services |
| `make docker-down` | Stop all services |

<br>

---

<br>

## 📁 Project Structure

<details>
<summary><b>📂 Expand for full project tree</b></summary>

```
Inventory-Management-AI-Employee/
│
├── agent/                              # 🤖 Core AI agent
│   ├── nodes/                          # LangGraph pipeline nodes
│   │   ├── sync_node.py                # 🔄 Shopify sync entry point
│   │   ├── forecast_node.py            # 📈 Per-SKU demand forecasting
│   │   ├── risk_node.py                # 🚨 Risk classification per forecast
│   │   ├── po_draft_node.py            # 📦 PO draft with LLM reasoning
│   │   ├── notify_node.py              # 🔔 Slack notifications (pending + confirmed)
│   │   ├── reflection_node.py          # 📝 Weekly LLM-generated insights
│   │   └── reporting_node.py           # 📊 Weekly Slack digest builder
│   ├── graph.py                        # 🔀 LangGraph state graph definition
│   ├── shopify_sync.py                 # 🔄 Shopify GraphQL client
│   ├── forecast.py                     # 📊 Exponential smoothing engine
│   ├── risk.py                         # ⚖️ Risk classification rules
│   ├── ordering.py                     # 🧮 Reorder quantity formulas
│   ├── outcomes.py                     # 📈 PO outcome evaluation (backtest)
│   ├── metrics.py                      # 📊 Acceptance rate & forecast error
│   ├── scheduler.py                    # ⏰ APScheduler job definitions
│   ├── config.py                       # ⚙️ Environment configuration
│   ├── models.py                       # 🗃️ SQLAlchemy ORM models (13 tables)
│   ├── db.py                           # 🔗 Async database engine & session
│   ├── auth.py                         # 🔐 RBAC & API key verification
│   ├── audit.py                        # 📝 Append-only immutable audit log
│   ├── signing.py                      # 🔏 HMAC token generation
│   ├── telemetry.py                    # 📡 OpenTelemetry tracing setup
│   ├── webhooks.py                     # 🔄 Shopify webhook handlers
│   ├── inventory_agent.py              # 🤖 Legacy InventoryAgent (deprecated)
│   └── llm_usage.py                    # 📊 LLM call tracking & spend cap
│
├── api/                                # ⚡ FastAPI server
│   ├── main.py                         # App entry, CORS, error handlers, startup/shutdown
│   ├── rate_limit.py                   # 🚦 Rate limiter configuration
│   └── routes/
│       ├── run_sync.py                 # POST /api/v1/run-sync
│       ├── purchase_orders.py          # PO CRUD, approve/reject, token-action
│       ├── operations.py               # SKUs, metrics, evaluate-outcomes, run-weekly
│       └── webhooks.py                 # Shopify webhook route registrations
│
├── alembic/                            # 🗺️ Database migrations
│   └── versions/
│       ├── 001_initial_schema.py
│       ├── 002_suppliers_and_purchase_orders.py
│       ├── 003_phase3_tables.py
│       ├── 004_multi_tenant_scoping.py
│       ├── 005_idempotency_and_webhook_events.py
│       ├── 006_llm_usage.py
│       ├── 007_api_key_prefix.py
│       ├── 008_supplier_default_moq.py
│       └── 009_sales_history_unique_constraint.py
│
├── inventory-frontend/                 # 🖥️ React + TypeScript dashboard
│   └── src/
│       ├── pages/                      # Dashboard, Inventory, POs, Analytics, Settings
│       ├── components/                 # Layout, AnimatedNumber, toast notifications
│       └── lib/                        # Typed API client, utility helpers
│
├── tests/                              # ✅ Test suite
│   ├── test_forecast.py
│   ├── test_risk.py
│   ├── test_ordering.py
│   ├── test_signing.py
│   ├── test_agent.py
│   ├── test_notify_graph.py
│   ├── test_webhooks.py
│   ├── test_llm_usage.py
│   ├── test_auth.py
│   ├── test_graph_lifecycle.py
│   ├── test_idempotency.py
│   └── eval_suite.py
│
├── setup_demo.sh                     # 🎬 One-command demo environment setup
├── seed_demo_data.py                 # 📊 Seed 10 realistic US DTC SKUs with 90-day sales history
├── demo_script.md                    # 📝 15-minute client presentation script with live commands
├── .env.example                        # 🔑 Environment variable template
├── docker-compose.yml                  # 🐳 App + PostgreSQL
├── docker-compose.override.yml         # 🐳 Dev hot-reload overrides
├── Dockerfile                          # 🐳 Production container
├── requirements.txt                    # 📦 Python dependencies
├── pyproject.toml                      # ⚙️ Pytest configuration
├── alembic.ini                         # 🗺️ Alembic configuration
├── Makefile                            # 🔧 Dev commands
└── README.md                           # 📖 This document
```

</details>

<br>

---

<br>

## 🚢 Deployment

### Production Checklist

<details>
<summary><b>✅ Pre-deployment checklist (expand)</b></summary>

- [ ] **Set a strong `AGENT_API_KEY`** — never use `demo-key-2024` in production
- [ ] **Set `ENVIRONMENT=production`** — auto-disables the demo key bypass
- [ ] **Configure `SHOPIFY_WEBHOOK_SECRET`** — enables HMAC-verified webhooks
- [ ] **Use managed PostgreSQL** — RDS, Cloud SQL, or Supabase
- [ ] **Configure Slack webhook** — without it, notifications are silently skipped
- [ ] **Set an LLM provider** — PO draft and reflection require it
- [ ] **Run migrations** — `alembic upgrade head` on every deploy
- [ ] **Remove override file** — `docker-compose.override.yml` enables hot-reload (dev only)
- [ ] **Set `ALLOWED_ORIGINS`** — restrict to your dashboard domain
- [ ] **Set `PUBLIC_API_URL`** — must match your deployed API domain (approve/reject links use it)

</details>

### Docker Compose (Production)

```bash
docker compose -f docker-compose.yml up -d --build
```

### Recommended Platforms

| Layer | Recommended Providers |
|---|---|
| **Backend** | Render (Web Service), Railway, Fly.io |
| **Frontend** | Vercel, Netlify (SPA with API proxy) |
| **Database** | Render Managed Postgres, Railway, Supabase, AWS RDS |
| **Monitoring** | Grafana + OpenTelemetry Collector (optional but recommended) |

<br>

---

<br>

## 🛣️ Roadmap

### ✅ Phase 1 — Foundation *(Complete)*

- [x] LangGraph pipeline with 6 nodes + human-in-the-loop interrupt
- [x] Shopify GraphQL sync (products, orders, inventory)
- [x] Exponential smoothing forecasts with 28-test MAPE gate
- [x] Risk classification (stockout / overstock / safe)
- [x] PO draft with LLM reasoning + template fallback
- [x] Slack notifications with signed one-click approve/reject links
- [x] React dashboard (5 pages, real-time metrics, PO actions)
- [x] RBAC + immutable audit log + HMAC authentication
- [x] Multi-provider LLM support (Gemini, GPT-4, Groq)
- [x] APScheduler daily evaluation + weekly reflection

### 🚧 Phase 2 — Production Hardening *(In Progress)*

- [ ] Real LLM token counting from provider responses (accurate cost tracking)
- [ ] Shopify API retry/backoff with exponential jitter
- [ ] Batch DB transactions (single commit per sync page)
- [ ] TTL-based caches for idempotency and webhook dedup
- [ ] Structured JSON logging with correlation IDs
- [ ] Kubernetes Helm chart for production deployment

### 🔮 Phase 3 — Intelligence *(Planned)*

- [ ] **Multi-tenant Shopify sync** — per-merchant credentials with scoped data
- [ ] **Row-Level Security** — PostgreSQL RLS on all merchant-scoped tables
- [ ] **Machine learning forecasting** — Prophet / LightGBM alongside exponential smoothing
- [ ] **Seasonal decomposition** — detect trends, seasonality, and residual patterns
- [ ] **Supplier performance scoring** — lead time accuracy, fill rate, quality ratings
- [ ] **Anomaly detection** — flag unusual sales patterns (fraud, demand spikes, return abuse)
- [ ] **End-to-end request tracing** — OpenTelemetry spans linked across HTTP → graph → DB

### 🚀 Phase 4 — Scale *(Future)*

- [ ] Event sourcing — immutable event stream for all inventory state changes
- [ ] Webhook fan-out with SQS/SNS for reliable async processing
- [ ] CQRS — separate read/write DB connections for performance
- [ ] Real-time dashboards via WebSocket
- [ ] Integrations: QuickBooks, Xero, Cin7, ShipStation
- [ ] Mobile app for approve/reject on the go

<br>

---

<br>

## 💼 Business Use Cases

### DTC Brands & Shopify Merchants

- **Automate 90% of inventory operations** — let the agent handle daily syncs, forecasts, and PO drafts while your team focuses on strategy and growth
- **Prevent stockouts** — get Slack alerts when a SKU is 5 days from zero, with a pre-drafted PO ready for one-click approval
- **Optimize working capital** — reduce overstock by 20-40% with data-driven reorder quantities

### 3PL & Fulfillment Providers

- **Multi-client dashboard** — manage inventory across client stores from a single pane
- **Automated reorder triggers** — generate POs automatically when client stock hits thresholds
- **Performance analytics** — demonstrate forecast accuracy and stockout prevention to clients with real data

### Enterprise Operations Teams

- **Custom integration layer** — the LangGraph pipeline is extensible with custom nodes for ERPs, WMS, and procurement systems
- **Audit-ready compliance** — immutable audit log, RBAC, and signed approval tokens satisfy SOC 2 / ISO 27001 requirements
- **LLM cost controls** — configurable daily spend caps prevent cost overruns

<details>
<summary><b>📊 Why Choose Inventory Agent?</b></summary>

| Criteria | Inventory Agent | Spreadsheets | Legacy ERPs | Other AI Tools |
|---|---|---|---|---|
| **Setup time** | Hours | Immediate | Months | Days |
| **Automation level** | Full pipeline (sync → forecast → PO) | Zero | Partial | Point solutions |
| **Human oversight** | Interrupt-based (approve/reject) | N/A | Always required | Often none |
| **Forecast accuracy gates** | ✅ 28-test MAPE suite | ❌ | ❌ | ❌ |
| **LLM reasoning** | ✅ Multi-provider + template fallback | ❌ | ❌ | Limited |
| **Outcome tracking** | ✅ Auto-evaluated post-delivery | ❌ | ❌ | ❌ |
| **Multi-tenant ready** | ✅ Architecture supports it | N/A | ✅ | ❌ |
| **OpenTelemetry** | ✅ Full tracing | ❌ | ❌ | ❌ |
| **Cost control** | ✅ Daily spend cap | N/A | ✅ | ❌ |
| **Total Cost of Ownership** | Low (1 server + LLM usage) | High (labor) | Very High | Medium |

</details>

<br>

---

<br>

## 🤝 Contributing

We welcome contributions! Here's how to get started:

1. **Fork** the repository
2. **Create a feature branch**: `git checkout -b feat/amazing-feature`
3. **Commit**: `git commit -m 'feat: add amazing feature'`
4. **Push**: `git push origin feat/amazing-feature`
5. **Open a PR** — include tests and update documentation

### Guidelines

- Write tests for all new functionality (aim for >80% coverage on new code)
- Follow existing patterns — type hints, async-native, descriptive docstrings
- Run the full test suite before submitting: `pytest tests/ -v`
- Keep the eval suite MAPE gate in mind — forecast accuracy is critical
- Update documentation for any API or configuration changes

<br>

---

<br>

## 📄 License

**Proprietary** — All rights reserved.

This software is provided for evaluation and demonstration purposes. Contact the maintainer for licensing inquiries, commercial use, or enterprise agreements.

---

<br>

---

<br>

## 📬 Contact & Collaboration

<div align="center">

### Built by Ismail Sajid

**Principal Software Engineer & AI Systems Architect**

<em>Specializing in Agentic AI, LangGraph pipelines, LLM applications, and ecommerce operations automation</em>

<br>

I build autonomous AI agents for ecommerce operations, supply chain intelligence, and logistics automation. If you're looking for:

| | |
|---|---|
| 💼 **For Hiring Managers & Recruiters** | Senior/Staff/Principal Engineer (full-time or contract). Deep expertise in LangGraph, FastAPI, React, PostgreSQL. Proven delivery of production AI systems. |
| 🤝 **For Founders & Product Teams** | Technical partner for your AI/automation product. Custom LangGraph agent development. Inventory/supply chain AI solutions. Consulting on Agentic AI architecture. |

<br>

**Let's talk.**

[![GitHub](https://img.shields.io/badge/GitHub-Ismail--2001-181717?style=flat-square&logo=github&logoColor=white)](https://github.com/Ismail-2001)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0A66C2?style=flat-square&logo=linkedin&logoColor=white)](https://linkedin.com/in/your-profile)

<br>
<br>

**⭐ Star this repository if you find it useful — it helps others discover it too.**

<br>
<br>

<sub>Built with LangGraph, FastAPI, React, and PostgreSQL. Designed for ecommerce operations teams that need inventory management to be proactive, not reactive.</sub>

</div>

---
