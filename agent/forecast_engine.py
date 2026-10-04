"""Forecast engine selection, safety gates, and promotion.

Engines (canonical names — legacy aliases in ``_ALIASES`` map onto these):

    ensemble    model ensemble (agent/forecast.py) served to Risk / PO Draft
    exponential legacy exponential smoothing — kill-switch / demotion target
    shadow      run + persist both engines, serve exponential (A/B measurement)

Resolution precedence (``resolve_engine``):

    FORECAST_ENGINE_OVERRIDE  global kill switch / force, wins over everything
    merchants.forecast_engine per-merchant flag (admin endpoint or promotion)
    FORECAST_ENGINE_DEFAULT   fallback for merchants with no stored flag

Auto-promotion (``auto_promote_merchants``) flips ``shadow -> ensemble`` only
when every safety gate passes and the merchant is inside the rollout cohort.
Evaluation uses hold-out replay of both engines on the merchant's own sales
history (tier-0 ensemble only — deterministic, no external calls).
"""

from __future__ import annotations

import logging
import math
import statistics
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from agent.config import settings
from agent.db import async_session_factory
from agent.forecast import build_ensemble, legacy_predict_daily
from agent.models import Forecast, Merchant, SalesHistory, Sku
from shared.metrics import metrics

logger = logging.getLogger(__name__)

ENGINE_ENSEMBLE = "ensemble"
ENGINE_EXPONENTIAL = "exponential"
ENGINE_SHADOW = "shadow"
VALID_ENGINES = frozenset({ENGINE_ENSEMBLE, ENGINE_EXPONENTIAL, ENGINE_SHADOW})

_ALIASES = {
    "exp_smoothing_v1": ENGINE_EXPONENTIAL,
    "ensemble_v2": ENGINE_ENSEMBLE,
    "v1": ENGINE_EXPONENTIAL,
}

# --- Promotion safety gates (all must pass before auto-promotion) ----------
SHADOW_MIN_DAYS = 14
MAPE_RATIO_MAX = 0.85  # ensemble MAPE must be <= 85% of exponential MAPE
BIAS_MAX = 0.08  # |systematic bias| on high-velocity SKUs
COVERAGE_MIN = 0.45  # share of hold-out days inside the 50% interval
MIN_EVALUABLE_SKUS = 3
EVAL_HOLDOUT_DAYS = 14
EVAL_MIN_TRAIN_DAYS = 14
HIGH_VELOCITY_DAILY = 5.0  # units/day — above this a SKU counts as high-velocity
Z_50 = 0.6745  # normal quantile for a 50% interval
V1_MODEL_VERSION = "exp_smoothing_v1"
V2_MODEL_VERSION = "ensemble_v2"


# ---------------------------------------------------------------------------
# Engine resolution
# ---------------------------------------------------------------------------


def canonical_engine(value: str | None) -> str | None:
    """Map a raw engine string (legacy names included) onto a canonical one."""
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if not normalized:
        return None
    normalized = _ALIASES.get(normalized, normalized)
    return normalized if normalized in VALID_ENGINES else None


def resolve_engine(*, merchant_engine: str | None, merchant_id: int | None = None) -> tuple[str, str]:
    """Resolve the engine for a run. Returns ``(engine, source)``.

    ``merchant_id`` is accepted for call-site clarity; selection is driven by
    the override flag, the merchant flag, then the configured default — no
    database access (callers already hold the Merchant row).
    """
    override = canonical_engine(settings.forecast_engine_override)
    if override is not None:
        return override, "global_override"
    merchant = canonical_engine(merchant_engine)
    if merchant is not None:
        return merchant, "merchant"
    default = canonical_engine(settings.forecast_engine_default)
    if default is not None:
        return default, "default"
    # Never guess ensemble from a bad env value.
    return ENGINE_SHADOW, "fallback"


def in_rollout_cohort(merchant_id: int | None, percent: int | None = None) -> bool:
    """Deterministic gradual-rollout gate: ``id % 100 < percent``."""
    if percent is None:
        percent = settings.forecast_rollout_percent
    if percent >= 100:
        return True
    if percent <= 0 or merchant_id is None:
        return False
    return (abs(int(merchant_id)) % 100) < percent


# ---------------------------------------------------------------------------
# Hold-out evaluation (pure)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SkuHoldoutMetrics:
    sku_id: int
    avg_daily: float
    mape_ensemble: float
    mape_v1: float
    bias_ensemble: float  # signed fraction: (sum_pred - sum_actual) / sum_actual
    coverage_p50: float  # share of hold-out days inside the 50% interval
    positive_days: int  # hold-out days with actual > 0 (MAPE weight)
    actual_sum: float  # hold-out demand (bias weight)
    holdout_days: int
    evaluable: bool
    reason: str = ""


