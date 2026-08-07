"""Redis-backed TTL cache with automatic in-memory fallback.

If REDIS_URL is set and reachable, all operations go through Redis.
If Redis is unavailable at startup or fails at runtime, falls back to
the in-memory TTLCache transparently.
"""
import json
import logging
import time
from collections import OrderedDict
from typing import Any

from agent.config import settings

logger = logging.getLogger(__name__)

_redis_client = None
_redis_available = False


def _get_redis():
    global _redis_client, _redis_available
    if _redis_client is not None:
        return _redis_client
    if not settings.redis_url:
        return None
    try:
        import redis.asyncio as aioredis
        _redis_client = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        _redis_available = True
        logger.info("Redis cache connected: %s", settings.redis_url.split("@")[-1])
        return _redis_client
    except Exception as exc:
        logger.warning("Redis unavailable, using in-memory cache: %s", exc)
        _redis_available = False
        return None


class RedisCache:
    """TTL cache backed by Redis with in-memory fallback."""

    def __init__(self, namespace: str = "inventory", ttl_seconds: int = 3600, max_size: int = 1000):
        self._namespace = namespace
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._fallback: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def _key(self, key: str) -> str:
        return f"{self._namespace}:{key}"

    async def get(self, key: str) -> Any | None:
        r = _get_redis()
        if r is not None:
            try:
                raw = await r.get(self._key(key))
                if raw is not None:
                    return json.loads(raw)
                return None
            except Exception:
                pass
        return self._get_fallback(key)

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        ttl = ttl if ttl is not None else self._ttl
        r = _get_redis()
        if r is not None:
            try:
                await r.setex(self._key(key), ttl, json.dumps(value))
                return
            except Exception:
                pass
        self._set_fallback(key, value, ttl)

    async def invalidate(self, key: str) -> None:
        r = _get_redis()
        if r is not None:
            try:
                await r.delete(self._key(key))
            except Exception:
                pass
        self._fallback.pop(key, None)

    async def clear(self, prefix: str = "") -> None:
        r = _get_redis()
        if r is not None:
            try:
                pattern = self._key(f"{prefix}*") if prefix else self._key("*")
                keys = []
                async for k in r.scan_iter(match=pattern, count=100):
                    keys.append(k)
                if keys:
                    await r.delete(*keys)
            except Exception:
                pass
        if prefix:
            keys_to_remove = [k for k in self._fallback if k.startswith(prefix)]
            for k in keys_to_remove:
                del self._fallback[k]
        else:
            self._fallback.clear()

    async def health_check(self) -> bool:
        r = _get_redis()
        if r is None:
            return False
        try:
            return await r.ping()
        except Exception:
            return False

    @property
    def size(self) -> int:
        return len(self._fallback)

    def _get_fallback(self, key: str) -> Any | None:
        entry = self._fallback.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.time() > expires_at:
            del self._fallback[key]
            return None
        self._fallback.move_to_end(key)
        return value

    def _set_fallback(self, key: str, value: Any, ttl: int) -> None:
        expires_at = time.time() + ttl
        if key in self._fallback:
            self._fallback.move_to_end(key)
        self._fallback[key] = (expires_at, value)
        while len(self._fallback) > self._max_size:
            self._fallback.popitem(last=False)


async def close_redis():
    global _redis_client, _redis_available
    if _redis_client is not None:
        try:
            await _redis_client.aclose()
        except Exception:
            pass
        _redis_client = None
        _redis_available = False
