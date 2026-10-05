# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Natural-language chat agent: `POST /api/v1/chat` SSE endpoint with LangGraph tool-calling
  over live data, conversation history endpoints, and human-confirmed write actions
  (`/api/v1/chat/actions/{id}/confirm|cancel` that always create `pending_approval` POs).
- `/chat` frontend page with streaming responses, tool chips, and confirm/cancel action cards.
- `chat_messages` table (migration `017_chat_messages`) plus `CHAT_*` settings
  (`CHAT_MAX_STEPS`, `CHAT_MAX_INPUT_CHARS`, `CHAT_HISTORY_MESSAGES`, `CHAT_ACTION_TTL_MINUTES`).
- Tool-calling and streaming support in `shared/llm_client.py` (`call_with_tools`, `call_stream`)
  for OpenAI- and Gemini-compatible providers.
- Docs: `docs/CHAT-AGENT.md`.
- ROI & performance dashboard: `GET /api/v1/roi` aggregation endpoint (`agent/roi.py`) with
  date-range filters (`days=1-365` or inclusive `start`/`end`), covering value generated,
  LLM cost, ROI multiple, hours saved, stockouts avoided, excess avoided, PO acceptance +
  time-to-decision, ensemble-vs-baseline forecast accuracy, at-risk SKUs, forecast coverage /
  confidence distribution, and engine fallback rate. Settings `ROI_REVENUE_MULTIPLIER`
  (default 2.0) and `ROI_MANUAL_PO_MINUTES` (default 12) make the assumptions explicit.
- Dashboard rebuild: the default landing page is now the ROI dashboard with 7d/30d/90d/custom
  range filters, per-metric methodology popovers (`MetricHelp`), accuracy trend chart, and an
  on-page "How we calculate these numbers" panel. Methodology doc: `docs/ROI-DASHBOARD.md`.
- Per-merchant forecast engine promotion (`ensemble | exponential | shadow`) with a
  14-day holdout safety-gate evaluation, daily auto-promotion job, admin API
  (`/api/v1/forecast-engine`), Prometheus metrics and alerts, and
  `docs/FORECAST-ENGINE-RUNBOOK.md`.
- Rolling-origin backtest with velocity-tier breakdown
  (`scripts/forecast_backtest.py --folds`) and the promotion decision memo
  (`docs/FORECAST-PROMOTION-MEMO.md`).

### Changed
- Risk and PO Draft nodes consume forecast confidence bands: risk escalates on
  p90 days-of-cover, PO quantities plan against p90 demand (point forecast is
  kept when bands are absent or lower).
- Forecast engine defaults are measure-first: all tenants start on `shadow`
  (migration `016` + column default) and `FORECAST_ENGINE_DEFAULT` defaults to
  `shadow`; only the per-tenant promotion gates flip a tenant to `ensemble`.

## [1.0.0] - 2026-08-10

### Added
- Per-merchant tier-based rate limiting (`developer`/`business`/`enterprise`) with Redis-backed storage.
- `RATE_LIMIT_ENABLED` setting to disable rate limiting (used by the CI load test).
- Prometheus + Alertmanager monitoring stack wired into the production compose file, with the
  stack kept internal-only (no host port binding) in production.
- Composite database indexes for hot query paths (`purchase_orders`, `sales_history`, `risk_alerts`).
- SSO via OIDC (complete) and SAML 2.0 (tested at the protocol level).
- Audit trail with JSONL export and optional S3 archival.
- White-label branding per merchant.
- Background task queue with `run-sync-async` + `/api/v1/tasks/{id}` polling.
- Automated Postgres backup service in the production compose stack with configurable
  interval and retention (`BACKUP_INTERVAL`, `BACKUP_RETENTION`).

### Changed
- **Removed deprecated demo endpoints** `/api/v1/analyze`, `/api/v1/bulk`, and
  `/api/v1/forecast`. New integrations must use `POST /api/v1/run-sync` (synchronous)
  or `POST /api/v1/run-sync-async` (background). The k6 load test now exercises
  `run-sync-async` instead of the removed `/api/v1/analyze` endpoint.
- Production deployment now requires both compose files:
  `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`
  (the base file defines postgres, redis, and the monitoring stack).

### Security
- Hardened the Docker image: pip removed after install, non-root user, no-new-privileges,
  dropped capabilities, `stop_grace_period`, pinned transitive deps (msgpack, setuptools),
  upgraded `checkpoint`/`languagegraph` to patched versions.
- Trivy container scan gate in CI (unfixed severities ignored).

### Fixed
- k6 load test previously reported a false pass: the summary parser read k6 v1 metric
  paths, and `|| true` swallowed k6's real exit code. The workflow now parses k6 v2
  metrics and honors thresholds.
