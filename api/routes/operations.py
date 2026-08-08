from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select

from agent.auth import verify_api_key
from agent.db import async_session_factory, async_session_factory_readonly
from agent.metrics import calculate_acceptance_rate, calculate_forecast_error_summary
from agent.models import Merchant, Sku
from agent.nodes.reflection_node import run_reflection
from agent.nodes.reporting_node import run_reporting
from agent.outcomes import evaluate_pending_outcomes
from api.rate_limit import _get_tier_limit, limiter

router = APIRouter()


@router.get("/api/v1/skus")
@limiter.limit(_get_tier_limit)
async def list_skus(request: Request, merchant: Merchant = Depends(verify_api_key)) -> list[dict[str, Any]]:
    factory = async_session_factory_readonly or async_session_factory
    async with factory() as session:
        query = select(Sku)
        if merchant.id and merchant.id != 0:
            query = query.where(Sku.merchant_id == merchant.id)
        query = query.order_by(Sku.id)
        result = await session.execute(query)
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
@limiter.limit(_get_tier_limit)
async def trigger_outcome_evaluation(request: Request, merchant: Merchant = Depends(verify_api_key)) -> dict[str, Any]:
    count = await evaluate_pending_outcomes()
    return {"status": "ok", "evaluated": count}


@router.post("/api/v1/run-weekly")
@limiter.limit(_get_tier_limit)
async def trigger_weekly(
    request: Request,
    week_start: str | None = None,
    merchant: Merchant = Depends(verify_api_key),
) -> dict[str, Any]:
    ws = date.fromisoformat(week_start) if week_start else date.today()
    insights = await run_reflection(ws)
    digest = await run_reporting(ws, insights)
    return {"status": "ok", "insights_count": len(insights), "digest_length": len(digest)}


@router.get("/api/v1/metrics")
@limiter.limit(_get_tier_limit)
async def get_metrics(
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
    merchant: Merchant = Depends(verify_api_key),
) -> dict[str, Any]:
    from datetime import timedelta

    since = date.today() - timedelta(days=days)
    acceptance = await calculate_acceptance_rate(since=since, session_factory=async_session_factory_readonly or async_session_factory)
    forecast = await calculate_forecast_error_summary(since=since, session_factory=async_session_factory_readonly or async_session_factory)
    return {"acceptance": acceptance, "forecast_error": forecast}
