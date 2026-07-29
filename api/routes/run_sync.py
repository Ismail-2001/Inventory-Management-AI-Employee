import uuid

from fastapi import APIRouter, Depends, Request

from agent.auth import verify_api_key
from api.rate_limit import limiter

router = APIRouter()


@router.post("/api/v1/run-sync")
@limiter.limit("5/minute")
async def run_sync(request: Request, merchant=Depends(verify_api_key)):
    """Trigger the full inventory agent pipeline.

    The graph runs synchronously: sync → forecast → risk → po_draft → notify_pending.
    Purchase orders are created with a thread_id attached immediately (no post-hoc DB update).
    Returns the thread_id so the caller can resume the graph after human approval.
    """
    thread_id = str(uuid.uuid4())
    graph = request.app.state.graph
    result = await graph.ainvoke({}, {"configurable": {"thread_id": thread_id}})

    pending_pos = result.get("purchase_orders", [])

    return {
        "status": "ok",
        "synced_products": result.get("synced_products", 0),
        "synced_sales": result.get("synced_sales", 0),
        "risk_alerts": len(result.get("risk_alerts", [])),
        "purchase_orders": len(pending_pos),
        "thread_id": thread_id,
    }
