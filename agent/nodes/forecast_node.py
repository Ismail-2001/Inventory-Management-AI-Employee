import asyncio
import logging
import statistics
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select

from agent.config import settings
from agent.db import async_session_factory
from agent.forecast import ForecastBundle, build_ensemble, legacy_predict_daily
from agent.forecast_engine import ENGINE_ENSEMBLE, ENGINE_EXPONENTIAL, ENGINE_SHADOW, canonical_engine
from agent.models import Forecast, SalesHistory
from agent.state import State
from agent.telemetry import trace_node
from shared.cache import forecast_cache
from shared.metrics import metrics

logger = logging.getLogger(__name__)

VALID_MODES = {"exp_smoothing_v1", "shadow", "ensemble_v2"}
FORECAST_TIMEOUT_SECONDS = 12.0


@dataclass
class ForecastResult:
    sku_id: int
    predicted_daily_demand: float
    days_of_stock_remaining: float | None
    p10_daily_demand: float | None = None
    p90_daily_demand: float | None = None
    days_of_cover_p10: float | None = None
    days_of_cover_p90: float | None = None
    horizon_days: int = 30
    model_version: str = "exp_smoothing_v1"
    backtest_wmape: float | None = None
    backtest_bias: float | None = None
    fallback_used: bool = False
    model_meta: dict[str, Any] = field(default_factory=dict)


def _mode() -> str:
    mode = settings.forecast_model_version
    return mode if mode in VALID_MODES else "exp_smoothing_v1"


def _days_of_cover(stock: int, demand: float | None) -> float | None:
    if demand is None or demand <= 0:
        return None
    days = round(stock / demand, 1)
    return days if days < 999 else None


async def _load_history(sku_id: int) -> list[tuple[date, float]]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(SalesHistory.units_sold, SalesHistory.date)
            .where(SalesHistory.sku_id == sku_id)
            .order_by(SalesHistory.date.desc())
            .limit(settings.forecast_history_days)
        )
        rows = result.all()
    return [(row[1], float(row[0])) for row in rows]


def _v1_values(history: list[tuple[date, float]]) -> list[float]:
    asc = sorted(history, key=lambda r: r[0])
    return [v for _, v in asc][-90:]


async def _persist_async(forecasts: list[Forecast]) -> None:
    if not forecasts:
        return
    async with async_session_factory() as session:
        for f in forecasts:
            session.add(f)
        await session.commit()


def _bundle_result(
    sku_id: int,
    current_stock: int,
    bundle: ForecastBundle,
    horizon: int,
) -> tuple[ForecastResult, float]:
    predicted = statistics.fmean(bundle.predictions) if bundle.predictions else 0.0
    p10_mean = statistics.fmean(bundle.p10) if bundle.p10 else 0.0
    p90_mean = statistics.fmean(bundle.p90) if bundle.p90 else 0.0
    days_stock = _days_of_cover(current_stock, predicted)
    result = ForecastResult(
        sku_id=sku_id,
        predicted_daily_demand=round(predicted, 2),
        days_of_stock_remaining=days_stock,
        p10_daily_demand=round(p10_mean, 2),
        p90_daily_demand=round(p90_mean, 2),
        days_of_cover_p10=_days_of_cover(current_stock, p10_mean),
        days_of_cover_p90=_days_of_cover(current_stock, p90_mean),
        horizon_days=horizon,
        model_version="ensemble_v2",
        backtest_wmape=bundle.wmape,
        backtest_bias=bundle.bias,
        model_meta=bundle.meta,
    )
    return result, predicted


