import asyncio
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from agent.db import async_session_factory
from agent.forecast import exponential_smoothing
from agent.models import Forecast, SalesHistory
from agent.telemetry import trace_node
from shared.cache import forecast_cache


@dataclass
class ForecastResult:
    sku_id: int
    predicted_daily_demand: float
    days_of_stock_remaining: float | None


async def calculate_forecast(sku_id: int, current_stock: int, lead_time_days: int) -> ForecastResult:
    async with async_session_factory() as session:
        result = await session.execute(
            select(SalesHistory.units_sold, SalesHistory.date)
            .where(SalesHistory.sku_id == sku_id)
            .order_by(SalesHistory.date.desc())
            .limit(90)
        )
        rows = result.all()

    if not rows:
        predicted = 0.0
    else:
        ordered_rows = sorted(rows, key=lambda row: row[1])
        daily_values = [float(units) for units, _ in ordered_rows]

        if not daily_values:
            predicted = 0.0
        else:
            avg = sum(daily_values) / len(daily_values)
            smoothed = exponential_smoothing(daily_values)
            predicted = max(smoothed, avg * 0.5)

    days_stock = (current_stock / predicted) if predicted > 0 else 999.0

    async with async_session_factory() as session:
        f = Forecast(
            sku_id=sku_id,
            predicted_daily_demand=round(predicted, 2),
            days_of_stock_remaining=round(days_stock, 1) if days_stock < 999 else None,
            model_version="exp_smoothing_v1",
        )
        session.add(f)
        await session.commit()

    return ForecastResult(
        sku_id=sku_id,
        predicted_daily_demand=round(predicted, 2),
        days_of_stock_remaining=round(days_stock, 1) if days_stock < 999 else None,
    )


@trace_node("forecast")
async def forecast_node(state: dict[str, Any]) -> dict[str, Any]:
    skus = state.get("skus", [])

    async def _forecast_one(sku: dict[str, Any]) -> dict[str, Any] | None:
        cache_key = f"forecast:{sku['id']}"
        cached = await forecast_cache.get(cache_key)
        if cached is not None:
            return dict(cached)

        try:
            fr = await asyncio.wait_for(
                calculate_forecast(
                    sku_id=sku["id"],
                    current_stock=sku["current_stock"],
                    lead_time_days=sku.get("lead_time_days", 7),
                ),
                timeout=10.0,
            )
            result = {
                "sku_id": fr.sku_id,
                "predicted_daily_demand": fr.predicted_daily_demand,
                "days_of_stock_remaining": fr.days_of_stock_remaining,
            }
            await forecast_cache.set(cache_key, result)
            return result
        except TimeoutError:
            return None

    results = [r for r in await asyncio.gather(*[_forecast_one(s) for s in skus]) if r is not None]
    return {**state, "forecasts": results}
