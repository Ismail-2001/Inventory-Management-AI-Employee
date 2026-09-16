# Ops Dashboard - Quick Reference

## Service Health

| Service | URL | Health Check |
|---------|-----|--------------|
| API | http://localhost:8002 | `curl -s localhost:8002/health` |
| Prometheus | http://localhost:9090 | `curl -s localhost:9090/-/healthy` |
| Alertmanager | http://localhost:9093 | `curl -s localhost:9093/-/healthy` |
| Grafana (if enabled) | http://localhost:3000 | `curl -s localhost:3000/api/health` |

## Key Metrics to Watch

```bash
# Request rate and latency
curl -s localhost:8002/metrics | grep http_requests_total
curl -s localhost:8002/metrics | grep http_request_duration_seconds

# Database connections
curl -s localhost:8002/metrics | grep db_connection_pool

# Task queue depth
curl -s localhost:8002/metrics | grep task_queue_depth

# Error rate
curl -s localhost:8002/metrics | grep http_requests_total{status=~"5.."}
```

## Alert Thresholds

| Alert | Threshold | Action |
|-------|-----------|--------|
| HighErrorRate | >5% 5xx | Check logs, restart if needed |
| HighRequestLatency | P95 >5s | Check DB, slow queries |
| ConnectionPoolExhaustion | >=15 conns | Restart API, investigate |
| TaskQueueBacklog | >10 queued | Check worker, restart |

## Quick Commands

```bash
# Check all services
docker compose ps

# View recent logs
docker compose logs --tail=50 inventory-agent

# Restart API
docker compose restart inventory-agent

# Check database size
docker compose exec postgres psql -U inventory -d inventory_agent -c "SELECT pg_size_pretty(pg_database_size('inventory_agent'));"

# Check slow queries
docker compose exec postgres psql -U inventory -d inventory_agent -c "SELECT pid, now()-query_start AS dur, query FROM pg_stat_activity WHERE state='active' ORDER BY dur DESC LIMIT 5;"
```

## Disk Space

```bash
# Check backup volume
docker compose exec backup sh -c 'df -h /backups'

# Check disk usage
df -h /var/lib/docker
```

## Backup Status

```bash
# List backups
ls -lh backups/

# Check backup age
ls -lt backups/ | head -5
```
