from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from langgraph.graph import Command
from sqlalchemy import select

from agent.auth import verify_api_key, require_role
from agent.db import async_session_factory
from agent.graph import get_compiled_graph
from agent.models import POStatus, PurchaseOrder
from agent.signing import sign_token, verify_token

router = APIRouter()


async def _resolve_po(po_id: int) -> tuple[PurchaseOrder, str]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(PurchaseOrder).where(PurchaseOrder.id == po_id)
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


async def _mark_edited_if_changed(po_id: int, approved_quantity: int | None):
    if approved_quantity is None:
        return
    async with async_session_factory() as session:
        po = await session.get(PurchaseOrder, po_id)
        if po and po.quantity != approved_quantity:
            po.edited_before_approval = True
            po.original_quantity = po.quantity
            await session.commit()


async def _update_po_status(po_id: int, status: POStatus, **extra):
    async with async_session_factory() as session:
        po = await session.get(PurchaseOrder, po_id)
        if po:
            po.status = status
            for k, v in extra.items():
                setattr(po, k, v)
            await session.commit()


async def _resume_graph(thread_id: str, resume_value: str):
    graph = await get_compiled_graph()
    await graph.ainvoke(
        Command(resume=resume_value),
        {"configurable": {"thread_id": thread_id}},
    )


@router.post("/api/v1/po/{po_id}/approve")
async def approve_po(
    po_id: int,
    approved_by: str = "merchant",
    quantity: int | None = None,
    merchant=Depends(verify_api_key),
    _user=Depends(require_role("owner", "staff")),
):
    po, thread_id = await _resolve_po(po_id)
    await _mark_edited_if_changed(po_id, quantity)
    await _resume_graph(thread_id, "approve")
    await _update_po_status(
        po_id, POStatus.approved,
        approved_by=approved_by,
        approved_at=datetime.now(timezone.utc),
        quantity=quantity if quantity else po.quantity,
    )
    return {"status": "approved", "po_id": po_id}


@router.post("/api/v1/po/{po_id}/reject")
async def reject_po(
    po_id: int,
    reason: str = "",
    merchant=Depends(verify_api_key),
    _user=Depends(require_role("owner", "staff")),
):
    po, thread_id = await _resolve_po(po_id)
    await _resume_graph(thread_id, "reject")
    await _update_po_status(po_id, POStatus.rejected, rejected_reason=reason or None)
    return {"status": "rejected", "po_id": po_id}


@router.get("/api/v1/po/action")
async def po_action_via_token(
    token: str = Query(...),
    reason: str = Query(default=""),
    quantity: int | None = Query(default=None),
):
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    po_id = payload["po_id"]
    action = payload["action"]

    if action == "approve":
        po, thread_id = await _resolve_po(po_id)
        await _mark_edited_if_changed(po_id, quantity)
        await _resume_graph(thread_id, "approve")
        await _update_po_status(
            po_id, POStatus.approved,
            approved_by="token",
            approved_at=datetime.now(timezone.utc),
            quantity=quantity if quantity else po.quantity,
        )
        return {"status": "approved", "po_id": po_id}
    elif action == "reject":
        po, thread_id = await _resolve_po(po_id)
        await _resume_graph(thread_id, "reject")
        await _update_po_status(po_id, POStatus.rejected, rejected_reason=reason or None)
        return {"status": "rejected", "po_id": po_id}
    else:
        raise HTTPException(status_code=400, detail="Invalid action")
