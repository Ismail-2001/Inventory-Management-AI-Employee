import hashlib
import hmac
import time
from typing import Optional

from agent.config import settings


def _secret() -> str:
    return settings.agent_api_key or "default-signing-secret-change-me"


def sign_token(po_id: int, action: str, ttl_seconds: int = 172800) -> str:
    expiry = int(time.time()) + ttl_seconds
    msg = f"{po_id}:{action}:{expiry}"
    sig = hmac.new(_secret().encode(), msg.encode(), hashlib.sha256).hexdigest()
    return f"{msg}:{sig}"


def verify_token(token: str) -> Optional[dict]:
    try:
        parts = token.split(":")
        if len(parts) != 4:
            return None
        po_id_str, action, expiry_str, sig = parts
        po_id = int(po_id_str)
        expiry = int(expiry_str)

        if time.time() > expiry:
            return None

        expected = hmac.new(
            _secret().encode(),
            f"{po_id}:{action}:{expiry}".encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(sig, expected):
            return None

        return {"po_id": po_id, "action": action, "expiry": expiry}
    except (ValueError, IndexError):
        return None
