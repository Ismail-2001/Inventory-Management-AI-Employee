<p align="center">
  <img src="https://img.shields.io/badge/status-production%20ready-22c55e?style=flat-square" alt="Status: Production Ready" />
  <img src="https://img.shields.io/badge/python-3.12%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+" />
  <img src="https://img.shields.io/badge/FastAPI-0.115%2B-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/LangGraph-0.2%2B-7C3AED?style=flat-square" alt="LangGraph" />
  <img src="https://img.shields.io/badge/PostgreSQL-16%2B-4169E1?style=flat-square&logo=postgresql&logoColor=white" alt="PostgreSQL 16+" />
  <img src="https://img.shields.io/badge/Shopify-7AB55C?style=flat-square&logo=shopify&logoColor=white" alt="Shopify" />
  <img src="https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=white" alt="React 19" />
  <img src="https://img.shields.io/badge/license-proprietary-F05032?style=flat-square" alt="License" />
</p>

<div align="center">
  <h1>Inventory Agent</h1>
  <h3>AI-Powered Inventory Management & Demand Forecasting</h3>
  <p><strong>Stop stockouts. Reduce overstock. Automate purchasing decisions.</strong></p>
  <p>An autonomous pipeline that syncs your Shopify store, forecasts demand, detects risks,<br>drafts purchase orders with AI reasoning, and notifies your team — all in real time.</p>
  <br>
  <a href="#-quick-start"><strong>Get started in 10 minutes →</strong></a>
  <br>
  <a href="#-api-overview">API Docs</a> ·
  <a href="#-features">Features</a> ·
  <a href="#-roadmap">Roadmap</a>
  <br><br>
</div>

---

## Why Inventory Agent?

Inventory mismanagement is a $1.1 trillion problem globally. Stockouts lose revenue. Overstock ties up capital. Spreadsheets don't scale. ERPs take months and cost six figures.

**This is a different approach.** A lightweight, autonomous AI pipeline that plugs into your existing Shopify store and delivers intelligent inventory decisions in minutes. No implementation consultants. No rigid workflows. No monthly minimums.

### Who is this for?

| You are... | If you... |
|---|---|
| **A DTC brand owner** | Manage 50–5,000 SKUs and can't manually review every reorder |
| **An operations director** | Want to reduce stockouts without over-ordering |
| **A Shopify Plus merchant** | Need real-time inventory decisions, not batch reports |
| **A full-service agency** | Manage inventory for multiple client stores |
| **A supply chain decision-maker** | Are evaluating AI-powered alternatives to traditional ERP |

---

## The Problem it Solves

Every day you wait, inventory decisions compound:

- **Stockouts**: Lost sales, damaged brand trust, rushed shipping costs
- **Overstock**: Cash tied up in unsold goods, warehousing costs, markdowns
- **Manual review**: Hours spent evaluating spreadsheets instead of making strategic decisions
- **Reactive purchasing**: Buying based on gut feel instead of demand signals

**Inventory Agent replaces reactive guesswork with an autonomous, data-driven pipeline.**

---

## How It Works

A 5-node LangGraph pipeline runs on-demand or on a schedule. Each node is autonomous, handles failures gracefully, and produces structured output for the next stage.

```mermaid
flowchart LR
    A[Sync<br/>Shopify → DB] --> B[Forecast<br/>Demand Prediction]
    B --> C[Risk<br/>Stockout Detection]
    C --> D{Alerts?}
    D -->|Yes| E[PO Draft<br/>AI Reasoning]
    D -->|No| F[END]
    E --> G[Notify<br/>Slack Review]
    G --> H[Approve/Reject<br/>One-Click]
    H --> I[END]
```

### Pipeline Nodes

| Step | What Happens | Outcome |
|---|---|---|
| **1. Sync** | Pulls products, inventory, and 30 days of sales from Shopify via GraphQL | Up-to-date catalog with stock levels and sales history |
| **2. Forecast** | Applies exponential smoothing per SKU to predict daily demand | `predicted_daily_demand` and `days_of_stock_remaining` per SKU |
| **3. Risk** | Flags SKUs as `critical` or `warning` when stock falls below lead-time threshold | Prioritized alerts for at-risk items |
| **4. PO Draft** | Calculates MOQ-aware reorder quantities and generates AI-powered purchasing rationale | Draft purchase orders with human-readable reasoning |
| **5. Notify** | Sends Slack summary with HMAC-signed one-click approve/reject links | Decision in seconds, not days |

