# Contributing to Inventory Agent

## Quick start

```bash
git clone https://github.com/Ismail-2001/Inventory-Management-AI-Employee.git
cd Inventory-Management-AI-Employee
cp .env.example .env
docker compose up -d --build
docker compose exec inventory-agent alembic upgrade head
docker compose exec inventory-agent python seed_demo_data.py
```

## Branching model

All changes go through a **pull request** targeting `main`. Direct pushes to `main`
are blocked by branch protection.

```bash
git checkout -b feature/my-change
# ... make changes ...
git add -A && git commit -m "feat: short description"
git push origin feature/my-change
# Open a PR on GitHub
```

### Commit messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

| Prefix | When |
|--------|------|
| `feat:` | New feature |
| `fix:` | Bug fix |
| `chore:` | Maintenance, deps, CI |
| `docs:` | Documentation only |
| `refactor:` | Code restructuring without behavior change |
| `test:` | Adding or updating tests |

## Running checks locally

```bash
# Lint + format
ruff check . --target-version py312
ruff format --check .

# Type check (matches CI scope)
mypy agent api shared

# Backend tests (unit — no Postgres required)
pytest tests/ -v --ignore=tests/test_integration.py

# Frontend tests
cd inventory-frontend && npm ci && npm test
```

All four must pass before a PR will be approved.

## Architecture overview

See [docs/RUNBOOK.md](docs/RUNBOOK.md) for production topology and on-call
procedures. The key paths:

- `agent/` — LangGraph nodes, config, DB, auth
- `api/` — FastAPI routes, rate limiting, middleware
- `shared/` — Cache, metrics, task queue, LLM client
- `inventory-frontend/` — React 19 dashboard (Vitest + Playwright)
- `load/` — k6 load tests
- `prometheus/` — Alerting rules and Alertmanager config
