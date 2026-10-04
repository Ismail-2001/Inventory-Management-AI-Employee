"""Optional Prophet candidate for the forecasting ensemble.

Prophet is never a hard dependency: the import is lazy, failures trip an
in-process circuit breaker, and every call site treats ``None`` as "candidate
unavailable". The tier-0 ensemble in ``agent.forecast`` remains fully
functional without this module ever succeeding.

Install (optional): ``pip install -r requirements-forecast.txt``
Disable: ``FORECAST_MODEL_PROPHET=false``
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date
from threading import Lock

from agent.config import settings
from agent.forecast import (
    ExternalCandidate,
    bias_pct,
    holdout_days,
    impute_censored_days,
    prepare_series,
    wmape,
)

logger = logging.getLogger(__name__)

PROPHET_TIMEOUT_SECONDS = 5.0
CIRCUIT_FAILURE_THRESHOLD = 5
CIRCUIT_OPEN_SECONDS = 300.0
MIN_OBS = 60
MIN_NONZERO = 30

_import_ok: bool | None = None


def prophet_available() -> bool:
    """Cached import probe — cheap after the first call."""
    global _import_ok
    if _import_ok is None:
        try:
            import prophet  # noqa: F401

            _import_ok = True
        except Exception:
            _import_ok = False
            logger.info("prophet not installed — ensemble runs tier-0 models only")
    return _import_ok


class ProphetCircuitBreaker:
    """Open after N consecutive failures; half-open after a cooldown."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._failures = 0
        self._open_until = 0.0

    def is_open(self) -> bool:
        with self._lock:
            return time.monotonic() < self._open_until

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._open_until = 0.0

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= CIRCUIT_FAILURE_THRESHOLD:
                self._open_until = time.monotonic() + CIRCUIT_OPEN_SECONDS
                self._failures = 0
                logger.warning("prophet circuit opened for %.0fs", CIRCUIT_OPEN_SECONDS)


_circuit = ProphetCircuitBreaker()


def prophet_eligible(rows: list[tuple[date, float]]) -> bool:
    """Enough history with real signal — Prophet on 20 sparse points overfits."""
    if not settings.forecast_enable_prophet:
        return False
    if not prophet_available():
        return False
    _, values = prepare_series(rows)
    if len(values) < MIN_OBS:
        return False
    return sum(1 for v in values if v > 0) >= MIN_NONZERO


def _run_prophet_sync(
    dates: list[date],
    values: list[float],
    holdout: int,
    horizon: int,
) -> ExternalCandidate:
    from prophet import Prophet

    n = len(values)
    train_dates, train_vals = dates[: n - holdout], values[: n - holdout]
    test_vals = values[n - holdout :]

    frame = _to_frame(train_dates, train_vals)
    model = Prophet(
        yearly_seasonality=False,
        weekly_seasonality=True,
        daily_seasonality=False,
        changepoint_prior_scale=0.05,
    )
    model.fit(frame)
    future = model.make_future_dataframe(periods=holdout)
    predicted = model.predict(future)["yhat"].tolist()
    holdout_preds = [float(v) for v in predicted[-holdout:]]
    residuals = [holdout_preds[i] - test_vals[i] for i in range(holdout)]

    full_frame = _to_frame(dates, values)
    full_model = Prophet(
        yearly_seasonality=False,
        weekly_seasonality=True,
        daily_seasonality=False,
        changepoint_prior_scale=0.05,
    )
    full_model.fit(full_frame)
    future_full = full_model.make_future_dataframe(periods=horizon)
    horizon_preds = [max(0.0, float(v)) for v in full_model.predict(future_full)["yhat"].tolist()[-horizon:]]

    return ExternalCandidate(
        name="prophet",
        wmape=round(wmape(holdout_preds, test_vals), 4),
        bias=round(bias_pct(holdout_preds, test_vals), 4),
        residuals=residuals,
        horizon_predictions=horizon_preds,
        params={"holdout": float(holdout)},
    )


def _to_frame(dates: list[date], values: list[float]) -> object:
    import pandas as pd

    return pd.DataFrame({"ds": [d.isoformat() for d in dates], "y": values})


async def try_prophet(
    rows: list[tuple[date, float]],
    horizon: int,
    stockout_correction: bool,
) -> ExternalCandidate | None:
    """Best-effort Prophet candidate. Never raises; None means 'not available'."""
    if not prophet_eligible(rows):
        return None
    if _circuit.is_open():
        return None

    prepared_dates, prepared = prepare_series(rows)
    work = prepared
    if stockout_correction:
        work, _ = impute_censored_days(prepared)
    h = holdout_days(len(work))
    if h == 0:
        return None

    start = time.perf_counter()
    try:
        candidate = await asyncio.wait_for(
            asyncio.to_thread(
                _run_prophet_sync,
                prepared_dates,
                work,
                h,
                horizon,
            ),
            timeout=PROPHET_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        _circuit.record_failure()
        logger.warning("prophet timed out after %.1fs", PROPHET_TIMEOUT_SECONDS)
        return None
    except Exception as exc:
        _circuit.record_failure()
        logger.warning("prophet failed: %s", exc)
        return None

    _circuit.record_success()
    logger.info(
        "prophet candidate ready wmape=%.3f latency_ms=%.0f",
        candidate.wmape,
        (time.perf_counter() - start) * 1000,
    )
    return candidate
