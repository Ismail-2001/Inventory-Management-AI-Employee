"""Forecasting engine — legacy exponential smoothing (v1) + ensemble (v2).

All functions here are pure (no I/O, no clock, no DB) so every model is
unit-testable in isolation. The ensemble selects the best model per SKU via
hold-out backtesting (wMAPE) and always returns confidence intervals
alongside the point forecast.

Model tiers:
    ses             simple exponential smoothing — the legacy baseline
    holt            damped Holt linear trend (trending SKUs)
    seasonal_holt   7-day additive decomposition + Holt (weekly seasonality)
    croston         Croston/SBA for intermittent demand (sparse SKUs)
    mean            naive prefix average (floor candidate)
    prophet         optional external candidate (agent/forecast_prophet.py)

Selection: fit every candidate on the train split, score on the hold-out
window with wMAPE, take the winner (blend with runner-up when within 10%
relative), refit on the full series, then derive p10/p90 from robust
hold-out residual spread.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

MAX_SERIES_DAYS = 730
WEEKLY_STRENGTH_THRESHOLD = 0.30
BLEND_RELATIVE_TOLERANCE = 0.10
ALPHA_GRID: tuple[float, ...] = (0.1, 0.2, 0.3, 0.5)
HOLT_ALPHA_GRID: tuple[float, ...] = (0.2, 0.3, 0.5)
HOLT_BETA_GRID: tuple[float, ...] = (0.05, 0.1, 0.2)
DAMPING_PHI = 0.9
INTERMITTENT_ZERO_SHARE = 0.6
INTERMITTENT_MIN_NONZERO = 14


def exponential_smoothing(values: list[float], alpha: float = 0.3) -> float:
    if not values:
        return 0.0
    smoothed = values[0]
    for v in values[1:]:
        smoothed = alpha * v + (1 - alpha) * smoothed
    return smoothed


def legacy_predict_daily(values: list[float]) -> float:
    """Exact v1 point forecast: max(SES(alpha=0.3), mean * 0.5)."""
    if not values:
        return 0.0
    return max(exponential_smoothing(values), (sum(values) / len(values)) * 0.5)


# ---------------------------------------------------------------------------
# Series preparation & diagnosis
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SeriesDiagnosis:
    n_obs: int
    zero_share: float
    intermittent: bool
    weekly_seasonality: bool
    trend_slope: float


def prepare_series(rows: Sequence[tuple[date, float]]) -> tuple[list[date], list[float]]:
    """Sort ascending, de-duplicate, and 0-fill calendar gaps."""
    if not rows:
        return [], []
    ordered = sorted(rows, key=lambda r: r[0])
    values_by_date: dict[date, float] = {}
    for d, v in ordered:
        values_by_date[d] = float(v)
    start = min(values_by_date)
    end = max(values_by_date)
    span = (end - start).days + 1
    if span > MAX_SERIES_DAYS:
        start = end - timedelta(days=MAX_SERIES_DAYS - 1)
    dates: list[date] = []
    values: list[float] = []
    current = start
    while current <= end:
        dates.append(current)
        values.append(values_by_date.get(current, 0.0))
        current += timedelta(days=1)
    return dates, values


def _weekly_strength(values: Sequence[float]) -> float:
    """Spread of day-of-week phase means relative to overall mean (0 if flat)."""
    n = len(values)
    if n < 14:
        return 0.0
    overall = sum(values) / n
    if overall <= 0:
        return 0.0
    phases: list[list[float]] = [[] for _ in range(7)]
    for i, v in enumerate(values):
        phases[i % 7].append(v)
    means = [sum(p) / len(p) for p in phases if p]
    if not means:
        return 0.0
    return (max(means) - min(means)) / overall


def _trend_slope(values: Sequence[float]) -> float:
    """Least-squares slope per day."""
    n = len(values)
    if n < 3:
        return 0.0
    mean_x = (n - 1) / 2.0
    mean_y = sum(values) / n
    num = sum((i - mean_x) * (v - mean_y) for i, v in enumerate(values))
    den = sum((i - mean_x) ** 2 for i in range(n))
    return num / den if den else 0.0


def diagnose(values: Sequence[float]) -> SeriesDiagnosis:
    n = len(values)
    if n == 0:
        return SeriesDiagnosis(0, 0.0, True, False, 0.0)
    nonzero = sum(1 for v in values if v > 0)
    zero_share = (n - nonzero) / n
    intermittent = zero_share >= INTERMITTENT_ZERO_SHARE or nonzero < INTERMITTENT_MIN_NONZERO
    return SeriesDiagnosis(
        n_obs=n,
        zero_share=round(zero_share, 3),
        intermittent=intermittent,
        weekly_seasonality=_weekly_strength(values) >= WEEKLY_STRENGTH_THRESHOLD,
        trend_slope=round(_trend_slope(values), 4),
    )


def impute_censored_days(values: Sequence[float]) -> tuple[list[float], int]:
    """Un-constrain demand on probable stockout days.

    A zero-sales day is treated as censored only when it is bracketed by
    non-zero sales within ±7 days and the local window is active (≥3 non-zero
    days). Dead SKUs and leading/trailing zero runs are left untouched.
    """
    n = len(values)
    if n == 0 or all(v == 0 for v in values):
        return list(values), 0
    result = list(values)
    imputed = 0
    for i, v in enumerate(values):
        if v != 0:
            continue
        lo = max(0, i - 7)
        hi = min(n, i + 8)
        window = values[lo:hi]
        nonzero = [w for w in window if w > 0]
        if len(nonzero) < 3:
            continue
        before = any(w > 0 for w in values[lo:i])
        after = any(w > 0 for w in values[i + 1 : hi])
        if before and after:
            result[i] = statistics.fmean(nonzero)
            imputed += 1
    return result, imputed


# ---------------------------------------------------------------------------
# Model fitting — every fitter returns a FittedModel
# ---------------------------------------------------------------------------


@dataclass
class FittedModel:
    name: str
    predict: Callable[[int], list[float]]
    fitted_one_step: list[float]
    params: dict[str, float]


def _one_step_mse(values: Sequence[float], fitter: Callable[[list[float]], FittedModel]) -> float:
    if len(values) < 3:
        return math.inf
    fit = fitter(list(values))
    preds = fit.fitted_one_step
    errs = [(values[i] - preds[i]) ** 2 for i in range(min(len(values), len(preds))) if i >= 1]
    return sum(errs) / len(errs) if errs else math.inf


def fit_mean(values: list[float]) -> FittedModel:
    prefix = list(values)

    def predict(h: int) -> list[float]:
        m = statistics.fmean(prefix) if prefix else 0.0
        return [m] * h

    fitted: list[float] = []
    running_sum = 0.0
    for i, v in enumerate(prefix):
        fitted.append(v if i == 0 else running_sum / i)
        running_sum += v
    return FittedModel("mean", predict, fitted, {"mean": statistics.fmean(prefix) if prefix else 0.0})


def _ses_path(values: Sequence[float], alpha: float) -> list[float]:
    if not values:
        return []
    fitted = [values[0]]
    for v in values[1:]:
        fitted.append(alpha * v + (1 - alpha) * fitted[-1])
    return fitted


def fit_ses(values: list[float], alpha: float | None = None) -> FittedModel:
    if not values:
        return FittedModel("ses", lambda h: [0.0] * h, [], {"alpha": 0.3})
    chosen = alpha
    if chosen is None:
        chosen = min(ALPHA_GRID, key=lambda a: _one_step_mse(values, lambda xs: _ses_fitted(xs, a)))
    fitted = _ses_path(values, chosen)
    level = fitted[-1]

    def predict(h: int) -> list[float]:
        return [level] * h

    return FittedModel("ses", predict, fitted, {"alpha": chosen})


def _ses_fitted(values: list[float], alpha: float) -> FittedModel:
    fitted = _ses_path(values, alpha)
    return FittedModel("ses", lambda h: [fitted[-1] if fitted else 0.0] * h, fitted, {"alpha": alpha})


def _holt_state(values: Sequence[float], alpha: float, beta: float, phi: float) -> tuple[list[float], float, float]:
    """One-step fitted values plus terminal (level, trend) state."""
    if not values:
        return [], 0.0, 0.0
    level = values[0]
    trend = values[1] - values[0] if len(values) > 1 else 0.0
    fitted: list[float] = [level]
    for t in range(1, len(values)):
        pred = level + phi * trend
        fitted.append(pred)
        prev_level = level
        level = alpha * values[t] + (1 - alpha) * (level + phi * trend)
        trend = beta * (level - prev_level) + (1 - beta) * phi * trend
    return fitted, level, trend


def _holt_path(values: Sequence[float], alpha: float, beta: float, phi: float) -> list[float]:
    return _holt_state(values, alpha, beta, phi)[0]


def fit_holt(values: list[float], alpha: float | None = None, beta: float | None = None) -> FittedModel:
    phi = DAMPING_PHI
    if not values:
        return FittedModel("holt", lambda h: [0.0] * h, [], {"alpha": 0.3, "beta": 0.1, "phi": phi})
    chosen_alpha, chosen_beta = alpha, beta
    if chosen_alpha is None or chosen_beta is None:
        combos = [(a, b) for a in HOLT_ALPHA_GRID for b in HOLT_BETA_GRID]
        chosen_alpha, chosen_beta = min(
            combos, key=lambda ab: _one_step_mse(values, lambda xs: _holt_fitted(xs, ab[0], ab[1], phi))
        )
    fitted, level, trend = _holt_state(values, chosen_alpha, chosen_beta, phi)

    def predict(h: int) -> list[float]:
        return [max(0.0, level + trend * phi * (1 - phi**i) / (1 - phi)) for i in range(1, h + 1)]

    return FittedModel("holt", predict, fitted, {"alpha": chosen_alpha, "beta": chosen_beta, "phi": phi})


def _holt_fitted(values: list[float], alpha: float, beta: float, phi: float) -> FittedModel:
    fitted = _holt_path(values, alpha, beta, phi)
    return FittedModel("holt", lambda h: fitted[-1:] * h, fitted, {"alpha": alpha, "beta": beta})


def _seasonal_indices(values: Sequence[float]) -> list[float]:
    phases: list[list[float]] = [[] for _ in range(7)]
    for i, v in enumerate(values):
        phases[i % 7].append(v)
    means = [statistics.fmean(p) if p else 0.0 for p in phases]
    center = statistics.fmean(means)
    return [m - center for m in means]


def fit_seasonal(values: list[float], period: int = 7) -> FittedModel | None:
    if len(values) < period * 2:
        return None
    indices = _seasonal_indices(values)
    deseason = [values[i] - indices[i % period] for i in range(len(values))]
    base = fit_holt(deseason)
    base_alpha = float(base.params.get("alpha", 0.3))
    base_beta = float(base.params.get("beta", 0.1))
    fitted = [
        _holt_path(deseason, base_alpha, base_beta, DAMPING_PHI)[i] + indices[i % period] for i in range(len(values))
    ]
    n = len(values)

    def predict(h: int) -> list[float]:
        raw = base.predict(h)
        return [max(0.0, raw[i] + indices[(n + i) % period]) for i in range(h)]

    return FittedModel(
        "seasonal_holt", predict, fitted, {"alpha": base_alpha, "beta": base_beta, "period": float(period)}
    )


def fit_croston(values: list[float], alpha: float = 0.2) -> FittedModel:
    """Croston with Syntetos-Boylan correction — constant rate per day."""
    q = 0.0
    p = 0.0
    last_nonzero: int | None = None
    rate = 0.0
    fitted: list[float] = []
    for t, v in enumerate(values):
        fitted.append(rate)
        if v > 0:
            if last_nonzero is None:
                q, p = v, 1.0
            else:
                interval = t - last_nonzero
                q = alpha * v + (1 - alpha) * q
                p = alpha * interval + (1 - alpha) * p
            last_nonzero = t
            if p > 0 and q > 0:
                rate = (q / p) * (1 - alpha / 2)
    params = {"alpha": alpha, "rate": rate}

    def predict(h: int) -> list[float]:
        return [rate] * h

    return FittedModel("croston", predict, fitted, params)


# ---------------------------------------------------------------------------
# Hold-out scoring
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelScore:
    name: str
    wmape: float
    bias: float
    residuals: list[float]


def holdout_days(n: int) -> int:
    if n >= 60:
        return 14
    if n >= 30:
        return 7
    if n >= 21:
        return 5
    if n >= 14:
        return 3
    return 0


def wmape(predicted: Sequence[float], actual: Sequence[float]) -> float:
    if not actual:
        return 0.0
    err = sum(abs(p - a) for p, a in zip(predicted, actual, strict=False))
    scale = max(sum(abs(a) for a in actual), 1.0)
    return err / scale


def bias_pct(predicted: Sequence[float], actual: Sequence[float]) -> float:
    if not actual:
        return 0.0
    err = sum(p - a for p, a in zip(predicted, actual, strict=False))
    scale = max(sum(actual), 1.0)
    return err / scale


def score_fit(fit: FittedModel, holdout: Sequence[float]) -> ModelScore:
    preds = fit.predict(len(holdout))
    residuals = [preds[i] - holdout[i] for i in range(len(holdout))]
    return ModelScore(
        name=fit.name,
        wmape=round(wmape(preds, holdout), 4),
        bias=round(bias_pct(preds, holdout), 4),
        residuals=residuals,
    )


# ---------------------------------------------------------------------------
# Confidence intervals
# ---------------------------------------------------------------------------


def robust_sigma(residuals: Sequence[float]) -> float:
    if len(residuals) < 3:
        return 0.0
    med = statistics.median(residuals)
    mad = statistics.median([abs(r - med) for r in residuals])
    return 1.4826 * mad


def confidence_band(p50: Sequence[float], sigma: float) -> tuple[list[float], list[float]]:
    """p10/p90 grow as sqrt(horizon), clipped to [sigma, 2*sigma]."""
    p10: list[float] = []
    p90: list[float] = []
    for i, point in enumerate(p50, start=1):
        sigma_h = min(max(sigma * math.sqrt(i), sigma), 2 * sigma)
        p10.append(max(0.0, point - 1.2816 * sigma_h))
        p90.append(point + 1.2816 * sigma_h)
    return p10, p90


# ---------------------------------------------------------------------------
# Ensemble entry point
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExternalCandidate:
    """Scored horizon path produced outside this module (Prophet)."""

    name: str
    wmape: float
    bias: float
    residuals: list[float]
    horizon_predictions: list[float]
    params: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ForecastBundle:
    predictions: list[float]
    p10: list[float]
    p90: list[float]
    model: str
    wmape: float
    bias: float
    sigma: float
    meta: dict[str, Any]


def _fitter_for(name: str) -> Callable[[list[float]], FittedModel]:
    if name == "ses":
        return fit_ses
    if name == "holt":
        return fit_holt
    if name == "seasonal_holt":
        return fit_seasonal  # type: ignore[return-value]
    if name == "croston":
        return fit_croston
    return fit_mean


def _empty_bundle(horizon: int, reason: str) -> ForecastBundle:
    zeros = [0.0] * horizon
    return ForecastBundle(
        predictions=zeros,
        p10=list(zeros),
        p90=list(zeros),
        model="mean",
        wmape=0.0,
        bias=0.0,
        sigma=0.0,
        meta={"reason": reason},
    )


def build_ensemble(
    rows: Sequence[tuple[date, float]],
    horizon: int,
    *,
    external: ExternalCandidate | None = None,
    stockout_correction: bool = True,
) -> ForecastBundle:
    """Select the best model for this SKU and return point + interval forecasts."""
    horizon = max(1, min(horizon, 365))
    _, values = prepare_series(rows)
    if not values:
        return _empty_bundle(horizon, "no_history")

    work = list(values)
    imputed = 0
    if stockout_correction:
        work, imputed = impute_censored_days(work)
    if all(v == 0 for v in work):
        bundle = _empty_bundle(horizon, "all_zero")
        return ForecastBundle(
            predictions=bundle.predictions,
            p10=bundle.p10,
            p90=bundle.p90,
            model="zero",
            wmape=0.0,
            bias=0.0,
            sigma=0.0,
            meta={"reason": "all_zero", "n_obs": len(work), "imputed_days": 0},
        )

    diag = diagnose(work)
    n = len(work)
    h = holdout_days(n)

    candidate_names: list[str] = ["ses", "holt", "mean", "croston"]
    if diag.weekly_seasonality:
        candidate_names.insert(2, "seasonal_holt")

    scores: list[ModelScore] = []
    if h > 0:
        train, actual = work[: n - h], work[n - h :]
        for name in candidate_names:
            fit = _fitter_for(name)(train)
            if fit is None:
                continue
            scores.append(score_fit(fit, actual))
        if external is not None and len(external.horizon_predictions) > 0:
            scores.append(
                ModelScore(name=external.name, wmape=external.wmape, bias=external.bias, residuals=external.residuals)
            )
    if not scores:
        default = "croston" if diag.intermittent else "ses"
        fit = fit_croston(work) if default == "croston" else fit_ses(work)
        path = [max(0.0, v) for v in fit.predict(horizon)]
        sigma = max(0.1 * max(statistics.fmean(path), 1.0), 0.0)
        p10, p90 = confidence_band(path, sigma)
        return ForecastBundle(
            predictions=path,
            p10=p10,
            p90=p90,
            model=default,
            wmape=0.0,
            bias=0.0,
            sigma=round(sigma, 3),
            meta={
                "candidates": {},
                "holdout_days": 0,
                "n_obs": n,
                "zero_share": diag.zero_share,
                "intermittent": diag.intermittent,
                "weekly_seasonality": diag.weekly_seasonality,
                "imputed_days": imputed,
                "blended": False,
            },
        )

    scores.sort(key=lambda s: s.wmape)
    best = scores[0]
    runner_up = scores[1] if len(scores) > 1 else None

    blend_pair: tuple[ModelScore, ModelScore] | None = None
    if runner_up is not None and runner_up.wmape <= best.wmape * (1 + BLEND_RELATIVE_TOLERANCE):
        blend_pair = (best, runner_up)

    if blend_pair is not None:
        first, second = blend_pair
        w_first = 1.0 / max(first.wmape, 1e-6)
        w_second = 1.0 / max(second.wmape, 1e-6)
        total = w_first + w_second
        path_a = _horizon_path(first.name, work, horizon, external)
        path_b = _horizon_path(second.name, work, horizon, external)
        path = [(w_first * a + w_second * b) / total for a, b in zip(path_a, path_b, strict=False)]
        model_label = f"{first.name}+{second.name}"
        used = first
        blended = True
    else:
        path = _horizon_path(best.name, work, horizon, external)
        model_label = best.name
        used = best
        blended = False

    mean_pred = statistics.fmean(path) if path else 0.0
    sigma_floor = 0.1 * max(mean_pred, 1.0)
    sigma = max(robust_sigma(used.residuals), sigma_floor)
    p10, p90 = confidence_band(path, sigma)

    return ForecastBundle(
        predictions=path,
        p10=p10,
        p90=p90,
        model=model_label,
        wmape=round(used.wmape, 4),
        bias=round(used.bias, 4),
        sigma=round(sigma, 3),
        meta={
            "candidates": {s.name: s.wmape for s in scores},
            "holdout_days": h,
            "n_obs": n,
            "zero_share": diag.zero_share,
            "intermittent": diag.intermittent,
            "weekly_seasonality": diag.weekly_seasonality,
            "imputed_days": imputed,
            "blended": blended,
            "selected": used.name,
        },
    )


def _horizon_path(name: str, work: list[float], horizon: int, external: ExternalCandidate | None) -> list[float]:
    if name == "prophet" and external is not None:
        preds = list(external.horizon_predictions)
        if len(preds) < horizon:
            preds = preds + [preds[-1]] * (horizon - len(preds))
        return [max(0.0, v) for v in preds[:horizon]]
    fit = _fitter_for(name)(work)
    if fit is None:
        return [0.0] * horizon
    return [max(0.0, v) for v in fit.predict(horizon)]
