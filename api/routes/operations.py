from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from agent.auth import verify_api_key
from agent.db import async_session_factory
from agent.metrics import calculate_acceptance_rate, calculate_forecast_error_summary
from agent.models import Sku
from agent.nodes.reflection_node import run_reflection
from agent.nodes.reporting_node import run_reporting
from agent.outcomes import evaluate_pending_outcomes

router = APIRouter()


@router.get("/api/v1/skus")
async def list_skus(merchant=Depends(verify_api_key)):
    async with async_session_factory() as session:
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
async def trigger_outcome_evaluation(merchant=Depends(verify_api_key)):
    count = await evaluate_pending_outcomes()
    return {"status": "ok", "evaluated": count}


@router.post("/api/v1/run-weekly")
async def trigger_weekly(
    week_start: str | None = None,
    merchant=Depends(verify_api_key),
):
    ws = date.fromisoformat(week_start) if week_start else date.today()
    insights = await run_reflection(ws)
    digest = await run_reporting(ws, insights)
    return {"status": "ok", "insights_count": len(insights), "digest_length": len(digest)}


@router.get("/api/v1/metrics")
async def get_metrics(
    days: int = 30,
    merchant=Depends(verify_api_key),
):
    from datetime import timedelta

    since = date.today() - timedelta(days=days)
    acceptance = await calculate_acceptance_rate(since=since)
    forecast = await calculate_forecast_error_summary(since=since)
    return {"acceptance": acceptance, "forecast_error": forecast}
