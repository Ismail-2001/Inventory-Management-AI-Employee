# Chaos Testing

Fault-injection tests that prove the stack **degrades gracefully** when a
dependency is killed mid-request, and **recovers** without data corruption.

## Two layers

### 1. Deterministic unit-level chaos (`tests/test_chaos.py`)

Runs in CI with no infrastructure. Injects failures at the seam and asserts the
degradation contract:

| Injected fault | Asserted behavior |
|---|---|
| Redis connection dies | `RedisCache` reads/writes fall back to in-memory TTL; `health_check()` → `False`; auto-recovers when Redis returns |
| Redis down during forecast | `forecast_node` still produces forecasts (cache miss falls through to DB) |
| Redis down during rate limiting | slowapi `in_memory_fallback_enabled=True` → per-instance memory storage, no 500 storm |
| Postgres dies mid-run (async) | task queue records `{"error": ...}`, continues serving later tasks — no queue/event-loop corruption |
| Postgres dies mid-node | DB error propagates as a raised exception — never a silently truncated/corrupt result |

```bash
pytest tests/test_chaos.py -v
```

### 2. Live container chaos (`chaos/chaos_runner.py`)

Stops/restarts real Redis and Postgres containers while the docker-compose
stack is serving traffic. Requires the stack to be up first:

```bash
docker compose up -d --build

python chaos/chaos_runner.py --scenario redis      # kill Redis mid-request
python chaos/chaos_runner.py --scenario postgres   # drop Postgres mid-run
python chaos/chaos_runner.py --all                 # both
```

What it verifies:

- **Redis mid-request**: `/health` flips to degraded while Redis is down, but
  `/api/v1/config` and other routes keep serving (in-memory cache fallback).
  After `docker compose start redis`, health and traffic return to normal.
- **Postgres mid-pipeline-run**: an in-flight async sync run terminates in a
  clean HTTP 500 (missing DB dependency) instead of hanging or returning a
  misleading success. Once Postgres is restarted, health recovers and a fresh
  full run completes end-to-end (no corrupted or partial state).

## Adding a new chaos scenario

1. Add a deterministic test to `tests/test_chaos.py` that injects the failure
   at the code seam (monkeypatch / fake session) and asserts the degradation
   contract.
2. If the fault can be injected at the container level, add a
   `scenario_<name>()` function to `chaos/chaos_runner.py` that stops the
   dependency with `docker compose stop <svc>`, asserts graceful behavior, then
   restarts and asserts recovery.
