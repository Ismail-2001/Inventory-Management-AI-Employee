
<p align="center">
  <img src="https://img.shields.io/badge/status-production%20ready-22c55e?style=flat-square" alt="Status" />
  <img src="https://img.shields.io/badge/python-3.12%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-0.115%2B-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/LangGraph-0.2%2B-7C3AED?style=flat-square" alt="LangGraph" />
  <img src="https://img.shields.io/badge/PostgreSQL-16%2B-4169E1?style=flat-square&logo=postgresql&logoColor=white" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/Shopify-7AB55C?style=flat-square&logo=shopify&logoColor=white" alt="Shopify" />
  <img src="https://img.shields.io/badge/license-proprietary-F05032?style=flat-square" alt="License" />
</p>

<h1 align="center">Inventory Agent</h1>
<p align="center"><strong>AI-Powered Inventory Management &amp; Demand Forecasting</strong></p>
<p align="center">
  An autonomous pipeline that syncs inventory, forecasts demand, detects stockout risks,<br>
  drafts purchase orders with LLM-powered reasoning, and notifies stakeholders via Slack.
</p>

---

## The Problem

Inventory mismanagement costs businesses billions every year: stockouts lose revenue, overstocking ties up capital, and manual review across hundreds of SKUs is impossible at scale. Spreadsheets don't scale, and off-the-shelf ERPs are rigid, expensive, and require months of implementation.

Inventory Agent solves this with an **autonomous, lightweight pipeline** that plugs directly into your existing Shopify store and makes intelligent inventory decisions in minutes — not months.

---

## What It Does

| Step | What Happens | Business Value |
|------|-------------|----------------|
| **1. Sync** | Pulls products, inventory levels, and sales history from Shopify via GraphQL | Your real-time catalog, no manual exports |
| **2. Forecast** | Applies exponential smoothing on sales history (configurable window, default 30 days) to predict daily demand | Accurate demand signal per SKU |
| **3. Risk** | Flags SKUs as `critical` or `warning` when stock runs low relative to lead time | Prevent stockouts before they happen |
| **4. Draft PO** | Calculates optimal reorder quantities and generates LLM-powered purchasing rationale | Data-backed purchasing decisions |
| **5. Notify** | Sends a Slack summary with one-click approve/reject links | Act in seconds, not days |
| **6. Reflect** (weekly) | Reviews outcomes, calculates forecast accuracy, and generates strategic insights | Continuous improvement |

All of this runs autonomously on a schedule or on-demand via a single API call.

---

## Key Features

###  Demand Forecasting
- Exponential smoothing on per-SKU sales history (configurable window)
- Per-SKU predictions with days-of-stock-remaining calculations
- Forecast caching (10-minute TTL) for pipeline efficiency
- Parallel execution with per-SKU timeout (10s) prevents slow items from blocking the batch

###  Stockout Risk Detection
- Two-tier risk model: `critical` (stock ≤ lead time) and `warning` (stock ≤ safety buffer)
- Real-time evaluation against supplier lead times and current inventory levels

###  Intelligent Purchase Order Drafting
- LLM-powered purchasing rationale via Groq, OpenAI, or Gemini
- Rule-based fallback template if LLM is unavailable or capped
- MOQ-aware quantity calculation with supplier-specific overrides
- **Deduplication**: prevents duplicate POs for the same SKU within a 1-hour window
- Supplier-aware: respects per-SKU MOQ and unit cost from supplier profiles

###  Shopify Integration
- **GraphQL API** (not REST) for efficient, paginated data sync
- **Real-time webhook handlers** for inventory updates, order creation, and product changes — no full resync needed
- **HMAC-SHA256 verification** and idempotency deduplication for all incoming webhooks
- **Rate-limit resilience**: automatic retry with exponential backoff on Shopify 429 responses
- **Dead-letter queue**: failed webhooks are persisted and automatically retried with exponential backoff

