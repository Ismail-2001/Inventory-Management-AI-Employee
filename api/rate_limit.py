import hashlib

from fastapi import Request
from slowapi import Limiter

from agent.models import TIER_RATE_LIMITS


def _get_api_key_key(request: Request) -> str:
    api_key = request.headers.get("x-api-key") or request.headers.get("X-API-Key") or "anonymous"
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
    tier = getattr(request.state, "merchant_tier", None)
    limit = TIER_RATE_LIMITS.get(tier, "20/minute") if tier else "20/minute"
    return f"api-key:{key_hash}:{limit}"


limiter = Limiter(key_func=_get_api_key_key, default_limits=["20/minute"])