> **No alerts?** If no SKU is at risk, the pipeline stops before drafting POs. No noise. No false positives.

### Scheduled Jobs

Beyond the on-demand pipeline, the system runs autonomously:

| Job | Frequency | What It Does |
|---|---|---|
| **Outcome Evaluation** | Every 24h | Measures approved POs against actual sales; tracks forecast error |
| **Weekly Reflection** | Monday 8AM | AI generates strategic insights from acceptance rates and forecast accuracy |
| **Webhook Retry** | Every 15min | Retries failed Shopify webhooks with exponential backoff (max 3) |
| **Checkpoint Cleanup** | Every 24h | Purges old LangGraph state data (30-day retention) |
| **Audit Export** | Every 24h | Ships audit logs to S3 as JSONL (SigV4-signed) |

---

## Features

###  Demand Forecasting

- **Exponential smoothing** on per-SKU sales history (configurable window, default 30 days)
- Per-SKU predictions with days-of-stock-remaining calculations
- **10-min TTL cache** for pipeline efficiency
- **Parallel execution** with per-SKU 10s timeout — slow items never block the batch

###  Stockout Risk Detection

- Two-tier model: `critical` (stock ≤ lead time) and `warning` (stock ≤ safety buffer)
- Real-time evaluation against supplier lead times and current inventory
- Integrates with supplier profiles for lead time and MOQ information

###  Intelligent Purchase Order Drafting

- **AI-powered purchasing rationale** via Groq, OpenAI, or Gemini
- **Rule-based fallback** when AI is unavailable or daily spend cap is reached
- **MOQ-aware** quantity calculation with supplier-specific overrides
- **Deduplication**: no duplicate POs for the same SKU within a 1-hour window
- Supplier-aware: respects per-SKU minimum order quantities and unit costs

###  Shopify Integration

| Capability | Detail |
|---|---|
| **Data Sync** | GraphQL API for efficient, paginated product and order sync |
| **Real-Time Webhooks** | Instant inventory updates, order creation, and product changes — no full resync |
| **Webhook Security** | HMAC-SHA256 verification + idempotency deduplication per event |
| **Rate-Limit Resilience** | Automatic retry with exponential backoff on Shopify 429 responses |
| **Dead-Letter Queue** | Failed webhooks persisted and retried with escalating backoff |

###  Human-in-the-Loop Approval

- **Multi-role access control**: `owner`, `staff`, `viewer` roles per merchant
- **One-click approve/reject** from Slack via HMAC-signed tokens (48-hour TTL)
- **Quantity override** on approval with change tracking
- **Idempotency-key support** for safe retries on approval/rejection
- **Signed action tokens** enable secure approval links without exposing API keys

###  Reporting & Analytics

- **Weekly AI reflection**: strategic insights on forecast accuracy and PO acceptance rates
- **Usage dashboard**: 7-day aggregates and 14-day time-series for POs, alerts, and LLM costs
- **Outcome evaluation**: tracks approved POs against actual sales to measure forecast error
- **Metrics API**: acceptance rates, forecast error summary, stockout rates
- **Recharts-powered dashboard** for visual analytics (included frontend)

###  Security & Compliance

| Layer | Implementation |
|---|---|
| **API Authentication** | bcrypt-hashed keys with `sk_live_` prefix, fast prefix-based lookup |
| **Role-Based Access** | `owner` / `staff` / `viewer` — enforced per endpoint |
| **Rate Limiting** | Tiered: `developer` 10/min, `business` 30/min, `enterprise` 100/min |
| **Webhook Verification** | HMAC-SHA256 with shop-specific secret |
| **Request Security** | CSP headers, HSTS, X-Frame-Options (DENY), 1MB request size limit |
| **Action Tokens** | HMAC-SHA256 signed, 48-hour TTL, no API key exposure |
| **Audit Trail** | Every action logged; nightly S3 export (SigV4, JSONL) |
| **LLM Cost Controls** | Daily spend cap (default $5), per-model cost tracking, circuit breaker after 5 failures |
| **Idempotency** | Deduplication keys prevent double-processing on retries |
| **Prompt Injection** | Boundary markers in LLM prompts with system-level guardrails |

