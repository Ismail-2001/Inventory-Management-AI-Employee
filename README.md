# Inventory Management AI Employee

> **Your autonomous inventory operations agent.** Syncs, forecasts, detects risks, drafts purchase orders, and reports — 24/7, with human oversight where it matters.

![CI](https://github.com/Ismail-2001/Inventory-Management-AI-Employee/actions/workflows/ci.yml/badge.svg) ![LangGraph](https://img.shields.io/badge/Powered%20By-LangGraph-purple) ![FastAPI](https://img.shields.io/badge/Backend-FastAPI-green) ![React](https://img.shields.io/badge/Frontend-React%20%2B%20TypeScript-blue) ![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL-336791)

---

## The Problem

Inventory operations are **reactive, manual, and expensive**:

- Teams spend *hours per day* checking stock levels instead of growing the business
- Stockouts cost **3–5× the product's value** in lost revenue and damaged trust
- Overstock ties up **30–50% of working capital** in dead inventory
- Purchase orders bounce between email, spreadsheets, and Slack — taking **3–5 days** to approve
- No one has time to analyze forecast accuracy or track whether POs actually worked

## The Solution

A **full-time, autonomous inventory operations agent** that:

1. **Watches every SKU** — syncs sales, stock, and product data from Shopify automatically
2. **Predicts demand** — statistical forecasting (not guesswork) for 30/60/90-day horizons
3. **Flags risks before they happen** — stockout, overstock, and dead-stock alerts per SKU
4. **Drafts purchase orders** — calculates quantity, cost, and explains *why* in plain English
5. **Pauses for your approval** — one-click approve/reject from the dashboard or Slack
6. **Tracks outcomes** — did the PO prevent a stockout? Was the forecast accurate? Measured automatically.
7. **Reports weekly** — AI-generated insights and recommendations delivered to your team

---

## Features

| Capability | Detail |
|---|---|
| **Shopify Sync** | Fetches products, orders, and inventory levels via GraphQL — read-only, no writes |
| **Demand Forecasting** | Exponential smoothing for 30/60/90-day projections per SKU |
| **Risk Detection** | Classifies every SKU as stockout, overstock, dead-stock, or healthy |
| **AI Purchase Orders** | Drafts POs with calculated quantity, unit cost, total cost, and LLM reasoning |
| **Human Approval** | Pauses the agent workflow; approve/reject from dashboard or Slack with one click |
| **Quantity Editing** | Approvers can adjust PO quantities before approval |
| **Outcome Tracking** | Evaluates POs post-fulfillment — measures acceptance rate and forecast error |
| **Weekly Reflection** | LLM reviews metrics and generates a management summary with recommendations |
| **Slack Notifications** | Real-time alerts for risks, pending POs, and weekly digests |
| **RBAC** | API key auth with owner, staff, and viewer roles |
| **Audit Trail** | Append-only log of every state change — immutable, queryable |
| **Observability** | OpenTelemetry tracing across every agent node |
| **React Dashboard** | Real-time metrics, PO management, analytics, and inventory browser |
| **Animated UI** | Framer Motion page transitions, animated numbers, toast notifications |
| **Eval Suite** | 28 forecast accuracy regression tests with a deploy-blocking MAPE gate |

---

## How It Works

```
                    ┌─────────────┐
                    │   Shopify   │
                    └──────┬──────┘
                           │ GraphQL
                           ▼
    ┌──────────────────────────────────────────┐
    │           LangGraph Agent Flow           │
    │                                          │
    │  Sync ──► Forecast ──► Risk ──► PO ──► Notify
    │                               │
    │                       Human Approval
    │                      (interrupt_after)
    └──────────────────────────────────────────┘
                           │
                           ▼
                ┌──────────────────────┐
                │     PostgreSQL       │
                │  (state + history)   │
                └──────────────────────┘
```

The agent is a directed state graph. Each node is an independent, traced function. The graph checkpoints state in PostgreSQL after every node — if the process crashes mid-flow, it resumes from the last checkpoint. **No data loss. No skipped steps.**

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Runtime** | Python 3.12 / FastAPI |
| **Orchestration** | LangGraph (state graph + Postgres checkpointer) |
| **Database** | PostgreSQL 16 (SQLAlchemy async + asyncpg) |
| **LLM** | Gemini 2.0 Flash / OpenAI GPT-4 (configurable) |
| **Frontend** | React 19 + TypeScript + Vite + Tailwind CSS 4 |
| **Animations** | Framer Motion |
| **Migrations** | Alembic |
| **Notifications** | Slack Incoming Webhooks |
| **Observability** | OpenTelemetry (console + OTLP export) |
| **Scheduling** | APScheduler (daily outcome eval + weekly reflection) |
| **Auth** | HMAC-signed tokens + API key with bcrypt verification |
| **Testing** | pytest (asyncio mode) + 28-case eval suite with MAPE gate |

---

## Quick Start

### Prerequisites

- Docker & Docker Compose (recommended) or Python 3.12+ locally
- A Shopify dev store with an Admin API token
- A Gemini API key (or OpenAI key)
- A Slack webhook URL for notifications (optional)

### 1. Clone & Configure

```bash
git clone https://github.com/Ismail-2001/Inventory-Management-AI-Employee.git
cd Inventory-Management-AI-Employee
cp .env.example .env
```

Edit `.env` with your credentials:

```env
SHOPIFY_STORE_DOMAIN=your-store.myshopify.com
SHOPIFY_ADMIN_API_TOKEN=shpat_xxxx
GOOGLE_API_KEY=AIza...
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

### 2. Run with Docker

```bash
docker compose up -d
```

The API starts at `http://localhost:8002`, PostgreSQL on `5432`. Swagger UI at `http://localhost:8002/docs`.

### 3. Run the Frontend (separate terminal)

```bash
cd inventory-frontend
npm install
npm run dev
```

Opens the dashboard at `http://localhost:5173`. The dev server proxies `/api` calls to the backend.

### 4. Trigger a Sync

```bash
curl -X POST http://localhost:8002/api/v1/run-sync \
  -H "X-API-Key: demo-key-2024"
```

The agent syncs products, runs forecasts, detects risks, drafts POs, and sends Slack notifications. POs pause for human approval before they proceed.

---

## API Endpoints

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | — | Health check |
| `POST` | `/api/v1/run-sync` | API key | Trigger full sync → forecast → risk → PO → notify flow |
| `GET` | `/api/v1/skus` | API key | List all synced SKUs with stock levels |
| `GET` | `/api/v1/po` | API key | List all purchase orders (filter by `?status=`) |
| `POST` | `/api/v1/po/{id}/approve` | API key | Approve a PO (optionally override quantity) |
| `POST` | `/api/v1/po/{id}/reject` | API key | Reject a PO with a reason |
| `GET` | `/api/v1/po/action?token=` | Signed HMAC | One-click approve/reject from Slack (no login) |
| `GET` | `/api/v1/metrics?days=30` | API key | PO acceptance rates and forecast error summary |
| `POST` | `/api/v1/evaluate-outcomes` | API key | Evaluate pending PO outcomes |
| `POST` | `/api/v1/run-weekly` | API key | Generate weekly reflection report |
| `POST` | `/webhooks/shopify` | HMAC | Receive Shopify inventory/webhook events |
| `GET` | `/docs` | — | Swagger UI |
| `GET` | `/redoc` | — | ReDoc UI |

---

## Project Structure

```
├── agent/                        # Core agent logic
│   ├── nodes/                    # LangGraph node implementations
│   │   ├── sync_node.py          # Shopify data sync
│   │   ├── forecast_node.py      # Demand forecasting
│   │   ├── risk_node.py          # Risk classification
│   │   ├── po_draft_node.py      # PO generation + LLM reasoning
│   │   ├── notify_node.py        # Slack notifications
│   │   ├── reflection_node.py    # Weekly insight generation
│   │   └── reporting_node.py     # Slack digest formatting
│   ├── graph.py                  # LangGraph state machine
│   ├── shopify_sync.py           # Shopify GraphQL client
│   ├── forecast.py               # Exponential smoothing engine
│   ├── risk.py                   # Risk classification rules
│   ├── ordering.py               # Reorder quantity formulas
│   ├── outcomes.py               # PO outcome evaluation
│   ├── metrics.py                # Acceptance rate & forecast error
│   ├── scheduler.py              # APScheduler job definitions
│   ├── config.py                 # Environment configuration
│   ├── models.py                 # SQLAlchemy ORM models
│   ├── db.py                     # Async database session
│   ├── auth.py                   # RBAC and API key verification
│   ├── audit.py                  # Append-only audit log
│   ├── signing.py                # HMAC token generation
│   ├── telemetry.py              # OpenTelemetry tracing
│   └── webhooks.py               # Shopify HMAC verification
├── api/                          # FastAPI server
│   ├── main.py                   # App entry, CORS, error handlers
│   └── routes/
│       ├── run_sync.py           # POST /api/v1/run-sync
│       ├── purchase_orders.py    # GET/POST /api/v1/po/*
│       ├── operations.py         # GET /api/v1/skus, metrics, evaluate
│       └── webhooks.py           # POST /webhooks/shopify
├── alembic/                      # Database migrations
│   └── versions/
│       ├── 001_initial_schema.py
│       ├── 002_suppliers_and_purchase_orders.py
│       ├── 003_phase3_tables.py
│       └── 004_multi_tenant_scoping.py
├── inventory-frontend/           # React dashboard
│   └── src/
│       ├── pages/                # Dashboard, Inventory, POs, Analytics, Settings
│       ├── components/           # Layout shell, AnimatedNumber
│       └── lib/                  # API client, utils, toast notifications
├── tests/
│   ├── test_forecast.py
│   ├── test_risk.py
│   ├── test_ordering.py
│   ├── test_signing.py
│   ├── test_agent.py
│   └── eval_suite.py             # 28-case regression suite (MAPE < 30%)
├── Dockerfile
├── docker-compose.yml
└── Makefile
```

---

## Configuration

All configuration is via environment variables (see `.env.example`).

| Variable | Required | Default | Description |
|---|---|---|---|
| `SHOPIFY_STORE_DOMAIN` | Yes | — | Your Shopify store domain |
| `SHOPIFY_ADMIN_API_TOKEN` | Yes | — | Shopify Admin API token |
| `DATABASE_URL` | No | `postgresql+asyncpg://...` | Async Postgres connection string |
| `LLM_PROVIDER` | No | `openai` | LLM provider: `openai` or `google` |
| `OPENAI_API_KEY` | Varies | — | OpenAI API key |
| `GOOGLE_API_KEY` | Varies | — | Google AI API key |
| `AGENT_API_KEY` | No | `demo-key-2024` | API key for endpoint authentication |
| `SLACK_WEBHOOK_URL` | No | — | Slack incoming webhook URL |
| `SHOPIFY_WEBHOOK_SECRET` | No | — | Shopify app shared secret |
| `ENVIRONMENT` | No | `development` | Set to `production` to disable demo key |
| `ALLOW_DEMO_KEY` | No | `true` | Must be `true` for demo key to work |

---

## Testing

```bash
# Run all unit tests
pytest tests/ -v

# Run forecast accuracy regression suite
python -m pytest tests/eval_suite.py -v
```

The eval suite runs 28 forecast accuracy tests against historical data. It enforces a **30% MAPE (Mean Absolute Percentage Error)** threshold — if forecast accuracy degrades beyond this gate, the suite fails.

---

## Deployment

### Production Checklist

1. **Set a strong `AGENT_API_KEY`** — never use the demo key in production
2. **Set `ENVIRONMENT=production`** — disables the demo key automatically
3. **Configure `SHOPIFY_WEBHOOK_SECRET`** — enables HMAC-verified Shopify webhooks
4. **Set up a production database** — use a managed PostgreSQL 16 instance
5. **Enable Slack** — without a webhook URL, notifications are silently skipped
6. **Configure an LLM provider** — the PO draft and reflection nodes require an LLM
7. **Run migrations** — `alembic upgrade head` on deploy
8. **Remove `docker-compose.override.yml`** — it enables hot-reload, not for production

### Docker Compose (production)

```bash
docker compose -f docker-compose.yml up -d --build
```

---

## Security

- **RBAC enforced** — owner/staff roles required for PO approval; viewers are read-only
- **Demo key gated** — `demo-key-2024` only works when `ALLOW_DEMO_KEY=true` (disabled in production)
- **CORS locked down** — no wildcard origins; configurable via `ALLOWED_ORIGINS`
- **HMAC signed links** — Slack approval links use signed tokens, not plain IDs
- **No secrets in code** — all credentials via environment variables, `.env` is gitignored

---

## License

Proprietary — All rights reserved.

---

*Built with LangGraph, FastAPI, React, and PostgreSQL. Designed for ecommerce operations teams that need inventory management to be proactive, not reactive.*