@dataclass(frozen=True)
class MerchantHoldoutSummary:
    evaluable_skus: int
    total_skus: int
    mape_ensemble: float
    mape_v1: float
    mape_ratio: float | None  # None when exponential MAPE is 0 (no proof possible)
    bias_high_velocity: float | None  # None when no high-velocity SKU exists
    coverage_p50: float
    high_velocity_skus: int


def _not_evaluable(sku_id: int, reason: str) -> SkuHoldoutMetrics:
    return SkuHoldoutMetrics(
        sku_id=sku_id,
        avg_daily=0.0,
        mape_ensemble=0.0,
        mape_v1=0.0,
        bias_ensemble=0.0,
        coverage_p50=0.0,
        positive_days=0,
        actual_sum=0.0,
        holdout_days=0,
        evaluable=False,
        reason=reason,
    )


def evaluate_sku_holdout(
    rows: list[tuple[date, float]],
    holdout: int = EVAL_HOLDOUT_DAYS,
    sku_id: int = 0,
) -> SkuHoldoutMetrics:
    """Replay both engines on a hold-out window of one SKU's history."""
    if holdout < 1:
        return _not_evaluable(sku_id, "no_holdout")
    asc = sorted(rows, key=lambda r: r[0])
    values = [float(v) for _, v in asc]
    if len(values) < holdout + EVAL_MIN_TRAIN_DAYS:
        return _not_evaluable(sku_id, "insufficient_history")

    train_rows = asc[:-holdout]
    train_values = values[:-holdout]
    actual = values[-holdout:]

    if not any(a > 0 for a in actual):
        return _not_evaluable(sku_id, "no_positive_demand")

    v1_point = legacy_predict_daily(train_values)
    v1_pred = [v1_point] * holdout

    try:
        bundle = build_ensemble(
            train_rows,
            holdout,
            stockout_correction=settings.forecast_stockout_correction,
        )
    except Exception:
        return _not_evaluable(sku_id, "ensemble_error")

    ens = list(bundle.predictions[:holdout])
    if len(ens) < holdout:
        return _not_evaluable(sku_id, "ensemble_short")

    def _mape(pred: list[float]) -> float:
        ape = [abs(p - a) / a for p, a in zip(pred, actual, strict=False) if a > 0]
        return statistics.fmean(ape) if ape else 0.0

    actual_sum = sum(actual)
    covered = 0
    for i, point in enumerate(ens, start=1):
        sigma_h = min(max(bundle.sigma * math.sqrt(i), bundle.sigma), 2 * bundle.sigma)
        lo = max(0.0, point - Z_50 * sigma_h)
        hi = point + Z_50 * sigma_h
        if lo <= actual[i - 1] <= hi:
            covered += 1

    return SkuHoldoutMetrics(
        sku_id=sku_id,
        avg_daily=statistics.fmean(values),
        mape_ensemble=_mape(ens),
        mape_v1=_mape(v1_pred),
        bias_ensemble=((sum(ens) - actual_sum) / actual_sum) if actual_sum > 0 else 0.0,
        coverage_p50=covered / holdout,
        positive_days=sum(1 for a in actual if a > 0),
        actual_sum=actual_sum,
        holdout_days=holdout,
        evaluable=True,
    )


def summarize_holdout(
    per_sku: list[SkuHoldoutMetrics],
    high_velocity_daily: float = HIGH_VELOCITY_DAILY,
) -> MerchantHoldoutSummary:
    """Pool per-SKU hold-out metrics (demand-weighted where it matters)."""
    total = len(per_sku)
    ev = [m for m in per_sku if m.evaluable]
    if not ev:
        return MerchantHoldoutSummary(
            evaluable_skus=0,
            total_skus=total,
            mape_ensemble=0.0,
            mape_v1=0.0,
            mape_ratio=None,
            bias_high_velocity=None,
            coverage_p50=0.0,
            high_velocity_skus=0,
        )

    pos_total = sum(m.positive_days for m in ev) or 1
    mape_ens = sum(m.mape_ensemble * m.positive_days for m in ev) / pos_total
    mape_v1 = sum(m.mape_v1 * m.positive_days for m in ev) / pos_total
    ratio = (mape_ens / mape_v1) if mape_v1 > 0 else None

    hv = [m for m in ev if m.avg_daily >= high_velocity_daily and m.actual_sum > 0]
    bias_hv: float | None = None
    if hv:
        den = sum(m.actual_sum for m in hv)
        if den > 0:
            bias_hv = sum(m.bias_ensemble * m.actual_sum for m in hv) / den

    days_total = sum(m.holdout_days for m in ev) or 1
    coverage = sum(m.coverage_p50 * m.holdout_days for m in ev) / days_total

    return MerchantHoldoutSummary(
        evaluable_skus=len(ev),
        total_skus=total,
        mape_ensemble=mape_ens,
        mape_v1=mape_v1,
        mape_ratio=ratio,
        bias_high_velocity=bias_hv,
        coverage_p50=coverage,
        high_velocity_skus=len(hv),
    )


