"""Backtest ensemble_v2 against the v1 legacy forecast on historical sales.

Loads per-SKU sales history, holds out the last N days (optionally repeated
backwards as rolling folds), fits both models on the remaining window, and
reports pooled, per-velocity-tier, and per-SKU accuracy:

    py -3.12 scripts/forecast_backtest.py --holdout 14 --limit 500
    py -3.12 scripts/forecast_backtest.py --holdout 14 --folds 3 --min-history 90
    py -3.12 scripts/forecast_backtest.py --json backtest-report.json

Scoring is calendar-aligned: the actual series for the hold-out horizon is
0-filled across every calendar day after the last training day, so
prediction day i always compares against demand on the same calendar day
(horizon = last test date - last train date, not the number of stored sale
rows). SKUs whose rows omit zero-sale days are therefore scored honestly.

Velocity tiers (computed from each fold's raw training rows):

    intermittent  mean < 1.5 units/day OR >= 30% zero-demand days
    high          mean >= 10 units/day
    medium        everything in between

Requires DATABASE_URL (and optionally FORECAST_* settings) to be set.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from sqlalchemy import select

from agent.db import async_session_factory
from agent.forecast import bias_pct, build_ensemble, legacy_predict_daily, prepare_series, wmape
from agent.models import SalesHistory

TIER_ORDER = ("high", "medium", "intermittent")


@dataclass
class SkuBacktest:
    sku_id: int
    fold: int
    tier: str
    days: int
    v1_wmape: float
    v2_wmape: float
    v1_bias: float
    v2_bias: float
    v1_mase: float
    v2_mase: float
    coverage: float | None
    model: str
    blended: bool
    total_actual: float


@dataclass
class TierStats:
    evaluations: int
    skus: int
    v1_pooled_wmape: float
    v2_pooled_wmape: float
    wmape_delta_pct: float
    v1_mean_bias: float
    v2_mean_bias: float
    interval_coverage: float | None


@dataclass
class Report:
    holdout_days: int
    min_history: int
    folds: int
    skus_tested: int
    evaluations: int
    skus_skipped: int
    v1_pooled_wmape: float
    v2_pooled_wmape: float
    wmape_delta_pct: float
    v1_mean_bias: float
    v2_mean_bias: float
    v1_mean_mase: float
    v2_mean_mase: float
    interval_coverage: float | None
    model_distribution: dict[str, int] = field(default_factory=dict)
    improved: int = 0
    regressed: int = 0
    by_tier: dict[str, TierStats] = field(default_factory=dict)
    per_sku: list[SkuBacktest] = field(default_factory=list)


def classify_tier(train: list[float]) -> str:
    """Velocity tier from the training window (see module docstring)."""
    if not train:
        return "intermittent"
    mean = statistics.fmean(train)
    zero_share = sum(1 for v in train if v <= 0) / len(train)
    if zero_share >= 0.30 or mean < 1.5:
        return "intermittent"
    if mean >= 10.0:
        return "high"
    return "medium"


def _pooled_wmape(rows: list[SkuBacktest], which: str) -> float:
    total_actual = sum(r.total_actual for r in rows)
    if total_actual <= 0:
        return 0.0
    weighted = sum(float(getattr(r, f"{which}_wmape")) * r.total_actual for r in rows)
    return weighted / total_actual


def _mase(train: list[float], errors: list[float]) -> float:
    if len(train) < 2 or not errors:
        return 0.0
    naive = statistics.fmean(abs(train[i] - train[i - 1]) for i in range(1, len(train)))
    if naive <= 0:
        return 0.0
    return statistics.fmean(abs(e) for e in errors) / naive


async def load_history(min_days: int, limit: int) -> dict[int, list[tuple[date, float]]]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(SalesHistory.sku_id, SalesHistory.date, SalesHistory.units_sold).order_by(
                SalesHistory.sku_id, SalesHistory.date
            )
        )
        by_sku: dict[int, list[tuple[date, float]]] = {}
        for sku_id, day, units in result.all():
            by_sku.setdefault(sku_id, []).append((day, float(units)))
    return {sku_id: rows for sku_id, rows in list(by_sku.items())[:limit] if len(rows) >= min_days}


def _tier_stats(rows: list[SkuBacktest]) -> TierStats:
    coverages = [r.coverage for r in rows if r.coverage is not None]
    v1_pooled = _pooled_wmape(rows, "v1")
    v2_pooled = _pooled_wmape(rows, "v2")
    return TierStats(
        evaluations=len(rows),
        skus=len({r.sku_id for r in rows}),
        v1_pooled_wmape=v1_pooled,
        v2_pooled_wmape=v2_pooled,
        wmape_delta_pct=((v2_pooled - v1_pooled) / v1_pooled * 100.0) if v1_pooled > 0 else 0.0,
        v1_mean_bias=statistics.fmean(r.v1_bias for r in rows),
        v2_mean_bias=statistics.fmean(r.v2_bias for r in rows),
        interval_coverage=statistics.fmean(coverages) if coverages else None,
    )


def aligned_actual(train_rows: list[tuple[date, float]], test_rows: list[tuple[date, float]]) -> list[float]:
    """0-filled actual demand for every calendar day after the last train day.

    The horizon runs from the day after the last training day through the
    last test row, so prediction day i always compares against demand on
    the same calendar day (stored rows may skip zero-sale days; the horizon
    therefore equals the calendar span, not ``len(test_rows)``).
    """
    dates, values = prepare_series([*train_rows, *test_rows])
    cutoff = (train_rows[-1][0] - dates[0]).days + 1
    return values[cutoff:]


async def run_backtest(holdout: int, min_history: int, limit: int, folds: int = 1) -> Report:
    history = await load_history(min_history, limit)
    tested: list[SkuBacktest] = []
    skipped = 0

    for sku_id, rows in history.items():
        rows = rows[-min_history:]
        evaluated_this_sku = False

        for fold in range(max(1, folds)):
            end = len(rows) - fold * holdout
            start = end - holdout
            if start < holdout + 7:
                break
            train_rows, test_rows = rows[:start], rows[start:end]

            train = [v for _, v in train_rows]
            actual = aligned_actual(train_rows, test_rows)
            horizon = len(actual)

            v1_point = legacy_predict_daily(train)
            v1_pred = [v1_point] * horizon

            bundle = build_ensemble(train_rows, horizon=horizon)
            v2_pred = bundle.predictions[:horizon]

            total_actual = sum(actual)
            coverage = None
            if bundle.p10 and bundle.p90:
                hits = sum(1 for i in range(horizon) if bundle.p10[i] <= actual[i] <= bundle.p90[i])
                coverage = hits / horizon

            tested.append(
                SkuBacktest(
                    sku_id=sku_id,
                    fold=fold,
                    tier=classify_tier(train),
                    days=len(rows),
                    v1_wmape=wmape(v1_pred, actual),
                    v2_wmape=wmape(v2_pred, actual),
                    v1_bias=bias_pct(v1_pred, actual),
                    v2_bias=bias_pct(v2_pred, actual),
                    v1_mase=_mase(train, [v1_pred[i] - actual[i] for i in range(horizon)]),
                    v2_mase=_mase(train, [v2_pred[i] - actual[i] for i in range(horizon)]),
                    coverage=coverage,
                    model=bundle.model,
                    blended=bundle.meta.get("blended", False),
                    total_actual=total_actual,
                )
            )
            evaluated_this_sku = True

        if not evaluated_this_sku:
            skipped += 1

    dist: dict[str, int] = {}
    for r in tested:
        dist[r.model] = dist.get(r.model, 0) + 1

    coverages = [r.coverage for r in tested if r.coverage is not None]
    v1_pooled = _pooled_wmape(tested, "v1")
    v2_pooled = _pooled_wmape(tested, "v2")

    by_sku: dict[int, list[SkuBacktest]] = {}
    for r in tested:
        by_sku.setdefault(r.sku_id, []).append(r)
    improved = sum(
        1
        for rows in by_sku.values()
        if statistics.fmean(r.v2_wmape for r in rows) < statistics.fmean(r.v1_wmape for r in rows)
    )
    regressed = sum(
        1
        for rows in by_sku.values()
        if statistics.fmean(r.v2_wmape for r in rows) > statistics.fmean(r.v1_wmape for r in rows)
    )

    by_tier = {
        tier: _tier_stats(tier_rows) for tier in TIER_ORDER if (tier_rows := [r for r in tested if r.tier == tier])
    }

    return Report(
        holdout_days=holdout,
        min_history=min_history,
        folds=folds,
        skus_tested=len(by_sku),
        evaluations=len(tested),
        skus_skipped=skipped,
        v1_pooled_wmape=v1_pooled,
        v2_pooled_wmape=v2_pooled,
        wmape_delta_pct=((v2_pooled - v1_pooled) / v1_pooled * 100.0) if v1_pooled > 0 else 0.0,
        v1_mean_bias=statistics.fmean(r.v1_bias for r in tested) if tested else 0.0,
        v2_mean_bias=statistics.fmean(r.v2_bias for r in tested) if tested else 0.0,
        v1_mean_mase=statistics.fmean(r.v1_mase for r in tested) if tested else 0.0,
        v2_mean_mase=statistics.fmean(r.v2_mase for r in tested) if tested else 0.0,
        interval_coverage=statistics.fmean(coverages) if coverages else None,
        model_distribution=dist,
        improved=improved,
        regressed=regressed,
        by_tier=by_tier,
        per_sku=tested,
    )


def render(report: Report) -> str:
    lines = [
        f"backtest: {report.skus_tested} skus tested, {report.skus_skipped} skipped "
        f"({report.evaluations} evaluations: holdout={report.holdout_days}d x {report.folds} folds, "
        f"min_history={report.min_history}d)",
        f"models: {json.dumps(report.model_distribution, sort_keys=True)}",
        "",
        f"{'':14}{'wMAPE':>10}{'bias%':>10}{'MASE':>10}",
        f"{'v1 (legacy)':14}{report.v1_pooled_wmape:>10.4f}{report.v1_mean_bias:>10.2f}{report.v1_mean_mase:>10.4f}",
        f"{'v2 (ensemble)':14}{report.v2_pooled_wmape:>10.4f}{report.v2_mean_bias:>10.2f}{report.v2_mean_mase:>10.4f}",
        f"{'delta':14}{report.wmape_delta_pct:>9.1f}%",
        "",
    ]
    if report.by_tier:
        lines.append("by velocity tier (pooled wMAPE):")
        lines.append(f"  {'tier':<14}{'evals':>6}{'v1':>9}{'v2':>9}{'delta':>9}{'cov':>7}")
        for tier, stats in report.by_tier.items():
            cov = f"{stats.interval_coverage:.2f}" if stats.interval_coverage is not None else "—"
            lines.append(
                f"  {tier:<14}{stats.evaluations:>6}{stats.v1_pooled_wmape:>9.4f}"
                f"{stats.v2_pooled_wmape:>9.4f}{stats.wmape_delta_pct:>8.1f}%{cov:>7}"
            )
        lines.append("")
    lines.append(f"per-sku wins: {report.improved} improved / {report.regressed} regressed")
    if report.interval_coverage is not None:
        lines.append(f"p10-p90 coverage: {report.interval_coverage:.2f} (target 0.80, period={report.holdout_days}d)")
    return "\n".join(lines)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--holdout", type=int, default=14, help="hold-out days per SKU")
    parser.add_argument("--min-history", type=int, default=60, help="minimum rows per SKU / rolling window size")
    parser.add_argument("--limit", type=int, default=500, help="max SKUs to test")
    parser.add_argument("--folds", type=int, default=1, help="rolling-origin folds (1 = single split)")
    parser.add_argument("--json", type=Path, default=None, help="write full JSON report here")
    args = parser.parse_args()

    report = await run_backtest(args.holdout, args.min_history, args.limit, args.folds)
    print(render(report))

    if args.json:
        args.json.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
        print(f"\njson report: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