###  Human-in-the-Loop Approval
- Multi-role access control: `owner`, `staff`, `viewer` roles per merchant
- One-click approve/reject from Slack via **HMAC-signed tokens** (48-hour TTL)
- Quantity override on approval with change tracking (`edited_before_approval`)
- Idempotency-key support for safe retries on approval/rejection

###  Reporting & Analytics
- **Weekly reflection**: LLM-generated insights on forecast accuracy and PO acceptance rates
- **Usage dashboard**: 7-day aggregates and 14-day time-series for POs, alerts, and LLM costs
- **Outcome evaluation**: tracks approved POs against actual sales to measure forecast error
- **Metrics API**: acceptance rates, forecast error summary, stockout rates

###  Security

| Layer | Implementation |
|-------|---------------|
| **API Authentication** | bcrypt-hashed API keys with `sk_live_` prefix, fast prefix-based lookup |
| **Role-Based Access** | `owner` / `staff` / `viewer` — enforced per endpoint |
| **Rate Limiting** | Tiered: `developer` 10/min, `business` 30/min, `enterprise` 100/min |
| **Webhook Verification** | HMAC-SHA256 with shop-by-shop secret |
| **Request Security** | CSP headers, HSTS, X-Frame-Options, 1MB request size limit |
| **Idempotency** | Deduplication keys prevent double-processing on retries |
| **Prompt Injection Protection** | Boundary markers in LLM prompts with system-level guardrails |

###  Enterprise-Grade Infrastructure

| Capability | Details |
|------------|---------|
| **Read Replicas** | Separate read-only connection pool (`DATABASE_READ_URL`) for analytics queries |
| **Audit Trail** | Every action logged with actor, action, target, and details; nightly export to S3 (JSONL, SigV4-signed) |
| **LLM Cost Controls** | Daily spend cap (default $5), per-model cost tracking, circuit breaker after 5 failures |
| **Checkpoint Cleanup** | Automatic 30-day TTL on LangGraph checkpoint data |
| **Background Processing** | Async task queue for runs exceeding 120s; polling endpoint for results |
| **Scheduled Jobs** | Daily outcome evaluation, weekly reflection, webhook retry (15min), checkpoint cleanup (24h), audit export (24h) |
| **Database Backups** | Automatic daily pg_dump with 30-day retention (production compose) |
| **Observability** | OpenTelemetry tracing with gRPC exporter, structured JSON logging |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Inventory Agent Pipeline                          │
│                            (LangGraph StateGraph)                           │
├────────┬────────┬────────┬────────┬────────┬────────┬────────┬────────────┤
│  Sync  │────▶│Forecast│────▶│  Risk  │─▶│PO Draft│─▶│ Notify │─▶│  END   │
│Shopify/│     │  Stats │     │ Rules  │  │  LLM   │  │  Slack │  │        │
│   DB   │     │+ Sales │     │        │  │ Reason │  │        │  │        │
└────────┘     └────────┘     └───┬────┘  └────────┘  └────────┘  └────────┘
                                  │
                          ┌───────▼───────┐
                          │  No alerts?   │
                          │   → SKIP PO   │
                          └───────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                        Supporting Infrastructure                           │