# ---------------------------------------------------------------------------
# Safety gates (pure)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GateCheck:
    name: str
    passed: bool
    value: float | None
    threshold: float
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "value": self.value,
            "threshold": self.threshold,
            "detail": self.detail,
        }


def build_gates(shadow_days: int, summary: MerchantHoldoutSummary) -> list[GateCheck]:
    """The full promotion gate set — every check must pass."""
    gates: list[GateCheck] = [
        GateCheck(
            name="shadow_days",
            passed=shadow_days >= SHADOW_MIN_DAYS,
            value=float(shadow_days),
            threshold=float(SHADOW_MIN_DAYS),
            detail=f"{shadow_days} paired shadow days observed",
        ),
        GateCheck(
            name="min_evaluable_skus",
            passed=summary.evaluable_skus >= MIN_EVALUABLE_SKUS,
            value=float(summary.evaluable_skus),
            threshold=float(MIN_EVALUABLE_SKUS),
            detail=f"{summary.evaluable_skus}/{summary.total_skus} SKUs had enough history",
        ),
    ]

    if summary.mape_ratio is None:
        gates.append(
            GateCheck(
                name="mape_ratio",
                passed=False,
                value=None,
                threshold=MAPE_RATIO_MAX,
                detail="no comparable hold-out (exponential MAPE is 0 or no evaluable SKUs)",
            )
        )
    else:
        gates.append(
            GateCheck(
                name="mape_ratio",
                passed=summary.mape_ratio <= MAPE_RATIO_MAX,
                value=round(summary.mape_ratio, 4),
                threshold=MAPE_RATIO_MAX,
                detail=(f"ensemble mape={summary.mape_ensemble:.4f} vs exponential mape={summary.mape_v1:.4f}"),
            )
        )

    if summary.bias_high_velocity is None:
        gates.append(
            GateCheck(
                name="high_velocity_bias",
                passed=True,
                value=None,
                threshold=BIAS_MAX,
                detail="no high-velocity SKUs in scope — vacuous pass",
            )
        )
    else:
        gates.append(
            GateCheck(
                name="high_velocity_bias",
                passed=abs(summary.bias_high_velocity) <= BIAS_MAX,
                value=round(summary.bias_high_velocity, 4),
                threshold=BIAS_MAX,
                detail=f"pooled signed bias across {summary.high_velocity_skus} high-velocity SKUs",
            )
        )

    gates.append(
        GateCheck(
            name="p50_coverage",
            passed=summary.coverage_p50 >= COVERAGE_MIN,
            value=round(summary.coverage_p50, 4),
            threshold=COVERAGE_MIN,
            detail="share of hold-out days inside the ensemble 50% interval",
        )
    )
    return gates


# ---------------------------------------------------------------------------
# Evaluation (DB-backed)
# ---------------------------------------------------------------------------


@dataclass
class PromotionEvaluation:
    merchant_id: int
    engine_before: str
    gates: list[GateCheck]
    shadow_days: int
    summary: MerchantHoldoutSummary
    cohort: bool
    promoted: bool = False

    @property
    def gates_passed(self) -> bool:
        return all(g.passed for g in self.gates)

    @property
    def blocked_by(self) -> list[str]:
        return [g.name for g in self.gates if not g.passed]

    @property
    def mape_ratio(self) -> float | None:
        return self.summary.mape_ratio

    def to_dict(self) -> dict[str, Any]:
        return {
            "merchant_id": self.merchant_id,
            "engine_before": self.engine_before,
            "gates": [g.to_dict() for g in self.gates],
            "gates_passed": self.gates_passed,
            "blocked_by": self.blocked_by,
            "shadow_days": self.shadow_days,
            "mape_ratio": self.summary.mape_ratio,
            "mape_ensemble": round(self.summary.mape_ensemble, 4),
            "mape_exponential": round(self.summary.mape_v1, 4),
            "bias_high_velocity": self.summary.bias_high_velocity,
            "coverage_p50": round(self.summary.coverage_p50, 4),
            "evaluable_skus": self.summary.evaluable_skus,
            "high_velocity_skus": self.summary.high_velocity_skus,
            "cohort": self.cohort,
            "promoted": self.promoted,
        }


