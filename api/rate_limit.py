from fastapi import Request
from slowapi import Limiter


def _get_api_key_key(request: Request) -> str:
    api_key = request.headers.get("x-api-key") or request.headers.get("X-API-Key") or "anonymous"
    return f"api-key:{api_key}"


limiter = Limiter(key_func=_get_api_key_key)