├───────────────────┬──────────────────────┬──────────────────┬───────────────┤
│   FastAPI Server  │   PostgreSQL 16      │   LLM Providers  │   Shopify     │
│   ┌───────────┐   │   ┌──────────────┐   │   ┌─────────┐   │   ┌───────┐  │
│   │ API Routes│   │   │ skus         │   │   │ OpenAI  │   │   │GraphQL│  │
│   │ Auth/RBAC │   │   │ forecasts    │   │   │ Groq    │   │   │REST   │  │
│   │ Rate Lim  │   │   │ purchase_ords│   │   │ Gemini  │   │   │Webhook│  │
│   │ Webhooks  │   │   │ risk_alerts  │   │   └─────────┘   │   └───────┘  │
│   │ Scheduler │   │   │ audit_logs   │   │                  │              │
│   │ Frontend  │   │   └──────────────┘   │                  │              │
│   └───────────┘   │   (Read replica)     │                  │              │
└───────────────────┴──────────────────────┴──────────────────┴──────────────┘
```

### Pipeline Nodes

| Node | Trigger | What It Produces |
|------|---------|-----------------|
| **sync** | On run | `skus[]`, `synced_products`, `synced_sales` |
| **forecast** | After sync | `forecasts[]` with `predicted_daily_demand`, `days_of_stock_remaining` |
| **risk** | After forecast | `risk_alerts[]` with `critical`/`warning` levels |
| **po_draft** | If alerts exist | `purchase_orders[]` with LLM reasoning (deduped within 1h per SKU) |
| **notify_pending** | If POs exist | Slack summary with approve/reject links |
| **notify_confirmed** | On approve/reject | Slack confirmation message |

### Scheduled Jobs (Background)

| Job | Frequency | Purpose |
|-----|-----------|---------|
| `daily_outcome_eval` | Every 24h | Evaluate approved POs against actual outcomes |
| `weekly_reflection` | Monday 8:00 AM | LLM-generated weekly insights + report digest |
| `retry_failed_webhooks` | Every 15 min | Retry dead-lettered webhooks (exponential backoff, max 3) |
| `cleanup_old_checkpoints` | Every 24h | Purge LangGraph checkpoints older than 30 days |
| `export_audit_logs` | Every 24h | Ship audit logs to S3 as JSONL |

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| **Runtime** | Python 3.12, FastAPI, Uvicorn |
| **Agent Framework** | LangGraph (StateGraph with checkpoints) |
| **Database** | PostgreSQL 16 (async via SQLAlchemy + asyncpg) |
| **LLM** | OpenAI (GPT-4o), Groq (Llama 3), Google Gemini |
| **LLM Client** | Custom with circuit breaker, exponential backoff, prompt injection guards |
| **API Auth** | bcrypt-hashed keys, HMAC-signed action tokens |
| **Rate Limiting** | slowapi with tier-based limits |
| **Frontend** | React 19, TypeScript, Vite 8, Tailwind CSS 4, Recharts |
| **Web Server** | Caddy (auto TLS via Let's Encrypt) |
| **Observability** | OpenTelemetry (gRPC exporter) |
| **Scheduling** | APScheduler (BackgroundScheduler) |
| **Testing** | pytest, pytest-asyncio |
| **CI/CD** | GitHub Actions (lint, test, build, container push) |
| **Container** | Docker, multi-stage (Node build → Python runtime), non-root user |

---

## API Overview

### Core Pipeline

| Method | Endpoint | Auth | Rate Limit | Description |
|--------|----------|------|------------|-------------|
| `POST` | `/api/v1/run-sync` | API Key | 5/min | Full pipeline (sync → forecast → risk → PO → notify) |
| `POST` | `/api/v1/run-sync-async` | API Key | 10/min | Async pipeline — returns `task_id` immediately |
| `GET` | `/api/v1/tasks/{id}` | API Key | — | Poll async pipeline result |

### Purchase Orders

| Method | Endpoint | Auth | Rate Limit | Description |
|--------|----------|------|------------|-------------|
| `GET` | `/api/v1/po` | API Key | — | List POs (optional `?status=` filter) |
| `POST` | `/api/v1/po/{id}/approve` | API Key + role | 5/min | Approve with optional `?quantity=` override |
| `POST` | `/api/v1/po/{id}/reject` | API Key + role | 5/min | Reject with optional reason |
| `GET` | `/api/v1/po/action` | Signed token | — | Token-based approve/reject (from Slack links) |

### Key Management

| Method | Endpoint | Auth | Rate Limit | Description |
|--------|----------|------|------------|-------------|
| `POST` | `/api/v1/keys` | API Key + owner | 3/min | Create new merchant key (with tier) |
| `GET` | `/api/v1/keys` | API Key + owner | 10/min | List existing key prefixes |
| `POST` | `/api/v1/keys/rotate` | API Key + owner | 3/min | Regenerate current key |
| `DELETE` | `/api/v1/keys/{prefix}` | API Key + owner | 3/min | Revoke a key |

### Analytics & Operations

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/api/v1/skus` | API Key | List all SKUs with stock levels |
| `GET` | `/api/v1/metrics` | API Key | PO acceptance rate + forecast error |
| `GET` | `/api/v1/usage/summary` | API Key | 7-day aggregates (POs, alerts, LLM cost) |
| `GET` | `/api/v1/usage/daily` | API Key | 14-day time-series for charts |
| `POST` | `/api/v1/evaluate-outcomes` | API Key | Trigger PO outcome evaluation |
| `POST` | `/api/v1/run-weekly` | API Key | Trigger weekly reflection + digest |
| `GET` | `/health` | None | Health check with region, provider, model |

