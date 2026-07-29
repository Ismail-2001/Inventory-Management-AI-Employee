from datetime import datetime, timezone
from functools import wraps

from agent.db import async_session_factory
from agent.models import AuditLog


async def log(
    merchant_id: int | None = None,
    actor_type: str = "system",
    actor_id: str | None = None,
    action: str = "",
    target_type: str | None = None,
    target_id: str | None = None,
    details: dict | None = None,
):
    async with async_session_factory() as session:
        entry = AuditLog(
            merchant_id=merchant_id,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details,
            created_at=datetime.now(timezone.utc),
        )
        session.add(entry)
        await session.commit()


def auditable(action: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            return result
        return wrapper
    return decorator
