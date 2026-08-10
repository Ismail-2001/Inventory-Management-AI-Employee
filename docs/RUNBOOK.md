# Inventory Agent — On-Call Runbook

This runbook covers how to detect, diagnose, and recover from production incidents
for the Inventory Agent service. It is written for the on-call engineer with no
prior knowledge of the codebase.

## 0. Releases, Rollback & Backups

### 0.1 How releases are versioned

The project uses [Semantic Versioning](https://semver.org). Every release is a git
tag (`v1.0.0`, `v1.1.0`, ...) and a matching container image tag pushed to GHCR
(`ghcr.io/inventory-agent/inventory-agent:<tag>`). See `CHANGELOG.md` for what
changed in each release. The version exposed by `GET /health` comes from
`agent/__init__.py` (`__version__`).

### 0.2 Deploying a release

```bash
# Pull and run a pinned image tag (never `latest` for prod rollbacks)
IMAGE_TAG=v1.0.0 DOMAIN=inventory.yourcompany.com \
  docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --pull always
```

### 0.3 Rolling back

A rollback is a versioned redeploy. Because `migrate` runs `alembic upgrade head`
on startup, **a downgrade requires a matching DB downgrade first**:

1. Check the current DB revision:
   ```bash
   docker compose exec postgres psql -U inventory -d inventory_agent -c "SELECT * FROM alembic_version;"
   ```
2. If the bad release **did not** run migrations, just redeploy the previous tag:
   ```bash
   IMAGE_TAG=v0.9.0 DOMAIN=inventory.yourcompany.com \
     docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --pull always
   ```
3. If it **did** run migrations, downgrade the DB **before** starting the old image:
   ```bash
   docker compose run --rm migrate alembic downgrade -1
   IMAGE_TAG=v0.9.0 DOMAIN=inventory.yourcompany.com \
     docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --pull always
   ```
4. Verify: `curl -sf https://inventory.yourcompany.com/health` returns the old version.

### 0.4 Backups & restore

The `backup` compose service dumps Postgres nightly (custom format, gzip) into the
`backups` volume and prunes files older than `BACKUP_RETENTION` days. On-call must
periodically **verify backups restore successfully** — a backup that never restores
is not a backup.

Restore drill (destructive — do this on a scratch DB first):

```bash
# List backups
docker compose exec backup sh -c 'ls -la /backups'

# Restore a dump into a scratch database
docker compose exec postgres psql -U inventory -d inventory_agent_restore \
  -c "SELECT 1" # ensure scratch DB exists
docker compose exec backup sh -c \
  'PGPASSWORD=$POSTGRES_PASSWORD pg_restore -h postgres -U $POSTGRES_USER \
   -d inventory_agent_restore --clean --if-exists /backups/inventory-agent-<TIMESTAMP>.dump'

# Verify row counts match the primary database
docker compose exec postgres psql -U inventory -d inventory_agent_restore \
  -c "SELECT (SELECT count(*) FROM skus) AS skus, (SELECT count(*) FROM purchase_orders) AS pos;"
```

Standalone scripted backup/restore (uses `DATABASE_URL` from the environment):

```bash
scripts/backup-db.sh          # writes ./backups/inventory-agent-<ts>.sql.gz
scripts/restore-db.sh ./backups/inventory-agent-<ts>.sql.gz
```

## 1. Service Overview & Topology

| Component | Container | Port | Purpose |
|---|---|---|---|
| API + Agent | `inventory-agent` | 8002 | FastAPI app, LangGraph pipeline, `/metrics` |
| PostgreSQL | `postgres` | 5432 | Primary data store (SKUs, POs, forecasts, audit) |
| Redis | `redis` | 6379 | Cache for forecasts, tier lookups, rate limiting |
| Checkpointer DB | `postgres` | 5432 | LangGraph checkpoint/thread state tables |
| Prometheus | `prometheus` | 9090 | Metrics scraping + alerting |
| Alertmanager | `alertmanager` | 9093 | Routes alerts to Slack |
| postgres-exporter | `postgres-exporter` | 9187 | Postgres metrics for Prometheus |
| redis-exporter | `redis-exporter` | 9121 | Redis metrics for Prometheus |

## 2. First Things First (Triage)

1. Check overall status:
   ```bash
   docker compose ps
   docker compose logs --tail=200 inventory-agent
   ```
2. Check the health endpoint:
   ```bash
   curl -s http://localhost:8002/health
   ```
   The response reports `status`, `database`, `redis`, and `sso` fields. If
   `status` is `degraded`, a dependency is down.
3. Check Prometheus alerts (if deployed):
   ```bash
   curl -s http://localhost:9090/api/v1/alerts
   ```
4. Check metrics directly:
   ```bash
   curl -s http://localhost:8002/metrics | grep -E "db_connection_pool|in_flight_requests|task_queue_depth|http_requests_total"
   ```

## 3. Alert Reference

| Alert | Severity | Meaning | First Action |
|---|---|---|---|
| `InventoryAgentDown` | critical | API unreachable 2m | Restart container, check logs |
| `HighErrorRate` / `ElevatedErrorRate` | warning / critical | >5% / >20% 5xx | Inspect logs for stack traces |
| `HighRequestLatency` | warning | P95 latency > 5s | Check DB load, slow queries |
| `ConnectionPoolExhaustion` | warning | >= 15 conns checked out | Restart agent, investigate slow queries |
| `TaskQueueBacklog` | warning | >10 queued runs | Check worker, DB saturation |
| `HighInflightRequests` | warning | >100 concurrent | Check for runaway clients / DDoS |
| `PostgreSQLDown` / `RedisDown` | critical | Exporter unreachable | Check dependency container |

## 4. Runbooks by Scenario

### 4.1 API container is down or crash-looping

**Symptoms:** `InventoryAgentDown`, `docker compose ps` shows `Restarting`.

1. Check logs:
   ```bash
   docker compose logs --tail=300 inventory-agent
   ```
2. Common causes and fixes:
   - **DB unreachable during startup:** the lifespan handler calls
     `settings.validate_required()` and creates the checkpointer. If Postgres is
     still migrating, the container exits. Wait for `migrate` to complete, then
     `docker compose up -d --force-recreate inventory-agent`.
   - **OOM kill:** check `docker inspect` for `OOMKilled`. Raise the memory limit
     in `docker-compose.yml` (currently 1G) if sustained.
   - **Crash in `alembic upgrade head`:** see section 4.4.
3. Restart:
   ```bash
   docker compose up -d --force-recreate inventory-agent
   ```
4. Verify: `curl -s http://localhost:8002/health` returns `"status": "healthy"`.

### 4.2 High error rate / 5xx responses

**Symptoms:** `HighErrorRate` or `ElevatedErrorRate`.

1. Pull the failing requests with a correlation id:
   ```bash
   docker compose logs --tail=1000 inventory-agent | grep -iE "traceback|error|exception" | tail -50
   ```
2. `global_exception_handler` returns a generic 500; the real error is in the logs.
3. Common causes:
   - **Rate limit exceeded (429):** clients hitting `_get_tier_limit`. Check
     `X-RateLimit-*` headers. If legitimate load, raise the tier limit in
     `api/rate_limit.py`.
   - **Shopify API failure:** agent calls Shopify for sync. Check for
     `Shopify GraphQL error` in logs. May be temporary — retry `/run-sync`.
   - **DB query timeout:** statement_timeout is 30s. Slow queries log
     `Slow pool checkout`. See section 4.3.
4. If the cause is a code bug, hotfix, rebuild, redeploy:
   ```bash
   docker compose build inventory-agent && docker compose up -d inventory-agent
   ```

### 4.3 Database saturation / slow queries

**Symptoms:** `ConnectionPoolExhaustion`, `HighRequestLatency`, `Slow pool checkout` logs.

1. Check pool usage:
   ```bash
   curl -s http://localhost:8002/metrics | grep db_connection_pool
   ```
2. Find slow queries on Postgres:
   ```bash
   docker compose exec postgres psql -U inventory -d inventory_agent -c "SELECT pid, now()-query_start AS dur, state, query FROM pg_stat_activity WHERE state='active' ORDER BY dur DESC LIMIT 10;"
   ```
3. Because of `statement_timeout=30000`, any single statement longer than 30s is
   aborted automatically. Investigate queries consistently near that limit.
4. Remedies:
   - Add missing indexes (there are composite indexes on
     `purchase_orders`/`sales_history`/`risk_alerts` already).
   - Reduce page size on `/api/v1/po` (max 200) if clients page aggressively.
   - If the pool is exhausted, restart the API to reset connections:
     ```bash
     docker compose restart inventory-agent
     ```
5. Emergency connection kill if needed:
   ```bash
   docker compose exec postgres psql -U inventory -d inventory_agent -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state='active' AND now()-query_start > interval '30 seconds';"
   ```

### 4.4 Schema migrations fail

**Symptoms:** `migrate` service exits non-zero; `inventory-agent` never starts.

1. View migration logs:
   ```bash
   docker compose logs migrate
   ```
2. CI runs `alembic check` (schema drift). If a developer changed a model without
   a migration, `alembic upgrade head` fails.
3. Fix: generate the missing migration, then redeploy:
   ```bash
   docker compose run --rm migrate alembic revision --autogenerate -m "fix drift"
   docker compose up -d
   ```
4. If a migration is half-applied, check `alembic_version`:
   ```bash
   docker compose exec postgres psql -U inventory -d inventory_agent -c "SELECT * FROM alembic_version;"
   ```

### 4.5 Redis down

**Symptoms:** `RedisDown`; `/health` reports `"redis": "error"`; tier caching and
forecast caching fall back to in-process storage automatically.

1. The app degrades gracefully (see `shared/redis_cache.py` fallback). It is not
   usually a full outage.
2. Restart Redis:
   ```bash
   docker compose restart redis
   ```
3. Verify: `docker compose exec redis redis-cli ping` → `PONG`.

### 4.6 LLM provider outage

**Symptoms:** `run-sync`/`run-weekly` return errors; logs show
`Circuit breaker is open` or provider HTTP failures.

1. The system falls back to rule-based logic (`_template_insight`,
   deterministic forecasting) when the circuit breaker is open.
2. Check provider status (OpenAI / Gemini / Groq status pages).
3. The circuit breaker auto-resets after the configured cooldown. No manual
   action needed unless the outage is prolonged.
4. If all keys are invalid, check `.env`:
   ```bash
   grep -E "OPENAI_API_KEY|GOOGLE_API_KEY|GROQ_API_KEY" .env
   ```

### 4.7 Rate-limit flooding / abuse

**Symptoms:** `429` responses; high `http_requests_total{status="429"}`.

1. Identify the offending client from access logs (API key prefix, IP).
2. Rate limits are per-endpoint in `api/rate_limit.py`. Adjust tier limits there
   and redeploy if the client is legitimate.
3. If abuse, revoke the key:
   ```bash
   curl -X DELETE http://localhost:8002/api/v1/keys/<prefix> -H "X-API-Key: <admin-key>"
   ```

### 4.8 Background task queue backs up

**Symptoms:** `TaskQueueBacklog` (task_queue_depth > 10).

1. The queue is in-process and single-worker. Tasks run sequentially.
2. If a task is stuck, restart the API to clear it:
   ```bash
   docker compose restart inventory-agent
   ```
3. For sustained volume, move to ARQ/Celery+Redis (noted in
   `shared/task_queue.py`).

## 5. Daily / Post-Incident Checks

- `docker compose ps` — all services `Up` (healthy).
- `/health` — `"status": "healthy"`, `database: ok`, `redis: ok`.
- `curl -s http://localhost:8002/metrics` — no anomalous pool/inflight values.
- Prometheus targets page (http://localhost:9090/targets) — all `UP`.
- Recent audit log for unusual activity:
  ```bash
  curl -s "http://localhost:8002/api/v1/audit/logs?limit=20" -H "X-API-Key: <admin-key>"
  ```

## 6. Escalation Contacts

- P1/P2 (full or degraded availability): page the platform owner.
- P3 (minor, non-user-visible): open a GitHub issue; fix during business hours.
