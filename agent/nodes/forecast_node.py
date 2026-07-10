from dataclasses import dataclass

from sqlalchemy import select, func

from agent.db import async_session_factory
from agent.forecast import exponential_smoothing
from agent.models import Forecast, SalesHistory
from agent.telemetry import trace_node


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
        by_day: dict = {}
        for units, d in rows:
            by_day[d.isoformat()] = units

        if not by_day:
            predicted = 0.0
        else:
            avg = sum(by_day.values()) / len(by_day)
            daily_values = [float(v) for v in by_day.values()]
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
async def forecast_node(state: dict) -> dict:
    skus = state.get("skus", [])
    results = []
    for sku in skus:
        fr = await calculate_forecast(
            sku_id=sku["id"],
            current_stock=sku["current_stock"],
            lead_time_days=sku.get("lead_time_days", 7),
        )
        results.append({
            "sku_id": fr.sku_id,
            "predicted_daily_demand": fr.predicted_daily_demand,
            "days_of_stock_remaining": fr.days_of_stock_remaining,
        })
    return {"forecasts": results}
