# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