async def count_shadow_days(merchant_id: int) -> int:
    """Days where BOTH engines persisted a forecast for this merchant."""
    day = func.date_trunc("day", Forecast.created_at)
    pairs = (
        select(day.label("day"), Forecast.model_version)
        .join(Sku, Sku.id == Forecast.sku_id)
        .where(
            Sku.merchant_id == merchant_id,
            Forecast.model_version.in_([V1_MODEL_VERSION, V2_MODEL_VERSION]),
        )
        .distinct()
        .subquery()
    )
    stmt = select(func.count()).select_from(
        select(pairs.c.day)
        .group_by(pairs.c.day)
        .having(func.count(func.distinct(pairs.c.model_version)) >= 2)
        .subquery()
    )
    async with async_session_factory() as session:
        result = await session.execute(stmt)
        return int(result.scalar_one())


async def load_merchant_holdout_metrics(
    merchant_id: int,
    holdout: int = EVAL_HOLDOUT_DAYS,
) -> list[SkuHoldoutMetrics]:
    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(SalesHistory.sku_id, SalesHistory.date, SalesHistory.units_sold)
                .join(Sku, Sku.id == SalesHistory.sku_id)
                .where(Sku.merchant_id == merchant_id)
                .order_by(SalesHistory.sku_id, SalesHistory.date)
            )
        ).all()

    by_sku: dict[int, list[tuple[date, float]]] = {}
    for sku_id, day, units in rows:
        by_sku.setdefault(sku_id, []).append((day, float(units)))

    return [evaluate_sku_holdout(history, holdout=holdout, sku_id=sku_id) for sku_id, history in by_sku.items()]


async def evaluate_merchant(
    merchant_id: int,
    engine_before: str = ENGINE_SHADOW,
    cohort: bool = True,
) -> PromotionEvaluation:
    per_sku = await load_merchant_holdout_metrics(merchant_id)
    summary = summarize_holdout(per_sku)
    shadow_days = await count_shadow_days(merchant_id)
    gates = build_gates(shadow_days, summary)
    return PromotionEvaluation(
        merchant_id=merchant_id,
        engine_before=engine_before,
        gates=gates,
        shadow_days=shadow_days,
        summary=summary,
        cohort=cohort,
    )


async def _flip_engine(merchant_id: int, engine: str) -> None:
    async with async_session_factory() as session:
        row = await session.get(Merchant, merchant_id)
        if row is None:
            return
        row.forecast_engine = engine
        row.forecast_promoted_at = datetime.now(UTC) if engine == ENGINE_ENSEMBLE else None
        await session.commit()


def _set_promotion_status_gauges(merchant_id: int, engine: str) -> None:
    for candidate in sorted(VALID_ENGINES):
        metrics.gauge(
            "forecast_promotion_status",
            1.0 if candidate == engine else 0.0,
            merchant=str(merchant_id),
            engine=candidate,
        )


async def auto_promote_merchants() -> list[PromotionEvaluation]:
    """Daily job: evaluate every shadow merchant; promote the ones that pass."""
    from agent.audit import log

    async with async_session_factory() as session:
        result = await session.execute(select(Merchant).where(Merchant.forecast_engine == ENGINE_SHADOW))
        merchants = [m for m in result.scalars().all() if m.id not in (None, 0)]

    evaluations: list[PromotionEvaluation] = []
    for merchant in merchants:
        cohort = in_rollout_cohort(merchant.id)
        evaluation = await evaluate_merchant(
            merchant.id,
            engine_before=merchant.forecast_engine,
            cohort=cohort,
        )

        if evaluation.gates_passed and cohort:
            await _flip_engine(merchant.id, ENGINE_ENSEMBLE)
            evaluation.promoted = True
            await log(
                action="forecast_engine_promoted",
                details={
                    "merchant_id": merchant.id,
                    "engine": ENGINE_ENSEMBLE,
                    "source": "auto_promotion",
                    "mape_ratio": evaluation.summary.mape_ratio,
                    "shadow_days": evaluation.shadow_days,
                },
            )
            logger.info(
                "forecast engine auto-promoted merchant=%s engine=ensemble mape_ratio=%s shadow_days=%s",
                merchant.id,
                evaluation.summary.mape_ratio,
                evaluation.shadow_days,
            )
        elif evaluation.gates_passed and not cohort:
            logger.info(
                "forecast engine gates passed for merchant=%s but cohort excludes it (rollout %s%%)",
                merchant.id,
                settings.forecast_rollout_percent,
            )

        evaluations.append(evaluation)
        if evaluation.summary.mape_ratio is not None:
            metrics.gauge("forecast_mape_ratio", evaluation.summary.mape_ratio, merchant=str(merchant.id))
        _set_promotion_status_gauges(
            merchant.id,
            ENGINE_ENSEMBLE if evaluation.promoted else merchant.forecast_engine,
        )

    return evaluations


