import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from agent.auth import verify_api_key
from api.rate_limit import limiter
from shared.task_queue import task_queue

router = APIRouter()


@router.post("/api/v1/run-sync")
@limiter.limit("5/minute")
async def run_sync(request: Request, merchant=Depends(verify_api_key)):
    """Trigger the full inventory agent pipeline (synchronous).

    The graph runs synchronously: sync → forecast → risk → po_draft → notify_pending.
    Returns after the graph completes, or 504 if it exceeds 120s.
    """
    thread_id = str(uuid.uuid4())
    graph = request.app.state.graph
    try:
        result = await asyncio.wait_for(
            graph.ainvoke(
                {"merchant_id": merchant.id, "thread_id": thread_id},
                {"configurable": {"thread_id": thread_id}},
            ),
            timeout=120.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Graph execution timed out")

    pending_pos = result.get("purchase_orders", [])

    return {
        "status": "ok",
        "synced_products": result.get("synced_products", 0),
        "synced_sales": result.get("synced_sales", 0),
        "risk_alerts": len(result.get("risk_alerts", [])),
        "purchase_orders": len(pending_pos),
        "thread_id": thread_id,
    }


@router.post("/api/v1/run-sync-async")
@limiter.limit("10/minute")
async def run_sync_async(request: Request, merchant=Depends(verify_api_key)):
    """Trigger the inventory agent pipeline (async/background).

    Returns immediately with a task_id (HTTP 202). Poll /api/v1/tasks/{task_id}
    to get the result when done. Useful for large inventories where sync
    can take > 2 minutes.
    """
    thread_id = str(uuid.uuid4())
    task_id = await task_queue.enqueue(
        {"merchant_id": merchant.id, "thread_id": thread_id},
        {"configurable": {"thread_id": thread_id}},
    )
    return {
        "status": "accepted",
        "task_id": task_id,
        "thread_id": thread_id,
    }


@router.get("/api/v1/tasks/{task_id}")
async def get_task_result(task_id: str, merchant=Depends(verify_api_key)):
    """Poll the result of an async pipeline run."""
    result = task_queue.get_result(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found or still processing")
    task_queue.remove_result(task_id)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    pending_pos = result.get("purchase_orders", [])
    return {
        "status": "ok",
        "synced_products": result.get("synced_products", 0),
        "synced_sales": result.get("synced_sales", 0),
        "risk_alerts": len(result.get("risk_alerts", [])),
        "purchase_orders": len(pending_pos),
    }
