"""TTL cache — Redis-backed when REDIS_URL is set, in-memory otherwise.

Usage:
    cache = TTLCache(ttl_seconds=300, max_size=1000)
    await cache.set("key", value)
    value = await cache.get("key")
"""
import time
from collections import OrderedDict
from typing import Any

from agent.config import settings


class TTLCache:
    def __init__(self, ttl_seconds: int = 3600, max_size: int = 1000):
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._store: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    async def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.time() > expires_at:
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return value

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        expires_at = time.time() + (ttl if ttl is not None else self._ttl)
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (expires_at, value)
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)

    async def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    async def clear(self) -> None:
        self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)


def _create_forecast_cache():
    if settings.redis_url:
        try:
            from shared.redis_cache import RedisCache
            return RedisCache(namespace="forecast", ttl_seconds=600)
        except Exception:
            pass
    return TTLCache(ttl_seconds=600)


forecast_cache = _create_forecast_cache()
