import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from langgraph.types import Command
from sqlalchemy import func, select

from agent.audit import log_audit_event
from agent.auth import require_role, verify_api_key
from agent.db import async_session_factory, session_scope
from agent.models import IdempotencyKey, Merchant, POStatus, PurchaseOrder
from agent.signing import verify_token
from api.rate_limit import _get_tier_limit, limiter

router = APIRouter()
_idempotency_cache: dict[str, dict[str, Any]] = {}
_IDEMPOTENCY_CACHE_MAX = 500


async def _resolve_po(po_id: int) -> tuple[PurchaseOrder, str]:
    async with session_scope(async_session_factory) as session:
        result = await session.execute(
            select(PurchaseOrder).where(PurchaseOrder.id == po_id).with_for_update()
        )
        po = result.scalar_one_or_none()
        if not po:
            raise HTTPException(status_code=404, detail="Purchase order not found")
        if po.status != POStatus.pending_approval:
            raise HTTPException(status_code=400, detail=f"PO is already {po.status.value}")
        if not po.thread_id:
            raise HTTPException(status_code=400, detail="No active approval thread for this PO")
        thread_id = po.thread_id
    return po, thread_id


async def _mark_edited_if_changed(po_id: int, approved_quantity: int | None) -> None:
    if approved_quantity is None:
        return
    async with async_session_factory() as session:
        po = await session.get(PurchaseOrder, po_id)
        if po and po.quantity != approved_quantity:
            po.edited_before_approval = True
            po.original_quantity = po.quantity
            await session.commit()


async def _update_po_status(po_id: int, status: POStatus, **extra: Any) -> None:
    async with session_scope(async_session_factory) as session:
        result = await session.execute(
            select(PurchaseOrder)
            .where(PurchaseOrder.id == po_id, PurchaseOrder.status == POStatus.pending_approval)
            .with_for_update()
        )
        po = result.scalar_one_or_none()
        if not po:
            raise HTTPException(status_code=409, detail="PO was already processed or does not exist")
        po.status = status
        for k, v in extra.items():
            setattr(po, k, v)
        await session.commit()


async def _resume_graph(request: Request, thread_id: str, resume_value: str) -> None:
    graph = request.app.state.graph
    await asyncio.wait_for(
        graph.ainvoke(
            Command(resume=resume_value),
            {"configurable": {"thread_id": thread_id}},
        ),
        timeout=120.0,
    )


async def _run_with_idempotency(key: str | None, endpoint: str, action: Callable[[], Awaitable[dict[str, Any]]]) -> dict[str, Any]:
    if key and key in _idempotency_cache:
        return _idempotency_cache[key]

    if key:
        async with session_scope(async_session_factory) as session:
            result = await session.execute(select(IdempotencyKey).where(IdempotencyKey.key == key))
            existing = result.scalar_one_or_none()
            if existing and existing.response_json is not None:
                _idempotency_cache[key] = existing.response_json
                return existing.response_json

    response_payload = await action()

    if key:
        if len(_idempotency_cache) >= _IDEMPOTENCY_CACHE_MAX:
            oldest = next(iter(_idempotency_cache))
            del _idempotency_cache[oldest]
        _idempotency_cache[key] = response_payload
        async with session_scope(async_session_factory) as session:
            session.add(IdempotencyKey(key=key, endpoint=endpoint, response_json=response_payload))
            await session.commit()

    return response_payload


