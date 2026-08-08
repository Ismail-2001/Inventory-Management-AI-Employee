import hashlib

from fastapi import Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address

from agent.config import settings
from agent.models import TIER_RATE_LIMITS, MerchantTier


def _get_rate_limit_key(request: Request) -> str:
    api_key = request.headers.get("x-api-key") or request.headers.get("X-API-Key") or ""
    tier = getattr(request.state, "merchant_tier", None) or "developer"
    tier_str = tier.value if hasattr(tier, "value") else str(tier)
    if api_key:
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
        return f"tenant:{key_hash}:{tier_str}"
    ip = get_remote_address(request) or "unknown"
    return f"ip:{ip}:{tier_str}"


def _get_tier_limit(key: str = "") -> str:
    parts = key.rsplit(":", 1)
    if len(parts) == 2:
        tier_str = parts[1]
        try:
            tier = MerchantTier(tier_str)
            return TIER_RATE_LIMITS.get(tier, "20/minute")
        except ValueError:
            pass
    return "20/minute"


storage_uri = settings.redis_url if settings.redis_url else "memory://"

limiter = Limiter(
    key_func=_get_rate_limit_key,
    default_limits=["20/minute"],
    storage_uri=storage_uri,
)


def add_rate_limit_headers(response: Response, request: Request, limit: str) -> None:
    response.headers["X-RateLimit-Limit"] = limit.split("/")[0]
    tier = getattr(request.state, "merchant_tier", None)
    if tier:
        response.headers["X-RateLimit-Tier"] = tier.value if hasattr(tier, "value") else str(tier)