---

## Technology Stack

| Layer | Technology |
|---|---|
| **Backend Runtime** | Python 3.12, FastAPI, Uvicorn |
| **Agent Framework** | LangGraph (StateGraph with Postgres checkpointer) |
| **Primary Database** | PostgreSQL 16 (async via SQLAlchemy 2.0 + asyncpg) |
| **Checkpointer DB** | Dedicated PostgreSQL (separated from primary in production) |
| **AI / LLM** | OpenAI (GPT-4o), Groq (Llama 3), Google Gemini — auto-detect |
| **LLM Client** | Custom with circuit breaker, exponential backoff, prompt injection guards, cost tracking |
| **API Authentication** | bcrypt-hashed keys, RBAC, HMAC-signed action tokens |
| **Rate Limiting** | slowapi with tier-based limits (developer/business/enterprise) |
| **Frontend** | React 19, TypeScript, Vite 8, Tailwind CSS 4, Recharts, Framer Motion |
| **Web Server** | Caddy (auto TLS via Let's Encrypt) |
| **Observability** | OpenTelemetry (gRPC exporter, distributed tracing) |
| **Scheduling** | APScheduler — async background jobs |
| **Infrastructure** | Docker, multi-stage builds, non-root user, health checks |
| **CI/CD** | GitHub Actions — lint → test → eval → frontend build → container push |
| **Testing** | 13 test suites (unit + integration + eval), pytest, pytest-asyncio |

---

## API Overview

### Core Pipeline

| Method | Endpoint | Auth | Rate Limit | Description |
|---|---|---|---|---|
| `POST` | `/api/v1/run-sync` | API Key | 5/min | Full pipeline (sync → forecast → risk → PO → notify) |
| `POST` | `/api/v1/run-sync-async` | API Key | 10/min | Async — returns `task_id`, poll `/api/v1/tasks/{id}` |
| `GET` | `/api/v1/tasks/{id}` | API Key | — | Poll result of async pipeline run |

### Purchase Orders

| Method | Endpoint | Auth | Rate Limit | Description |
|---|---|---|---|---|
| `GET` | `/api/v1/po` | API Key | — | List POs (optional `?status=` filter) |
| `POST` | `/api/v1/po/{id}/approve` | API Key + role | 5/min | Approve with optional `?quantity=` override |
| `POST` | `/api/v1/po/{id}/reject` | API Key + role | 5/min | Reject with optional reason |
| `GET` | `/api/v1/po/action` | Signed token | — | One-click approve/reject from Slack links |

### Keys & Access

| Method | Endpoint | Auth | Rate Limit | Description |
|---|---|---|---|---|
| `POST` | `/api/v1/keys` | API Key + owner | 3/min | Create new merchant key (sets tier: developer/business/enterprise) |
| `GET` | `/api/v1/keys` | API Key + owner | 10/min | List existing keys |
| `POST` | `/api/v1/keys/rotate` | API Key + owner | 3/min | Regenerate current key |
| `DELETE` | `/api/v1/keys/{prefix}` | API Key + owner | 3/min | Revoke a key |

### Analytics & Operations

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/skus` | API Key | List all SKUs with stock levels |
| `GET` | `/api/v1/metrics` | API Key | PO acceptance rate + forecast error summary |
| `GET` | `/api/v1/usage/summary` | API Key | 7-day aggregates (POs, alerts, LLM cost) |
| `GET` | `/api/v1/usage/daily` | API Key | 14-day time-series for charting |
| `POST` | `/api/v1/evaluate-outcomes` | API Key | Trigger PO outcome evaluation |
| `POST` | `/api/v1/run-weekly` | API Key | Trigger weekly reflection + digest |
| `GET` | `/health` | None | Health check (returns region, provider, model) |

### Shopify Webhooks (Real-Time)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/webhooks/inventory_levels_update` | HMAC | Sync single variant on stock change |
| `POST` | `/api/v1/webhooks/orders_create` | HMAC | Update sales history on new order |
| `POST` | `/api/v1/webhooks/products_update` | HMAC | Upsert product/variant on change |

> **Interactive docs**: Swagger UI at `/docs` and ReDoc at `/redoc` are available on every running instance.

---

## Quick Start

### Prerequisites

- Docker & Docker Compose
- An LLM API key (one of: Groq, OpenAI, Google Gemini)

### Setup (10 minutes)

```bash
# 1. Clone and configure
git clone <your-repo>
cd inventory-agent
cp .env.example .env

# 2. Add one LLM API key to .env
#    GROQ_API_KEY=gsk_...       (recommended — fastest)
#    OPENAI_API_KEY=sk-...
#    GOOGLE_API_KEY=AIza...

# 3. Launch
docker compose up -d --build

# 4. Run migrations
docker compose exec inventory-agent alembic upgrade head

# 5. Seed demo data (10 SKUs, 90 days of sales history)
docker compose exec inventory-agent python seed_demo_data.py

# 6. Verify
curl http://localhost:8002/health

# 7. Run the full pipeline
curl -X POST http://localhost:8002/api/v1/run-sync \
  -H "X-API-Key: demo-key-2024"
```

> First run will create forecasts, risk alerts, and draft purchase orders for the demo SKUs. You'll see output immediately.

**API Playground**: [http://localhost:8002/docs](http://localhost:8002/docs)  
**Frontend Dashboard**: [http://localhost:5173](http://localhost:5173) (dev) or served at `/` in production

### Docker Compose Profiles

| Profile | Command | Services |
|---|---|---|
| **Development** | `docker compose up -d --build` | FastAPI (hot-reload) + PostgreSQL 16 |
| **Production** | `docker compose -f docker-compose.prod.yml up -d --build` | Adds Caddy (auto TLS) + daily DB backups |

---

## Configuration

### Essential

| Variable | Required | Default | Description |
|---|---|---|---|
| `GROQ_API_KEY` | One of | — | Groq API key (fastest inference) |
| `OPENAI_API_KEY` | One of | — | OpenAI API key |
| `GOOGLE_API_KEY` | One of | — | Google Gemini API key |
| `LLM_PROVIDER` | No | `openai` | `openai`, `groq`, or `gemini` |
| `DATABASE_URL` | Yes | `postgresql+asyncpg://inventory:inventory@localhost:5432/inventory_agent` | Primary database |

### Shopify

| Variable | Required (Production) | Description |
|---|---|---|
| `SHOPIFY_STORE_DOMAIN` | Yes | Your store domain (e.g., `my-store.myshopify.com`) |
| `SHOPIFY_ADMIN_API_TOKEN` | Yes | Shopify Admin API access token |
| `SHOPIFY_WEBHOOK_SECRET` | For webhooks | HMAC secret for webhook verification |

### Auth & Security

| Variable | Default | Description |
|---|---|---|
| `AGENT_API_KEY` | `demo-key-2024` | Master API key for authentication |
| `ALLOW_DEMO_KEY` | `true` (auto-disabled in production) | Accept demo key |
| `PUBLIC_API_URL` | `http://localhost:8002` | Public URL for signed Slack approval links |

### Enterprise

| Variable | Default | Description |
|---|---|---|
| `DATABASE_READ_URL` | — | Read-replica connection for analytics queries |
| `CHECKPOINTER_DATABASE_URL` | (derived) | Must be separate from `DATABASE_URL` in production |
| `DEPLOYMENT_REGION` | `local` | Region label visible in `/health` |
| `AUDIT_S3_BUCKET` | — | S3 bucket for nightly audit log export (JSONL) |
| `AUDIT_S3_REGION` | `us-east-1` | S3 region |
| `AUDIT_S3_ACCESS_KEY` | — | S3 access key |
| `AUDIT_S3_SECRET_KEY` | — | S3 secret key |
| `SYNC_DAYS` | `30` | Days of sales history to sync from Shopify |
| `SLACK_WEBHOOK_URL` | — | Slack incoming webhook for notifications |

### LLM Tuning

| Variable | Default | Description |
|---|---|---|
| `MODEL_NAME` | `gemini-2.0-flash` | LLM model per provider |
| `DAILY_LLM_SPEND_CAP` | `5` | Daily LLM cost cap (USD) |
| `TEMPERATURE` | `0.3` | LLM temperature (lower = more deterministic) |
| `MAX_TOKENS` | `1024` | Max LLM output tokens |

---

## Production Deployment

```bash
DOMAIN=inventory.yourcompany.com docker compose -f docker-compose.prod.yml up -d --build
```

**Architecture**: `Browser — HTTPS → Caddy (auto TLS) → FastAPI (internal :8002)`

Caddy terminates TLS with automatic Let's Encrypt certificates. FastAPI serves both the API and the built React frontend. A dedicated backup service runs daily `pg_dump` with 30-day retention.

### Production Checklist

- [ ] Set `ENVIRONMENT=production`
- [ ] Configure `SHOPIFY_STORE_DOMAIN` and `SHOPIFY_ADMIN_API_TOKEN`
- [ ] Set `PUBLIC_API_URL` to your public domain
- [ ] Configure `CHECKPOINTER_DATABASE_URL` as a **separate** database from `DATABASE_URL`
- [ ] Set a strong `AGENT_API_KEY`
- [ ] Configure `SLACK_WEBHOOK_URL` for pipeline notifications
- [ ] Set `SHOPIFY_WEBHOOK_SECRET` for webhook verification
- [ ] Configure `DOMAIN` for automatic TLS and HSTS headers
- [ ] (Optional) Set `DATABASE_READ_URL` for read-replica offloading
- [ ] (Optional) Configure `AUDIT_S3_*` for compliance-grade audit logging

---

## Frontend Dashboard

A React 19 dashboard ships with the agent. It provides operational visibility into your inventory pipeline:

**Pages:**
| Page | Purpose |
|---|---|
| **Dashboard** | Overview cards (total SKUs, pending POs, alerts) + Run Sync button + forecast accuracy |
| **Inventory** | Full SKU table with stock levels, lead times, and current status |
| **Purchase Orders** | Pending approval queue with approve/reject UI and quantity override |
| **Analytics** | Recharts-powered bar charts: PO acceptance rates + forecast error distribution |
| **Settings** | API configuration, services status, system information |

```bash
# Development mode
cd inventory-frontend
npm ci
npm run dev    # → http://localhost:5173 (proxies /api → localhost:8002)
```

In production, the built frontend (`dist/`) is served directly by FastAPI's `StaticFiles` — no separate frontend server needed.

---

## Testing

The project includes 13 test suites covering unit, integration, and evaluation scenarios:

```bash
# Full test suite
pytest tests/ -v

# Integration tests only (requires PostgreSQL + Alembic migrations)
pytest tests/test_integration.py -v

# Forecast accuracy evaluation (MAPE threshold)
pytest tests/eval_suite.py -v

# Unit tests only (no external dependencies)
pytest tests/ -v --ignore=tests/test_integration.py
```

**CI pipeline**: Ruff lint → Alembic migrations → pytest → eval suite → frontend build → Docker image push to GHCR

---

## Demo Data

A seeded demo environment is included for evaluation:

- **10 SKUs** across a US DTC retailer product line (Bluetooth headphones, USB-C chargers, cables, monitors, mechanical keyboards)
- **Stock levels** ranging from 0 (critical) to 200 (healthy)
- **Lead times** from 5 to 21 days
- **90 days** of generated sales history with realistic weekday/weekend patterns, seasonal variation, and random noise
- A configured supplier with MOQ and unit cost data for testing PO drafting

Run `python seed_demo_data.py` after migrations to populate the database.

---

## Architecture

### Agent Pipeline (LangGraph StateGraph)

```
                    ┌──────────┐
                    │   Sync   │
                    │ Shopify  │
                    │  → DB    │
                    └────┬─────┘
                         │
                    ┌────▼─────┐
                    │ Forecast │
                    │  Stats   │
                    │  + Cache │
                    └────┬─────┘
                         │
                    ┌────▼─────┐
                    │   Risk   │
                    │  Rules   │
                    └────┬─────┘
                         │
                    ┌────▼──────┐
                    │  Alerts?  │
                    │  ──────── │
                    │  No → END │
                    │  Yes ────►│
                    └────┬──────┘
                         │
                    ┌────▼──────┐
                    │ PO Draft  │
                    │ AI Reason │
                    │ MOQ-aware │
                    └────┬──────┘
                         │
                    ┌────▼──────┐
                    │  Notify   │
                    │  Slack    │
                    └────┬──────┘
                         │
                    ┌────▼──────┐
                    │Approve/Rej│
                    │ One-Click │
                    └───────────┘
```

### Database Schema (PostgreSQL 16)

| Table | Purpose | Key Fields |
|---|---|---|
| `skus` | Product catalog | variant_id, sku_code, current_stock, location_id |
| `merchants` | Tenant accounts | hashed_api_key, key_prefix, shopify_domain, tier |
| `sales_history` | Daily unit sales per SKU | sku_id, date, units_sold |
| `forecasts` | Demand predictions | sku_id, predicted_daily_demand, days_of_stock_remaining |
| `risk_alerts` | Stockout warnings | sku_id, risk_level (critical/warning), reason |
| `suppliers` | Supplier profiles | default_lead_time, default_moq, moq_by_sku (JSONB) |
| `purchase_orders` | Draft and finalized POs | sku_id, status, quantity, unit_cost, reasoning_text, thread_id |
| `po_outcomes` | Post-delivery evaluation | actual_stockout, forecast_error_pct |
| `users` | Team members per merchant | email, role (owner/staff/viewer) |
| `audit_log` | Immutable action log | actor_type, action, details (JSONB), created_at |
| `failed_webhooks` | Dead-letter queue | payload, error, retry_count, next_retry_at |
| `llm_usage` | Cost tracking | node_name, tokens_in/out, estimated_cost |
| `webhook_events` | Idempotency tracking | event_id (PK), event_type |
| `reflection_insights` | Weekly AI analysis | week_start, insight_text, supporting_data (JSONB) |

### Supporting Services

| Service | Role | Technology |
|---|---|---|
| **FastAPI** | HTTP server + middleware | Uvicorn, slowapi rate limiting, OpenTelemetry tracing |
| **PostgreSQL** | Primary data store | Async via SQLAlchemy 2.0 + asyncpg |
| **LLM Providers** | AI reasoning | Groq (default), OpenAI, Google Gemini — auto-detected |
| **Shopify** | Inventory source | GraphQL Admin API + HMAC-verified webhooks |
| **Slack** | Notifications | Incoming webhooks with signed action links |
| **Caddy** | Reverse proxy + TLS | Auto Let's Encrypt, production only |
| **S3** | Audit archive | SigV4-signed PUT, no boto3 dependency |

### CI/CD Pipeline (GitHub Actions)

Every push to `main`:

1. **Lint**: `ruff check .` (Python code style)
2. **Test**: pytest with Postgres service container (Alembic migrations run first)
3. **Evaluate**: Forecast accuracy eval suite (MAPE threshold)
4. **Build**: React frontend production build (npm ci → npm run build)
5. **Package**: Multi-stage Docker image → GitHub Container Registry (`ghcr.io`)

---

## Roadmap

> Features planned for future releases. Priorities are driven by client demand.

| Area | Planned |
|---|---|
| **AI / Forecasting** | Multi-model ensemble forecasting (Prophet + exponential smoothing); anomaly detection via LLM; automated model selection |
| **Integrations** | Amazon SP-API (multi-channel inventory); QuickBooks/Xero sync for automated accounting; email-based approvals (reply-to-approve) |
| **Platform** | Multi-region active-active deployment; Redis cache backend (replace in-memory); Celery/ARQ for distributed task processing; multi-warehouse support |
| **Analytics** | Interactive drill-down dashboard; exportable reports (PDF/CSV); anomaly timeline visualization; inventory turnover analytics |
| **Machine Learning** | Prophet/NeuralProphet for non-linear patterns; automated forecast model selection per SKU; A/B forecast comparison |
| **Compliance** | SOC 2 audit support; data retention policies; PII classification and redaction |

---

## License

Proprietary. All rights reserved.

---

<p align="center">
  <strong>Inventory Agent</strong> — built for merchants who need intelligent, autonomous inventory management<br>
  without the overhead, cost, and complexity of traditional ERP systems.
</p>

<p align="center">
  <a href="#-quick-start">Get Started</a> ·
  <a href="#-api-overview">API Docs</a> ·
  <a href="#-roadmap">Roadmap</a>
</p>