### Shopify Webhooks

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/v1/webhooks/inventory_levels_update` | HMAC | Single variant sync on stock change |
| `POST` | `/api/v1/webhooks/orders_create` | HMAC | Sales history update on new order |
| `POST` | `/api/v1/webhooks/products_update` | HMAC | Product/variant upsert on update |

---

## Quick Start

### Prerequisites

- Docker & Docker Compose
- An LLM API key (Groq recommended — fastest inference)

### Setup (10 minutes)

```bash
# 1. Clone and configure
git clone <your-repo>
cd inventory-agent
cp .env.example .env

# 2. Set your LLM API key in .env (any one):
#    GROQ_API_KEY=gsk_...
#    OPENAI_API_KEY=sk-...
#    GOOGLE_API_KEY=AIza...

# 3. Start everything
docker compose up -d --build

# 4. Run database migrations
docker compose exec inventory-agent alembic upgrade head

# 5. Seed demo data
docker compose exec inventory-agent python seed_demo_data.py

# 6. Verify it works
curl http://localhost:8002/health

# 7. Run the full pipeline
curl -X POST http://localhost:8002/api/v1/run-sync \
  -H "X-API-Key: demo-key-2024"
```

**Swagger UI**: [http://localhost:8002/docs](http://localhost:8002/docs)

### Docker Compose Profiles

| Profile | Command | What It Starts |
|---------|---------|----------------|
| **Development** | `docker compose up -d --build` | FastAPI + PostgreSQL with hot-reload |
| **Production** | `docker compose -f docker-compose.prod.yml up -d --build` | FastAPI + PostgreSQL + Caddy (TLS) + backups |

---

## Configuration

### Essential

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GROQ_API_KEY` | One of | — | Groq API key (fastest, recommended) |
| `OPENAI_API_KEY` | One of | — | OpenAI API key |
| `GOOGLE_API_KEY` | One of | — | Google Gemini API key |
| `LLM_PROVIDER` | No | `openai` | Choose: `openai`, `groq`, `gemini` |
| `DATABASE_URL` | Yes | `postgresql+asyncpg://inventory:inventory@localhost:5432/inventory_agent` | Primary database |

### Shopify

| Variable | Required (Production) | Default | Description |
|----------|----------------------|---------|-------------|
| `SHOPIFY_STORE_DOMAIN` | Yes | — | Your store domain (e.g., `my-store.myshopify.com`) |
| `SHOPIFY_ADMIN_API_TOKEN` | Yes | — | Shopify Admin API access token |
| `SHOPIFY_WEBHOOK_SECRET` | No | — | HMAC secret for webhook verification |

### Auth & Security

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_API_KEY` | `demo-key-2024` | Master API key for dev auth |
| `ALLOW_DEMO_KEY` | `true` (auto-disabled in production) | Accept demo key |
| `PUBLIC_API_URL` | `http://localhost:8002` | Public URL for signed approval links |

