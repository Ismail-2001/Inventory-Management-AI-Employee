"""Structured Audit Trail — compliance logging for all sensitive operations.

Logs every action with actor, target, details, and timestamp.
Writes to the `audit_log` table and optionally to structured JSON logs.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from agent.db import async_session_factory, session_scope
from agent.models import AuditLog

logger = logging.getLogger("audit")


async def log(action: str, details: dict[str, Any] | None = None, **kwargs: Any) -> None:
    """Legacy structured log helper — writes to audit_log table + structured logger."""
    merged = dict(details or {})
    merged.update(kwargs)
    logger.info("AUDIT: action=%s details=%s", action, merged)
    try:
        async with session_scope(async_session_factory) as session:
            log_entry = AuditLog(
                merchant_id=merged.pop("merchant_id", None),
                actor_type=merged.pop("actor_type", "system"),
                actor_id=merged.pop("actor_id", None),
                action=action,
                target_type=merged.pop("target_type", None),
                target_id=str(merged.pop("target_id", "")) if merged.get("target_id") else None,
                details=merged if merged else None,
                created_at=datetime.now(UTC),
            )
            session.add(log_entry)
            await session.commit()
    except Exception:
        pass


async def log_audit_event(
    merchant_id: int | None,
    actor_type: str,
    actor_id: str | None,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    entry_details = dict(details or {})
    if ip_address:
        entry_details["ip_address"] = ip_address

    async with session_scope(async_session_factory) as session:
        log_entry = AuditLog(
            merchant_id=merchant_id,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id else None,
            details=entry_details if entry_details else None,
        )
        session.add(log_entry)
        await session.commit()

    logger.info(
        "AUDIT: merchant=%s actor=%s/%s action=%s target=%s/%s details=%s",
        merchant_id,
        actor_type,
        actor_id,
        action,
        target_type,
        target_id,
        entry_details,
    )


async def get_audit_logs(
    merchant_id: int | None = None,
    actor_type: str | None = None,
    action: str | None = None,
    target_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    from sqlalchemy import func

    async with session_scope(async_session_factory) as session:
        query = select(AuditLog)
        count_query = select(func.count(AuditLog.id))

        if merchant_id is not None:
            query = query.where(AuditLog.merchant_id == merchant_id)
            count_query = count_query.where(AuditLog.merchant_id == merchant_id)
        if actor_type:
            query = query.where(AuditLog.actor_type == actor_type)
            count_query = count_query.where(AuditLog.actor_type == actor_type)
        if action:
            query = query.where(AuditLog.action == action)
            count_query = count_query.where(AuditLog.action == action)
        if target_type:
            query = query.where(AuditLog.target_type == target_type)
            count_query = count_query.where(AuditLog.target_type == target_type)

        total_result = await session.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
        result = await session.execute(query)
        entries = result.scalars().all()

    return [
        {
            "id": e.id,
            "merchant_id": e.merchant_id,
            "actor_type": e.actor_type,
            "actor_id": e.actor_id,
            "action": e.action,
            "target_type": e.target_type,
            "target_id": e.target_id,
            "details": e.details,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in entries
    ], total
