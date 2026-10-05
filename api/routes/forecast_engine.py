"""Forecast engine admin API.

GET  /api/v1/forecast-engine — resolved engine, flags, optional gate run
POST /api/v1/forecast-engine — set this merchant's engine (kill switch)
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from agent.audit import log
from agent.auth import verify_api_key
from agent.config import settings
from agent.db import async_session_factory
from agent.forecast_engine import (
    VALID_ENGINES,
    canonical_engine,
    evaluate_merchant,
    in_rollout_cohort,
    resolve_engine,
)
from agent.models import Merchant
from api.rate_limit import _get_tier_limit, limiter
from shared.metrics import metrics

router = APIRouter()


class EngineUpdateRequest(BaseModel):
    engine: str = Field(..., description="ensemble | exponential | shadow")


@router.get("/api/v1/forecast-engine")
@limiter.limit(_get_tier_limit)
async def get_forecast_engine(
    request: Request,
    evaluate: bool = Query(default=False, description="Run the promotion gate evaluation"),
    merchant: Merchant = Depends(verify_api_key),
) -> dict[str, Any]:
    stored = getattr(merchant, "forecast_engine", None)
    active, source = resolve_engine(merchant_engine=stored, merchant_id=merchant.id)
    payload: dict[str, Any] = {
        "merchant_id": merchant.id,
        "stored_engine": stored,
        "active_engine": active,
        "source": source,
        "promoted_at": str(getattr(merchant, "forecast_promoted_at", None) or ""),
        "global_override": canonical_engine(settings.forecast_engine_override),
        "default_engine": canonical_engine(settings.forecast_engine_default),
        "rollout_percent": settings.forecast_rollout_percent,
        "circuit_breaker_threshold": settings.forecast_circuit_threshold,
        "valid_engines": sorted(VALID_ENGINES),
        "in_rollout_cohort": in_rollout_cohort(merchant.id),
    }
    if evaluate:
        if merchant.id in (None, 0):
            raise HTTPException(status_code=400, detail="demo merchant has no persisted history")
        evaluation = await evaluate_merchant(
            merchant.id,
            engine_before=stored or "",
            cohort=in_rollout_cohort(merchant.id),
        )
        payload["evaluation"] = evaluation.to_dict()
    return payload


@router.post("/api/v1/forecast-engine")
@limiter.limit(_get_tier_limit)
async def set_forecast_engine(
    request: Request,
    body: EngineUpdateRequest,
    merchant: Merchant = Depends(verify_api_key),
) -> dict[str, Any]:
    engine = canonical_engine(body.engine)
    if engine is None:
        raise HTTPException(
            status_code=422,
            detail=f"invalid engine; expected one of {sorted(VALID_ENGINES)}",
        )
    if merchant.id in (None, 0):
        raise HTTPException(
            status_code=400,
            detail="demo merchant is not persisted; set FORECAST_ENGINE_OVERRIDE instead",
        )

    # The authenticated merchant row is detached; re-fetch before mutating.
    async with async_session_factory() as session:
        row = await session.get(Merchant, merchant.id)
        if row is None:
            raise HTTPException(status_code=404, detail="merchant not found")
        row.forecast_engine = engine
        row.forecast_promoted_at = datetime.now(UTC) if engine == "ensemble" else None
        await session.commit()

    for candidate in sorted(VALID_ENGINES):
        metrics.gauge(
            "forecast_promotion_status",
            1.0 if candidate == engine else 0.0,
            merchant=str(merchant.id),
            engine=candidate,
        )
    await log(
        action="forecast_engine_change",
        details={"merchant_id": merchant.id, "engine": engine, "source": "api"},
    )
    return {"status": "ok", "merchant_id": merchant.id, "engine": engine}