def _row(result: ForecastResult) -> Forecast:
    return Forecast(
        sku_id=result.sku_id,
        predicted_daily_demand=result.predicted_daily_demand,
        days_of_stock_remaining=result.days_of_stock_remaining,
        model_version=result.model_version,
        p10_daily_demand=result.p10_daily_demand,
        p90_daily_demand=result.p90_daily_demand,
        days_of_cover_p10=result.days_of_cover_p10,
        days_of_cover_p90=result.days_of_cover_p90,
        backtest_wmape=result.backtest_wmape,
        backtest_bias=result.backtest_bias,
        horizon_days=result.horizon_days,
        model_meta=result.model_meta or None,
    )


def _v1_result(sku_id: int, current_stock: int, values: list[float], fallback: bool = False) -> ForecastResult:
    predicted = legacy_predict_daily(values)
    days_stock = current_stock / predicted if predicted > 0 else 999.0
    return ForecastResult(
        sku_id=sku_id,
        predicted_daily_demand=round(predicted, 2),
        days_of_stock_remaining=round(days_stock, 1) if days_stock < 999 else None,
        horizon_days=settings.forecast_horizon_days,
        model_version="exp_smoothing_v1",
        fallback_used=fallback,
    )


async def calculate_forecast(
    sku_id: int,
    current_stock: int,
    lead_time_days: int,
    engine: str | None = None,
) -> ForecastResult:
    """Compute the point forecast for one SKU for the requested engine.

    Engines (canonical, see agent/forecast_engine):
        exponential  legacy path only
        shadow       compute + persist both, serve exponential
        ensemble     serve ensemble; any failure falls back to exponential

    When ``engine`` is omitted the legacy FORECAST_MODEL_VERSION mode applies
    (exp_smoothing_v1 / shadow / ensemble_v2 map onto the canonical names).
    """
    start = time.perf_counter()
    history = await _load_history(sku_id)
    values = _v1_values(history)
    v1 = _v1_result(sku_id, current_stock, values)
    horizon = max(1, settings.forecast_horizon_days)
    mode = canonical_engine(engine) or canonical_engine(_mode()) or ENGINE_EXPONENTIAL

    served = v1
    rows_to_write: list[Forecast] = []
    bundle: ForecastBundle | None = None
    fallback = False

    if mode == ENGINE_EXPONENTIAL:
        rows_to_write = [_row(v1)]
    else:
        try:
            from agent.forecast_prophet import try_prophet

            external = None
            if settings.forecast_enable_prophet and history:
                external = await try_prophet(history, horizon, settings.forecast_stockout_correction)
            bundle = build_ensemble(
                history,
                horizon,
                external=external,
                stockout_correction=settings.forecast_stockout_correction,
            )
            v2, _ = _bundle_result(sku_id, current_stock, bundle, horizon)
            if mode == ENGINE_SHADOW:
                rows_to_write = [_row(v1), _row(v2)]
                served = v1
            else:
                rows_to_write = [_row(v2)]
                served = v2
        except Exception:
            logger.exception("ensemble engine failed for sku=%s — serving exponential", sku_id)
            fallback = True
            served = _v1_result(sku_id, current_stock, values, fallback=True)
            rows_to_write = [_row(served)]

    await _persist_async(rows_to_write)

    latency_ms = round((time.perf_counter() - start) * 1000, 1)
    metrics.inc("forecast_runs_total", model="exp_smoothing_v1")
    if bundle is not None:
        metrics.inc("forecast_runs_total", model="ensemble_v2")
    if fallback:
        metrics.inc("forecast_fallback_total")
        metrics.inc("forecast_fallback_count", reason="ensemble_error")
    metrics.observe("forecast_duration_seconds", latency_ms / 1000.0, model=served.model_version)

    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        span.set_attribute("forecast.model", served.model_version)
        span.set_attribute("forecast.engine", mode)
        span.set_attribute("forecast.latency_ms", latency_ms)
        span.set_attribute("forecast.fallback", fallback)
        if served.backtest_wmape is not None:
            span.set_attribute("forecast.wmape", served.backtest_wmape)
        if bundle is not None:
            span.set_attribute("forecast.sigma", bundle.sigma)
    except Exception:
        pass

    logger.info(
        "forecast sku=%s engine=%s model=%s demand=%.2f days=%s wmape=%s fallback=%s latency_ms=%.1f",
        sku_id,
        mode,
        served.model_version,
        served.predicted_daily_demand,
        served.days_of_stock_remaining,
        served.backtest_wmape,
        fallback,
        latency_ms,
    )
    return served