### Enterprise

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_READ_URL` | — | Read-replica connection for analytics queries |
| `CHECKPOINTER_DATABASE_URL` | (derived from DATABASE_URL) | Dedicated DB for LangGraph checkpoints (required in production) |
| `DEPLOYMENT_REGION` | `local` | Region label for health endpoint |
| `AUDIT_S3_BUCKET` | — | S3 bucket for nightly audit log export |
| `AUDIT_S3_REGION` | `us-east-1` | S3 region |
| `AUDIT_S3_ACCESS_KEY` | — | S3 access key |
| `AUDIT_S3_SECRET_KEY` | — | S3 secret key |
| `SYNC_DAYS` | `30` | Days of sales history to sync from Shopify |
| `SLACK_WEBHOOK_URL` | — | Slack webhook for pipeline notifications |

### LLM Tuning

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL_NAME` | `gemini-2.0-flash` | LLM model |
| `DAILY_LLM_SPEND_CAP` | `5` | Daily LLM cost cap in USD |
| `TEMPERATURE` | `0.3` | LLM temperature |
| `MAX_TOKENS` | `1024` | Max LLM output tokens |

---

## Production Deployment

```bash
DOMAIN=inventory.yourcompany.com docker compose -f docker-compose.prod.yml up -d --build
```

Architecture: `Browser — HTTPS → Caddy (auto TLS) → FastAPI (internal :8002)`

Caddy terminates TLS with automatic Let's Encrypt certificates. FastAPI serves both the API and the built React frontend. A dedicated backup service runs daily `pg_dump` with 30-day retention.

### Production Checklist

- [ ] Set `ENVIRONMENT=production`
- [ ] Configure `SHOPIFY_STORE_DOMAIN` and `SHOPIFY_ADMIN_API_TOKEN`
- [ ] Set `PUBLIC_API_URL` to your public domain
- [ ] Configure `CHECKPOINTER_DATABASE_URL` as a separate database from `DATABASE_URL`
- [ ] Set a strong `AGENT_API_KEY`
- [ ] Configure `SLACK_WEBHOOK_URL` for pipeline notifications
- [ ] Set `SHOPIFY_WEBHOOK_SECRET` for webhook verification
- [ ] Configure `DOMAIN` for automatic TLS and HSTS
- [ ] (Optional) Set `DATABASE_READ_URL` for read-replica offloading
- [ ] (Optional) Configure `AUDIT_S3_*` for compliance-grade audit logging

---

## Frontend

A React dashboard ships with the agent:

```bash
cd inventory-frontend
npm ci
npm run dev    # → http://localhost:5173 (proxies /api → localhost:8002)
```

**Pages**: Dashboard, Inventory (SKU view), Purchase Orders (approve/reject), Analytics (charts/metrics), Settings

In production, the built frontend is served directly by FastAPI (no separate frontend server needed).

---

## Testing

```bash
# All tests
pytest tests/ -v

# Integration tests only (requires Postgres + Alembic migrations)
pytest tests/test_integration.py -v

# ML forecast accuracy evaluation
pytest tests/eval_suite.py -v

# Unit tests (no external deps)
pytest tests/ -v --ignore=tests/test_integration.py

# CI runs: lint → migrations → backend tests → eval suite → frontend build → Docker
```

---

## CI/CD Pipeline

Every push to `main`:

1. **Lint**: `ruff check .` (Python style enforcement)
2. **Test**: pytest with Postgres service container (Alembic migrations run first)
3. **Evaluate**: Forecast accuracy eval suite
4. **Build**: React frontend production build
5. **Package**: Multi-stage Docker image → GitHub Container Registry (`ghcr.io`)

---

## Roadmap

> _Features planned for future releases. Priorities shift based on client demand._

| Area | Upcoming |
|------|----------|
| **LLM** | Multi-model ensemble forecasting, anomaly detection via LLM |
| **Integrations** | Amazon SP-API, QuickBooks/Xero sync, email-based approvals |
| **Platform** | Multi-region active-active deployment, Redis cache backend, Celery/ARQ for distributed task processing |
| **Analytics** | Interactive dashboard with drill-down, exportable reports, anomaly timeline |
| **ML** | Prophet/NeuralProphet forecast models, automated model selection, A/B forecast comparison |
| **Compliance** | SOC 2 audit support, data retention policies, PII classification |

---

<p align="center">
  <strong>Inventory Agent</strong> — built for merchants who need intelligent, autonomous inventory management without the overhead of traditional ERP.
</p>
