"""TTL cache with memory backend. Swap to Redis by replacing get/set methods.

Usage:
    cache = TTLCache(ttl_seconds=300)
    await cache.set("key", value)
    value = await cache.get("key")
"""
import time
from typing import Any


class TTLCache:
    def __init__(self, ttl_seconds: int = 3600):
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[float, Any]] = {}

    async def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.time() > expires_at:
            del self._store[key]
            return None
        return value

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        expires_at = time.time() + (ttl if ttl is not None else self._ttl)
        self._store[key] = (expires_at, value)

    async def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    async def clear(self) -> None:
        self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)


forecast_cache = TTLCache(ttl_seconds=600)
