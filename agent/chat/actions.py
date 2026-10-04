"""Two-phase write safety for chat actions.

The chat agent never writes to the database itself: mutating tools return an
action proposal, and the only write path is :func:`confirm_action` — which
always creates the PO as ``pending_approval``. Human approval stays a
separate step through the normal PO approval flow (POST /api/v1/po/{id}/approve).

Actions expire after ``settings.chat_action_ttl_minutes``; expired or
already-resolved actions are rejected with 410/409 respectively.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from agent.audit import log_audit_event
from agent.config import settings
from agent.db import async_session_factory
from agent.models import ChatMessage, POStatus, PurchaseOrder
from shared.metrics import metrics


class ActionError(Exception):
    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ActionNotFound(ActionError):
    status_code = 404


class ActionConflict(ActionError):
    status_code = 409


class ActionExpired(ActionError):
    status_code = 410


def new_action(tool: str, params: dict[str, Any], ttl_minutes: int | None = None) -> dict[str, Any]:
    ttl = ttl_minutes if ttl_minutes is not None else settings.chat_action_ttl_minutes
    now = datetime.now(UTC)
    return {
        "id": uuid.uuid4().hex,
        "tool": tool,
        "status": "pending",
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=max(1, ttl))).isoformat(),
        "params": params,
    }


async def _find_action(merchant_id: int, conversation_id: str, action_id: str) -> tuple[ChatMessage, dict[str, Any]]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(ChatMessage)
            .where(
                ChatMessage.merchant_id == merchant_id,
                ChatMessage.conversation_id == conversation_id,
                ChatMessage.role == "assistant",
            )
            .order_by(ChatMessage.id.desc())
            .limit(100)
        )
        for message in result.scalars().all():
            for action in message.actions or []:
                if isinstance(action, dict) and action.get("id") == action_id:
                    # Return the live dict from message.actions so status
                    # updates are persisted by _persist_actions.
                    return message, action
    raise ActionNotFound(f"Action {action_id} not found in this conversation")


async def _persist_actions(message: ChatMessage) -> None:
    async with async_session_factory() as session:
        row = await session.get(ChatMessage, message.id)
        if row:
            row.actions = message.actions
            await session.commit()


def _require_pending(action: dict[str, Any]) -> datetime:
    status = action.get("status")
    if status in ("confirmed", "cancelled", "expired"):
        raise ActionConflict(f"Action is already {status}")
    expires = datetime.fromisoformat(str(action.get("expires_at")))
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if datetime.now(UTC) > expires:
        raise ActionExpired("Action expired — ask the assistant to draft a new one")
    return expires


async def _require_pending_persisted(message: ChatMessage, action: dict[str, Any]) -> datetime:
    """Like _require_pending, but records expiry on the message before raising."""
    try:
        return _require_pending(action)
    except ActionExpired:
        action["status"] = "expired"
        action["expired_at"] = datetime.now(UTC).isoformat()
        await _persist_actions(message)
        raise


async def confirm_action(
    merchant_id: int,
    conversation_id: str,
    action_id: str,
    actor: str | None = None,
) -> dict[str, Any]:
    message, action = await _find_action(merchant_id, conversation_id, action_id)
    await _require_pending_persisted(message, action)

    params = action.get("params") or {}
    try:
        sku_id = int(params["sku_id"])
        quantity = int(params["quantity"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ActionConflict("Action payload is malformed and cannot be confirmed") from exc

    po = PurchaseOrder(
        sku_id=sku_id,
        supplier_id=params.get("supplier_id"),
        status=POStatus.pending_approval,
        quantity=quantity,
        unit_cost=float(params.get("unit_cost", 0.0)),
        total_cost=float(params.get("total_cost", 0.0)),
        merchant_id=merchant_id if merchant_id and merchant_id != 0 else None,
        reasoning_text=params.get("reasoning"),
    )
    async with async_session_factory() as session:
        session.add(po)
        await session.commit()
        await session.refresh(po)

    action["status"] = "confirmed"
    action["po_id"] = po.id
    action["confirmed_at"] = datetime.now(UTC).isoformat()
    await _persist_actions(message)

    metrics.inc("chat_actions_confirmed_total")
    await log_audit_event(
        merchant_id=merchant_id if merchant_id != 0 else None,
        actor_type="api_key",
        actor_id=actor or ("merchant" if merchant_id == 0 else str(merchant_id)),
        action="chat_action_confirmed",
        target_type="purchase_order",
        target_id=str(po.id),
        details={
            "action_id": action_id,
            "conversation_id": conversation_id,
            "tool": action.get("tool"),
            "quantity": quantity,
        },
    )

    return {
        "status": "confirmed",
        "action_id": action_id,
        "po_id": po.id,
        "po_status": po.status.value,
        "quantity": po.quantity,
        "total_cost": float(po.total_cost),
    }


async def cancel_action(
    merchant_id: int,
    conversation_id: str,
    action_id: str,
    actor: str | None = None,
) -> dict[str, Any]:
    message, action = await _find_action(merchant_id, conversation_id, action_id)
    await _require_pending_persisted(message, action)

    action["status"] = "cancelled"
    action["cancelled_at"] = datetime.now(UTC).isoformat()
    await _persist_actions(message)

    await log_audit_event(
        merchant_id=merchant_id if merchant_id != 0 else None,
        actor_type="api_key",
        actor_id=actor or ("merchant" if merchant_id == 0 else str(merchant_id)),
        action="chat_action_cancelled",
        target_type="chat_action",
        target_id=action_id,
        details={"conversation_id": conversation_id, "tool": action.get("tool")},
    )

    return {"status": "cancelled", "action_id": action_id}
