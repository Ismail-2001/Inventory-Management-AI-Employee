import uuid

from fastapi import APIRouter, Depends, Request

from agent.auth import verify_api_key
from agent.graph import get_compiled_graph
from api.rate_limit import limiter
from agent.db import async_session_factory
from agent.models import PurchaseOrder

router = APIRouter()


@router.post("/api/v1/run-sync")
@limiter.limit("10/minute")
async def run_sync(request: Request, merchant=Depends(verify_api_key)):
    thread_id = str(uuid.uuid4())
    graph = await get_compiled_graph()
    result = await graph.ainvoke({}, {"configurable": {"thread_id": thread_id}})

    pending_pos = result.get("purchase_orders", [])
    if pending_pos:
        async with async_session_factory() as session:
            for po_info in pending_pos:
                po = await session.get(PurchaseOrder, po_info["po_id"])
                if po:
                    po.thread_id = thread_id
            await session.commit()

    return {
        "status": "ok",
        "synced_products": result.get("synced_products", 0),
        "synced_sales": result.get("synced_sales", 0),
        "risk_alerts": len(result.get("risk_alerts", [])),
        "purchase_orders": len(pending_pos),
        "thread_id": thread_id,
    }
