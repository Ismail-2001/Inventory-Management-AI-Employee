from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from agent.auth import verify_api_key
from agent.metrics import calculate_acceptance_rate, calculate_forecast_error_summary
from agent.nodes.reflection_node import run_reflection
from agent.nodes.reporting_node import run_reporting
from agent.outcomes import evaluate_pending_outcomes

router = APIRouter()


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
