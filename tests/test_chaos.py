"""Chaos-engineering tests: verify graceful degradation when dependencies fail.

These are deterministic fault-injection tests that need no real Redis or
Postgres.  For live container-level chaos (killing Redis / disconnecting
Postgres mid-request against the docker-compose stack) see
``chaos/chaos_runner.py``.
"""

import asyncio
import types

import pytest

from shared.redis_cache import RedisCache
from shared.task_queue import BackgroundTaskQueue


class _DownRedis:
    """Redis client that raises on every call, simulating a killed connection."""

    def __init__(self, fail_times: int = -1) -> None:
        self.fail_times = fail_times
        self._store: dict[str, str] = {}
        self.closed = False

    async def get(self, key: str) -> str | None:
        self._maybe_fail()
        return self._store.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self._maybe_fail()
        self._store[key] = value

    async def delete(self, *keys: str) -> None:
        self._maybe_fail()
        for k in keys:
            self._store.pop(k, None)

    async def ping(self) -> bool:
        self._maybe_fail()
        return True

    async def aclose(self) -> None:
        self.closed = True

    def _maybe_fail(self) -> None:
        if self.fail_times != 0:
            if self.fail_times > 0:
                self.fail_times -= 1
            raise ConnectionError("redis: connection refused")


@pytest.mark.asyncio
async def test_redis_down_get_set_falls_back_to_memory(monkeypatch):
    down = _DownRedis()
    monkeypatch.setattr("shared.redis_cache._get_redis", lambda: down)

    cache = RedisCache(namespace="chaos", ttl_seconds=300)

    await cache.set("forecast:1", {"value": 42})
    assert await cache.get("forecast:1") == {"value": 42}

    assert await cache.get("forecast:missing") is None


@pytest.mark.asyncio
async def test_redis_down_health_check_reports_false(monkeypatch):
    down = _DownRedis()
    monkeypatch.setattr("shared.redis_cache._get_redis", lambda: down)

    cache = RedisCache(namespace="chaos", ttl_seconds=300)
    assert await cache.health_check() is False


@pytest.mark.asyncio
async def test_redis_recovers_automatically_after_transient_failure(monkeypatch):
    # Phase 1: Redis is fully down — reads/writes fall back to in-memory.
    down = _DownRedis(fail_times=-1)
    monkeypatch.setattr("shared.redis_cache._get_redis", lambda: down)

    cache = RedisCache(namespace="chaos", ttl_seconds=300)
    await cache.set("key-a", "first")
    assert await cache.get("key-a") == "first"

    # Phase 2: Redis returns — writes go to Redis again and are readable.
    healthy = _DownRedis(fail_times=0)
    monkeypatch.setattr("shared.redis_cache._get_redis", lambda: healthy)

    await cache.set("key-b", "second")
    assert await cache.get("key-b") == "second"


@pytest.mark.asyncio
async def test_forecast_node_survives_redis_outage(monkeypatch):
    """forecast_node must still produce forecasts when the cache's Redis dies."""
    down = _DownRedis()
    monkeypatch.setattr("shared.redis_cache._get_redis", lambda: down)

    cache = RedisCache(namespace="forecast", ttl_seconds=600)
    monkeypatch.setattr("shared.cache.forecast_cache", cache)

    from agent.nodes import forecast_node as fn

    calls: list[dict] = []

    async def fake_calculate_forecast(sku_id: int, current_stock: int, lead_time_days: int):
        calls.append({"sku_id": sku_id, "stock": current_stock, "lead": lead_time_days})
        return fn.ForecastResult(sku_id=sku_id, predicted_daily_demand=3.5, days_of_stock_remaining=4.0)

    monkeypatch.setattr(fn, "calculate_forecast", fake_calculate_forecast)

    state = {"skus": [{"id": 1, "current_stock": 10, "lead_time_days": 7}]}
    result = await fn.forecast_node(state)

    assert len(result["forecasts"]) == 1
    assert result["forecasts"][0]["predicted_daily_demand"] == 3.5
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_rate_limiter_configured_with_in_memory_fallback():
    """With Redis configured but down, slowapi falls back to per-instance memory."""
    from api.rate_limit import limiter

    assert getattr(limiter, "_in_memory_fallback_enabled", False) is True


@pytest.mark.asyncio
async def test_task_queue_records_db_error_and_continues():
    """If Postgres dies mid-run, the async path records an error and the queue
    keeps serving subsequent tasks (no corruption of the queue or event loop)."""

    class SelectiveGraph:
        async def ainvoke(self, state: dict, config: dict) -> dict:
            thread_id = (config.get("configurable") or {}).get("thread_id")
            if thread_id == "boom":
                raise ConnectionError("postgres: connection refused")
            return {"ok": True, **state}

    queue = BackgroundTaskQueue()
    app = types.SimpleNamespace(state=types.SimpleNamespace(graph=SelectiveGraph()))

    queue.start(app)  # type: ignore[arg-type]
    try:
        first = await queue.enqueue({"merchant_id": 0}, {"configurable": {"thread_id": "boom"}})
        second = await queue.enqueue({"merchant_id": 0}, {"configurable": {"thread_id": "fine"}})

        for _ in range(100):
            if queue.get_result(first) is not None and queue.get_result(second) is not None:
                break
            await asyncio.sleep(0.01)

        assert queue.get_result(first) == {"error": "Internal error processing task"}
        assert queue.get_result(second) == {"ok": True, "merchant_id": 0}
    finally:
        await queue.stop()


@pytest.mark.asyncio
async def test_pipeline_db_failure_propagates_no_corrupt_partial_state(monkeypatch):
    """A DB failure mid-pipeline surfaces as a raised error (never silently
    returns a truncated/corrupt state that could be mistaken for success)."""
    import sqlalchemy.exc

    from agent.nodes import forecast_node as fn

    class BrokenSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def execute(self, *args, **kwargs):
            raise sqlalchemy.exc.OperationalError("SELECT 1", {}, Exception("pg down"))

    def broken_factory():
        return BrokenSession()

    monkeypatch.setattr(fn, "async_session_factory", broken_factory)

    with pytest.raises(sqlalchemy.exc.OperationalError):
        await fn.calculate_forecast(sku_id=1, current_stock=10, lead_time_days=7)
