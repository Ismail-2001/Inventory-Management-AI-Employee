# Inventory Agent

**AI Employee #2** — An autonomous, human-in-the-loop inventory management agent for ecommerce businesses. Syncs inventory from Shopify, forecasts demand, detects risks, drafts purchase orders, and notifies stakeholders — all with full observability and audit trail.

## Features

| Capability | Description |
|---|---|
| **Shopify Sync** | Pulls products, orders, and inventory levels via GraphQL |
| **Demand Forecasting** | Statistical exponential smoothing for 30/60/90-day projections |
| **Risk Detection** | Identifies stockout, overstock, and dead-stock risks per SKU |
| **AI Purchase Orders** | LLM-generated PO drafts with quantity, cost, and reasoning |
| **Human Approval** | One-click approve/reject via Slack with HMAC-signed links |
| **Outcome Tracking** | Evaluates PO accuracy post-fulfillment with acceptance rates |
| **Weekly Reflection** | LLM aggregates metrics and generates actionable insights |
| **Slack Notifications** | Real-time alerts for risks, POs pending approval, and digests |
| **Role-Based Access** | API key auth with scoped roles (admin, viewer, approver) |
| **Audit Log** | Append-only immutable log of every state change |
| **OpenTelemetry** | Distributed tracing across all agent nodes |
| **Dashboard UI** | React frontend with real-time metrics, PO management, and charts |

## Architecture

```
                  ┌─────────────┐
                  │   Shopify   │
                  └──────┬──────┘
                         │ GraphQL
                         ▼
    ┌─────────────────────────────────────────┐
    │          LangGraph Agent Flow           │
    │                                         │
    │  Sync ──► Forecast ──► Risk ──► PO ──► Notify
    │                              │
    │                      Human Approval
    │                     (interrupt_after)
    └─────────────────────────────────────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │     PostgreSQL      │
              │  (state + history)  │
              └─────────────────────┘
```

## Tech Stack

| Layer | Technology |
|---|---|
| **Runtime** | Python 3.12 / FastAPI |
| **Orchestration** | LangGraph (state graph + Postgres checkpointer) |
| **Database** | PostgreSQL 16 (SQLAlchemy async + asyncpg) |
| **LLM** | Gemini / OpenAI (configurable via provider) |
| **Frontend** | React 19 + TypeScript 6 + Vite 8 + Tailwind CSS 4 |
| **Migrations** | Alembic |
| **Notifications** | Slack webhooks |
| **Observability** | OpenTelemetry (console + OTLP export) |
| **Scheduling** | APScheduler (daily eval + weekly report) |
| **Auth** | HMAC-signed tokens + API key with bcrypt |
| **Testing** | pytest (asyncio) + eval suite with MAPE gate |

## Quick Start

### Prerequisites

- Docker & Docker Compose (recommended) OR Python 3.12+ locally
- A Shopify dev store with admin API access
- A Gemini API key (or OpenAI key)
- A Slack webhook URL (for notifications)

### Setup

```bash
git clone https://github.com/Ismail-2001/inventory-agent.git
cd inventory-agent
cp .env.example .env
```

Edit `.env` with your credentials:

```env
SHOPIFY_STORE_DOMAIN=your-store.myshopify.com
SHOPIFY_ADMIN_API_TOKEN=shpat_xxxx
GOOGLE_API_KEY=AIza...
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

### Run with Docker

```bash
docker compose up -d
```

This starts the API server on `http://localhost:8002` and PostgreSQL on `5432`.

### Run Locally (without Docker)

```bash
pip install -r requirements.txt
alembic upgrade head
uvicorn api.main:app --reload --port 8002
```

### Run Frontend

```bash
cd inventory-frontend
npm install
npm run dev
```

Opens the dashboard at `http://localhost:5173`.

