"""ROI & performance dashboard endpoint.

GET /api/v1/roi?days=30            → rolling window ending today
GET /api/v1/roi?start=...&end=...  → custom inclusive range (max 365 days)
"""

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from agent.auth import verify_api_key
from agent.db import async_session_factory, async_session_factory_readonly
from agent.models import Merchant
from agent.roi import calculate_roi_report
from api.rate_limit import _get_tier_limit, limiter

router = APIRouter()


@router.get("/api/v1/roi")
@limiter.limit(_get_tier_limit)
async def get_roi(
    request: Request,
    days: int | None = None,
    start: date | None = None,
    end: date | None = None,
    merchant: Merchant = Depends(verify_api_key),
) -> dict[str, Any]:
    today = date.today()
    if start is not None or end is not None:
        if start is None or end is None:
            raise HTTPException(status_code=400, detail="Both start and end are required for a custom range")
        if start > end:
            raise HTTPException(status_code=400, detail="start must be on or before end")
        if (end - start).days + 1 > 365:
            raise HTTPException(status_code=400, detail="Range cannot exceed 365 days")
    else:
        if days is not None and not 1 <= days <= 365:
            raise HTTPException(status_code=400, detail="days must be between 1 and 365")
        span = days if days is not None else 30
        end = today
        start = today - timedelta(days=span - 1)

    factory = async_session_factory_readonly or async_session_factory
    return await calculate_roi_report(merchant.id, start, end, session_factory=factory)
