from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select

from agent.auth import verify_api_key
from api.rate_limit import limiter
from agent.db import async_session_factory, async_session_factory_readonly
from agent.metrics import calculate_acceptance_rate, calculate_forecast_error_summary
from agent.models import Sku
from agent.nodes.reflection_node import run_reflection
from agent.nodes.reporting_node import run_reporting
from agent.outcomes import evaluate_pending_outcomes

router = APIRouter()


@router.get("/api/v1/skus")
@limiter.limit("30/minute")
async def list_skus(request: Request, merchant=Depends(verify_api_key)):
    factory = async_session_factory_readonly or async_session_factory
    async with factory() as session:
        result = await session.execute(select(Sku).order_by(Sku.id))
        skus = result.scalars().all()

    return [
        {
            "id": sku.id,
            "shopify_variant_id": sku.shopify_variant_id,
            "sku_code": sku.sku_code,
            "title": sku.title,
            "current_stock": sku.current_stock,
            "location_id": sku.location_id,
        }
        for sku in skus
    ]


@router.post("/api/v1/evaluate-outcomes")
@limiter.limit("5/hour")
async def trigger_outcome_evaluation(request: Request, merchant=Depends(verify_api_key)):
    count = await evaluate_pending_outcomes()
    return {"status": "ok", "evaluated": count}


@router.post("/api/v1/run-weekly")
@limiter.limit("1/hour")
async def trigger_weekly(
    request: Request,
    week_start: str | None = None,
    merchant=Depends(verify_api_key),
):
    ws = date.fromisoformat(week_start) if week_start else date.today()
    insights = await run_reflection(ws)
    digest = await run_reporting(ws, insights)
    return {"status": "ok", "insights_count": len(insights), "digest_length": len(digest)}


@router.get("/api/v1/metrics")
@limiter.limit("30/minute")
async def get_metrics(
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
    merchant=Depends(verify_api_key),
):
    from datetime import timedelta

    since = date.today() - timedelta(days=days)
    acceptance = await calculate_acceptance_rate(since=since, session_factory=async_session_factory_readonly or async_session_factory)
    forecast = await calculate_forecast_error_summary(since=since, session_factory=async_session_factory_readonly or async_session_factory)
    return {"acceptance": acceptance, "forecast_error": forecast}