# ---------------------------------------------------------------------------
# Weekly engine comparison report
# ---------------------------------------------------------------------------


async def build_weekly_engine_report(week_start: date) -> dict[str, Any]:
    """Compare engines over the last week: row counts + gate snapshots."""
    week_end = week_start + timedelta(days=7)

    async with async_session_factory() as session:
        merchants = [m for m in (await session.execute(select(Merchant))).scalars().all() if m.id not in (None, 0)]
        engines = {m.id: m.forecast_engine for m in merchants}
        row_counts: dict[int, dict[str, int]] = {}
        for merchant in merchants:
            counts = (
                await session.execute(
                    select(Forecast.model_version, func.count(Forecast.id))
                    .join(Sku, Sku.id == Forecast.sku_id)
                    .where(
                        Sku.merchant_id == merchant.id,
                        Forecast.created_at >= week_start,
                        Forecast.created_at < week_end,
                    )
                    .group_by(Forecast.model_version)
                )
            ).all()
            row_counts[merchant.id] = {version: int(count) for version, count in counts}

    merchants_payload: list[dict[str, Any]] = []
    for merchant_id, engine in sorted(engines.items()):
        entry: dict[str, Any] = {
            "merchant_id": merchant_id,
            "engine": engine,
            "ensemble_rows": row_counts.get(merchant_id, {}).get(V2_MODEL_VERSION, 0),
            "exponential_rows": row_counts.get(merchant_id, {}).get(V1_MODEL_VERSION, 0),
        }
        if engine == ENGINE_SHADOW:
            evaluation = await evaluate_merchant(
                merchant_id,
                engine_before=engine,
                cohort=in_rollout_cohort(merchant_id),
            )
            entry["mape_ratio"] = evaluation.summary.mape_ratio
            entry["coverage_p50"] = round(evaluation.summary.coverage_p50, 4)
            entry["gates_passed"] = evaluation.gates_passed
            entry["blocked_by"] = evaluation.blocked_by
            if evaluation.summary.mape_ratio is not None:
                metrics.gauge(
                    "forecast_mape_ratio",
                    evaluation.summary.mape_ratio,
                    merchant=str(merchant_id),
                )
        merchants_payload.append(entry)

    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "merchants": merchants_payload,
    }


async def send_weekly_engine_report(week_start: date) -> dict[str, Any]:
    """Build the weekly report, ship it to Slack + the audit log."""
    from agent.audit import log
    from shared.slack import send_slack

    report = await build_weekly_engine_report(week_start)

    lines = [
        f"Forecast Engine Report ({report['week_start']} to {report['week_end']})",
        "=" * 50,
    ]
    for entry in report["merchants"]:
        lines.append(
            f"  merchant {entry['merchant_id']}: engine={entry['engine']} "
            f"ensemble_rows={entry['ensemble_rows']} exponential_rows={entry['exponential_rows']}"
        )
        if "mape_ratio" in entry:
            ratio = entry["mape_ratio"]
            lines.append(
                f"    mape_ratio={ratio if ratio is None else round(ratio, 3)} "
                f"coverage_p50={entry['coverage_p50']} "
                f"gates_passed={entry['gates_passed']} blocked_by={entry['blocked_by']}"
            )
    if not report["merchants"]:
        lines.append("  no merchants found")

    logger.info("weekly forecast engine report: %s", " | ".join(lines[2:]) or "empty")
    if settings.slack_webhook_url:
        await send_slack(settings.slack_webhook_url, "\n".join(lines))
    await log(action="weekly_forecast_engine_report", details=report)
    return report