def _result_to_state(fr: ForecastResult) -> dict[str, Any]:
    return {
        "sku_id": fr.sku_id,
        "predicted_daily_demand": fr.predicted_daily_demand,
        "days_of_stock_remaining": fr.days_of_stock_remaining,
        "p10_daily_demand": fr.p10_daily_demand,
        "p90_daily_demand": fr.p90_daily_demand,
        "days_of_cover_p10": fr.days_of_cover_p10,
        "days_of_cover_p90": fr.days_of_cover_p90,
        "horizon_days": fr.horizon_days,
        "model_version": fr.model_version,
        "backtest_wmape": fr.backtest_wmape,
        "backtest_bias": fr.backtest_bias,
        "fallback_used": fr.fallback_used,
        "model_meta": fr.model_meta,
    }


@trace_node("forecast")
async def forecast_node(state: State) -> State:
    skus = state.get("skus", [])
    engine = canonical_engine(state.get("forecast_engine")) or canonical_engine(_mode()) or ENGINE_EXPONENTIAL
    horizon = max(1, settings.forecast_horizon_days)

    async def _forecast_one(sku: dict[str, Any], run_engine: str) -> dict[str, Any] | None:
        cache_key = f"forecast:{sku['id']}:{run_engine}:{horizon}"
        cached = await forecast_cache.get(cache_key)
        if cached is not None:
            return dict(cached)

        try:
            fr = await asyncio.wait_for(
                calculate_forecast(
                    sku_id=sku["id"],
                    current_stock=sku["current_stock"],
                    lead_time_days=sku.get("lead_time_days", 7),
                    engine=run_engine,
                ),
                timeout=FORECAST_TIMEOUT_SECONDS,
            )
            result = _result_to_state(fr)
            await forecast_cache.set(cache_key, result)
            return result
        except TimeoutError:
            metrics.inc("forecast_timeout_total")
            metrics.inc("forecast_fallback_count", reason="timeout")
            return None

    async def _gather(run_engine: str) -> list[dict[str, Any] | None]:
        return await asyncio.gather(*[_forecast_one(s, run_engine) for s in skus])

    results = [r for r in await _gather(engine) if r is not None]
    effective_engine = engine
    circuit_tripped = False

    # Circuit breaker: too many ensemble failures/timeouts in this run →
    # rerun every SKU on the exponential engine (cache may answer instantly).
    if engine == ENGINE_ENSEMBLE and skus:
        attempted = len(skus)
        failures = (attempted - len(results)) + sum(1 for r in results if r.get("fallback_used"))
        if failures / attempted > settings.forecast_circuit_threshold:
            circuit_tripped = True
            effective_engine = ENGINE_EXPONENTIAL
            metrics.inc("forecast_fallback_count", value=float(failures), reason="circuit_breaker")
            logger.error(
                "forecast circuit breaker tripped: %s/%s sku runs failed (threshold %.3f) — rerunning run with exponential engine",
                failures,
                attempted,
                settings.forecast_circuit_threshold,
            )
            results = [r for r in await _gather(effective_engine) if r is not None]

    for r in results:
        serving = ENGINE_ENSEMBLE if r.get("model_version") == "ensemble_v2" else ENGINE_EXPONENTIAL
        metrics.inc(
            "forecast_engine_used",
            engine=serving,
            merchant=str(state.get("merchant_id") or 0),
        )

    return {
        **state,
        "forecasts": results,
        "forecast_engine": effective_engine,
        "forecast_circuit_tripped": circuit_tripped,
    }
