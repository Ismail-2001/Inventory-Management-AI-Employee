"""Audit Log API Routes.

Endpoints:
    GET /api/v1/audit/logs      — List audit logs with filters
    GET /api/v1/audit/export    — Export audit logs as JSONL
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from agent.auth import verify_api_key
from agent.audit import get_audit_logs
from agent.models import Merchant

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("/logs")
async def list_audit_logs(
    request: Request,
    action: str | None = Query(None, description="Filter by action (e.g. po.approve, po.reject)"),
    actor_type: str | None = Query(None, description="Filter by actor type (api_key, sso, webhook)"),
    target_type: str | None = Query(None, description="Filter by target type (purchase_order, sku, merchant)"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    merchant: Merchant = Depends(verify_api_key),
):
    entries, total = await get_audit_logs(
        merchant_id=merchant.id if merchant.id != 0 else None,
        actor_type=actor_type,
        action=action,
        target_type=target_type,
        limit=limit,
        offset=offset,
    )
    return {
        "items": entries,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/export")
async def export_audit_logs(
    request: Request,
    action: str | None = Query(None),
    merchant: Merchant = Depends(verify_api_key),
):
    entries, total = await get_audit_logs(
        merchant_id=merchant.id if merchant.id != 0 else None,
        action=action,
        limit=5000,
    )

    import json

    def generate():
        for entry in entries:
            yield json.dumps(entry, default=str) + "\n"

    return StreamingResponse(
        generate(),
        media_type="application/jsonl",
        headers={"Content-Disposition": "attachment; filename=audit_logs.jsonl"},
    )