## API Endpoints

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | — | Health check |
| `POST` | `/api/v1/run-sync` | API key | Trigger full sync + forecast + risk + PO flow |
| `GET` | `/api/v1/po` | API key | List purchase orders |
| `POST` | `/api/v1/po/{id}/approve` | API key | Approve a PO (optionally edit quantity) |
| `POST` | `/api/v1/po/{id}/reject` | API key | Reject a PO with reason |
| `GET` | `/api/v1/po/action?token=` | Signed | One-click approve/reject from Slack |
| `GET` | `/api/v1/metrics?days=30` | API key | PO acceptance and forecast error metrics |
| `POST` | `/api/v1/evaluate-outcomes` | API key | Evaluate pending PO outcomes |
| `POST` | `/api/v1/run-weekly` | API key | Generate weekly reflection report |
| `POST` | `/webhooks/shopify` | HMAC | Receive Shopify inventory/webhook events |
| `GET` | `/docs` | — | Swagger UI |
| `GET` | `/redoc` | — | ReDoc UI |

## Project Structure

```
├── agent/                  # Core agent logic
│   ├── nodes/              # LangGraph node implementations
│   │   ├── sync_node.py    # Shopify data sync
│   │   ├── forecast_node.py
│   │   ├── risk_node.py
│   │   ├── po_draft_node.py
│   │   ├── notify_node.py
│   │   ├── reflection_node.py
│   │   └── reporting_node.py
│   ├── graph.py            # LangGraph state machine definition
│   ├── shopify_sync.py     # Shopify GraphQL client
│   ├── forecast.py         # Exponential smoothing engine
│   ├── risk.py             # Risk classification rules
│   ├── ordering.py         # Reorder quantity formulas
│   ├── outcomes.py         # PO outcome evaluation
│   ├── metrics.py          # Acceptance rate & forecast error calculations
│   ├── scheduler.py        # APScheduler job definitions
│   ├── config.py           # Environment-based configuration
│   ├── models.py           # SQLAlchemy ORM models
│   ├── db.py               # Async database session
│   ├── auth.py             # RBAC and API key verification
│   ├── audit.py            # Append-only audit log
│   ├── signing.py          # HMAC token generation
│   ├── telemetry.py        # OpenTelemetry tracing
│   └── webhooks.py         # Shopify webhook HMAC verification
├── api/                    # FastAPI server
│   ├── main.py             # App entry point, CORS, error handlers
│   └── routes/             # Route handlers
│       ├── run_sync.py
│       ├── purchase_orders.py
│       ├── webhooks.py
│       └── operations.py
├── alembic/                # Database migrations
│   └── versions/
│       ├── 001_initial_schema.py
│       ├── 002_suppliers_and_purchase_orders.py
│       └── 003_phase3_tables.py
├── inventory-frontend/     # React dashboard
│   └── src/
│       ├── pages/          # Dashboard, Inventory, POs, Analytics, Settings
│       ├── components/     # Layout, shared components
│       └── lib/            # API client, utilities
├── tests/                  # Test suite
│   ├── test_forecast.py
│   ├── test_risk.py
│   ├── test_ordering.py
│   ├── test_signing.py
│   ├── test_agent.py
│   └── eval_suite.py       # 28-case regression suite with MAPE gate
├── Dockerfile
├── docker-compose.yml
└── Makefile
```

## Testing

```bash
# Run unit tests
pytest tests/ -v

# Run forecast accuracy regression suite
python -m pytest tests/eval_suite.py -v
```

The eval suite includes 28 test cases with a 30% MAPE threshold — deploys will fail if forecast accuracy degrades beyond this gate.

## Configuration

All configuration is via environment variables (see `.env.example`). Key settings:

| Variable | Required | Default | Description |
|---|---|---|---|
| `SHOPIFY_STORE_DOMAIN` | Yes | — | Your Shopify store domain |
| `SHOPIFY_ADMIN_API_TOKEN` | Yes | — | Shopify admin API token |
| `DATABASE_URL` | No | `postgresql+asyncpg://...` | Async Postgres connection string |
| `LLM_PROVIDER` | No | `openai` | `openai` or `google` |
| `OPENAI_API_KEY` | Varies | — | OpenAI API key |
| `GOOGLE_API_KEY` | Varies | — | Google AI API key |
| `AGENT_API_KEY` | No | `demo-key-2024` | API key for endpoint auth |
| `SLACK_WEBHOOK_URL` | No | — | Slack incoming webhook |
| `SHOPIFY_WEBHOOK_SECRET` | No | — | Shopify app shared secret |

## License

Proprietary — All rights reserved.
