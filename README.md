# Inventory Agent — AI-Powered Inventory Management

An autonomous LangGraph pipeline that syncs inventory from Shopify (or seeded demo data), forecasts demand, identifies stockout risks, drafts purchase orders, and notifies stakeholders — all driven by LLM reasoning (Groq, OpenAI, or Gemini).

## Quick Start

```bash
# Prerequisites: Docker, Docker Compose
cp .env.example .env
# Edit .env: set GROQ_API_KEY (or OPENAI_API_KEY / GOOGLE_API_KEY)

docker compose up -d --build
docker compose exec inventory-agent alembic upgrade head
docker compose exec inventory-agent python seed_demo_data.py

curl http://localhost:8002/health
curl -X POST http://localhost:8002/api/v1/run-sync \
  -H "X-API-Key: demo-key-2024"
```

Swagger UI: [http://localhost:8002/docs](http://localhost:8002/docs)

## Architecture

```
┌──────────┐   ┌─────────┐   ┌─────────┐   ┌──────────┐   ┌───────────┐   ┌──────────────┐
│  Sync    │──▶│ Forecast│──▶│  Risk   │──▶│ PO Draft│──▶│ Reflection│──▶│ Notify (Slack)│
│(Shopify/ │   │(Stats + │   │(Stockout│   │(LLM     │   │(LLM      │   │ (webhook)    │
│  DB)     │   │  Sales) │   │  Rules) │   │  Reason)│   │  Review) │   │              │
└──────────┘   └─────────┘   └─────────┘   └──────────┘   └───────────┘   └──────────────┘
```

| Node | Function |
|------|----------|
| **sync** | Pulls products/sales from Shopify or reads seeded SKUs from DB |
| **forecast** | Exponential smoothing on 90-day sales history |
| **risk** | Flags SKUs as `critical` / `warning` based on days-of-stock vs lead time |
| **po_draft** | Calculates reorder quantity, generates LLM-powered reasoning |
| **reflection** | LLM reviews the batch of POs for consistency |
| **notify** | Sends pending/confirmed summaries to Slack webhook |

## API

| Method | Path | Auth | Rate Limit | Description |
|--------|------|------|-----------|-------------|
| `POST` | `/api/v1/run-sync` | `X-API-Key` | 5/min | Run the full pipeline |
| `GET` | `/api/v1/po` | `X-API-Key` | — | List purchase orders |
| `POST` | `/api/v1/po/{id}/approve` | `X-API-Key` + role | 5/min | Approve a PO |
| `POST` | `/api/v1/po/{id}/reject` | `X-API-Key` + role | 5/min | Reject a PO |
| `GET` | `/api/v1/po/action` | signed token | — | Approve/reject via email link |
| `GET` | `/health` | none | — | Health check |

## Production Deploy

```bash
# 1. Build frontend
cd inventory-frontend && npm ci && npm run build && cd ..

# 2. Deploy with Caddy reverse proxy + auto HTTPS
DOMAIN=inventory.example.com docker compose -f docker-compose.prod.yml up -d --build
```

Architecture: `Browser —HTTPS→ Caddy (80/443) —→ FastAPI (8002, internal)`.
Caddy terminates TLS with automatic Let's Encrypt certificates. FastAPI serves both the API routes and the frontend static files (mounted at startup from `inventory-frontend/dist/`).

### Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GROQ_API_KEY` | one of | — | Groq API key |
| `OPENAI_API_KEY` | one of | — | OpenAI API key |
| `GOOGLE_API_KEY` | one of | — | Google Gemini API key |
| `LLM_PROVIDER` | no | `groq` | Provider to use |
| `DATABASE_URL` | yes | — | PostgreSQL connection string |
| `AGENT_API_KEY` | yes | `demo-key-2024` | API key for auth |
| `ENVIRONMENT` | no | `development` | `development` or `production` |
| `ENABLE_SCHEDULER` | no | `false` | Enable daily/weekly background jobs |
| `DOMAIN` | no | — | Domain for Caddy auto HTTPS |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | no | — | OpenTelemetry gRPC endpoint |
| `BACKUP_INTERVAL` | no | `86400` | DB backup interval (seconds) |
| `BACKUP_RETENTION` | no | `30` | Days to retain backups |

### Full Pipeline

```bash
ENVIRONMENT=production docker compose -f docker-compose.prod.yml up -d --build
```

This starts:
- **PostgreSQL 16** — database
- **Inventory Agent** — FastAPI + LangGraph pipeline
- **Caddy** — reverse proxy with auto HTTPS
- **Backup** — daily pg_dump with 30-day retention

## Frontend

```bash
cd inventory-frontend
npm ci
npm run dev    # → http://localhost:5173 (proxies /api → localhost:8002)
```

In production, the built frontend is served directly by FastAPI (no separate frontend server needed).

## LLM Support

- **Groq** (default): `llama-3.1-8b-instant`, `llama-3.3-70b-versatile`
- **OpenAI**: `gpt-4o-mini`, `gpt-4o`
- **Gemini**: `gemini-2.0-flash`

Set `LLM_PROVIDER`, `MODEL_NAME`, and the corresponding `*_API_KEY` in `.env`.

## Development

```bash
pip install -r requirements.txt
alembic upgrade head
uvicorn api.main:app --reload --port 8002
```

Tests: `pytest tests/ -v`

## CI/CD

On every push to `main`:
1. `ruff check .` — Python linting
2. `pytest tests/ -v` — Backend tests (with Postgres service)
3. `npm run build` — Frontend build
4. `docker build && docker push` — Multi-stage image to GitHub Container Registry

## Data Safety

Automatic daily PostgreSQL backups via the `backup` service (enabled in production compose).
Backups stored in a named Docker volume with 30-day retention.
Restore: `scripts/restore-db.sh <backup-file>`.
