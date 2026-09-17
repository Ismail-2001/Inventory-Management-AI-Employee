# Production Deployment Guide

## Prerequisites

- Docker Desktop running
- Domain configured (e.g., `inventory.yourcompany.com`)
- SSL certificate (via Let's Encrypt or cloud provider)
- Environment variables configured in `.env.production`

## Quick Deploy

### 1. Set up environment

```bash
# Copy and edit production env
cp .env.example .env.production
# Edit .env.production with production values
```

### 2. Deploy with Docker Compose

```bash
# Deploy (production layer)
DOMAIN=inventory.yourcompany.com \
  docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

### 3. Verify deployment

```bash
# Check all services
docker compose ps

# Check API health
curl -s https://inventory.yourcompany.com/health

# Check monitoring
curl -s http://localhost:9090/-/healthy
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DOMAIN` | Yes | Production domain |
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `CHECKPOINTER_DATABASE_URL` | Yes | Separate DB for LangGraph |
| `AGENT_API_KEY` | Yes | API key (NOT default) |
| `SHOPIFY_STORE_DOMAIN` | Yes | Shopify store domain |
| `SHOPIFY_ADMIN_API_TOKEN` | Yes | Shopify API token |
| `SENTRY_DSN` | No | Sentry error tracking |
| `SLACK_WEBHOOK_URL` | No | Slack alert notifications |

## SSL/TLS Setup

### Option 1: Cloudflare (Recommended)
1. Point domain to server IP
2. Enable Cloudflare proxy
3. SSL mode: Full (Strict)

### Option 2: Let's Encrypt
```bash
# Install certbot
sudo apt install certbot

# Get certificate
sudo certbot certonly --standalone -d inventory.yourcompany.com

# Update docker-compose.prod.yml with certificate paths
```

## Monitoring Setup

### Prometheus
- URL: `http://localhost:9090`
- Targets: API, Postgres, Redis exporters
- Alert rules: `prometheus/rules.yml`

### Alertmanager
- URL: `http://localhost:9093`
- Slack integration: Configure `prometheus/alertmanager.yml`

### Sentry (Optional)
1. Create account at sentry.io
2. Get DSN
3. Add to `.env.production`:
   ```
   SENTRY_DSN=https://xxx@sentry.io/xxx
   ```

## Backup Strategy

### Automated Backups
```bash
# Run backup drill
./scripts/ops/backup-drill.sh backup

# Schedule nightly backups (cron)
0 2 * * * /path/to/scripts/ops/backup-drill.sh backup
```

### Restore
```bash
# Restore from backup
./scripts/ops/backup-drill.sh restore
```

## Scaling

### Horizontal Scaling
```bash
# Scale API instances
docker compose up -d --scale inventory-agent=3
```

### Database Scaling
- Use managed PostgreSQL (AWS RDS, Google Cloud SQL)
- Read replicas for read-heavy workloads

## Troubleshooting

### Container won't start
```bash
docker compose logs inventory-agent
```

### Database connection refused
```bash
docker compose exec postgres psql -U inventory -d inventory_agent
```

### High memory usage
```bash
docker stats
docker compose restart inventory-agent
```

## Rollback

```bash
# Check current version
curl -s https://inventory.yourcompany.com/health | jq .version

# Rollback to previous version
IMAGE_TAG=v0.9.0 docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# If migrations ran, downgrade DB first
docker compose run --rm migrate alembic downgrade -1
```

## Support

- Runbook: `docs/RUNBOOK.md`
- Ops Dashboard: `docs/OPS-DASHBOARD.md`
- Contributing: `CONTRIBUTING.md`