@router.get("/api/v1/po")
async def list_purchase_orders(
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    merchant: Merchant = Depends(verify_api_key),
) -> dict[str, Any]:
    async with session_scope(async_session_factory) as session:
        query = select(PurchaseOrder)
        count_q = select(func.count(PurchaseOrder.id))
        if merchant.id and merchant.id != 0:
            query = query.where(PurchaseOrder.merchant_id == merchant.id)
            count_q = count_q.where(PurchaseOrder.merchant_id == merchant.id)
        if status:
            try:
                status_enum = POStatus(status)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
            query = query.where(PurchaseOrder.status == status_enum)
            count_q = count_q.where(PurchaseOrder.status == status_enum)

        total = (await session.execute(count_q)).scalar() or 0
        query = query.order_by(PurchaseOrder.id.desc()).limit(limit).offset(offset)
        result = await session.execute(query)
        pos = result.scalars().all()

    return {
        "items": [
            {
                "id": po.id,
                "sku_id": po.sku_id,
                "supplier_id": po.supplier_id,
                "status": po.status.value,
                "quantity": po.quantity,
                "unit_cost": float(po.unit_cost),
                "total_cost": float(po.total_cost),
                "reasoning_text": po.reasoning_text,
                "approved_by": po.approved_by,
                "approved_at": po.approved_at.isoformat() if po.approved_at else None,
                "rejected_reason": po.rejected_reason,
                "created_at": po.created_at.isoformat() if po.created_at else None,
                "edited_before_approval": po.edited_before_approval,
                "original_quantity": po.original_quantity,
            }
            for po in pos
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


async def _approve_po_impl(request: Request, po_id: int, approved_by: str, quantity: int | None, merchant_id: int | None = None) -> dict[str, Any]:
    po, thread_id = await _resolve_po(po_id)
    await _mark_edited_if_changed(po_id, quantity)
    await _resume_graph(request, thread_id, "approve")
    await _update_po_status(
        po_id, POStatus.approved,
        approved_by=approved_by,
        approved_at=datetime.now(UTC),
        quantity=quantity if quantity is not None else po.quantity,
    )
    await log_audit_event(
        merchant_id=merchant_id,
        actor_type="api_key",
        actor_id=approved_by,
        action="po.approve",
        target_type="purchase_order",
        target_id=str(po_id),
        details={"quantity": quantity, "thread_id": thread_id},
    )
    return {"status": "approved", "po_id": po_id}


async def _reject_po_impl(request: Request, po_id: int, reason: str, merchant_id: int | None = None) -> dict[str, Any]:
    po, thread_id = await _resolve_po(po_id)
    await _resume_graph(request, thread_id, "reject")
    await _update_po_status(po_id, POStatus.rejected, rejected_reason=reason or None)
    await log_audit_event(
        merchant_id=merchant_id,
        actor_type="api_key",
        actor_id="merchant",
        action="po.reject",
        target_type="purchase_order",
        target_id=str(po_id),
        details={"reason": reason, "thread_id": thread_id},
    )
    return {"status": "rejected", "po_id": po_id}


@router.post("/api/v1/po/{po_id}/approve")
@limiter.limit(_get_tier_limit)
async def approve_po(
    request: Request,
    po_id: int,
    approved_by: str = "merchant",
    quantity: int | None = None,
    merchant: Merchant = Depends(verify_api_key),
    _user: Any = Depends(require_role("owner", "staff")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    return await _run_with_idempotency(
        idempotency_key,
        f"/api/v1/po/{po_id}/approve",
        lambda: _approve_po_impl(request, po_id, approved_by, quantity, merchant.id),
    )


@router.post("/api/v1/po/{po_id}/reject")
@limiter.limit(_get_tier_limit)
async def reject_po(
    request: Request,
    po_id: int,
    reason: str = "",
    merchant: Merchant = Depends(verify_api_key),
    _user: Any = Depends(require_role("owner", "staff")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    return await _run_with_idempotency(
        idempotency_key,
        f"/api/v1/po/{po_id}/reject",
        lambda: _reject_po_impl(request, po_id, reason, merchant.id),
    )


@router.post("/api/v1/po/action")
@limiter.limit(_get_tier_limit)
async def po_action_via_token(
    request: Request,
    token: str = Query(...),
    reason: str = Query(default=""),
    quantity: int | None = Query(default=None, ge=1),
) -> dict[str, Any]:
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    po_id = payload["po_id"]
    action = payload["action"]

    if action == "approve":
        po, thread_id = await _resolve_po(po_id)
        await _mark_edited_if_changed(po_id, quantity)
        await _resume_graph(request, thread_id, "approve")
        await _update_po_status(
            po_id, POStatus.approved,
            approved_by="token",
            approved_at=datetime.now(UTC),
            quantity=quantity if quantity is not None else po.quantity,
        )
        return {"status": "approved", "po_id": po_id}
    elif action == "reject":
        po, thread_id = await _resolve_po(po_id)
        await _resume_graph(request, thread_id, "reject")
        await _update_po_status(po_id, POStatus.rejected, rejected_reason=reason or None)
        return {"status": "rejected", "po_id": po_id}
    else:
        raise HTTPException(status_code=400, detail="Invalid action")
