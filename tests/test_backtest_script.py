"""Backtest script — computed on synthetic history (no DB required)."""

import importlib.util
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "forecast_backtest",
    Path(__file__).resolve().parents[1] / "scripts" / "forecast_backtest.py",
)
assert _SPEC is not None and _SPEC.loader is not None
backtest = importlib.util.module_from_spec(_SPEC)
sys.modules["forecast_backtest"] = backtest
_SPEC.loader.exec_module(backtest)


def _seasonal_rows(n: int, start: date = date(2026, 1, 1)) -> list[tuple[date, float]]:
    pattern = [10.0, 10.0, 10.0, 10.0, 10.0, 16.0, 18.0]
    return [(start + timedelta(days=i), pattern[i % 7]) for i in range(n)]


@pytest.mark.asyncio
async def test_run_backtest_on_synthetic_history(monkeypatch: pytest.MonkeyPatch) -> None:
    long_sku = _seasonal_rows(60)
    short_sku = _seasonal_rows(20)

    async def fake_load(min_days: int, limit: int) -> dict[int, list[tuple[date, float]]]:
        return {1: long_sku, 2: short_sku}

    monkeypatch.setattr(backtest, "load_history", fake_load)

    report = await backtest.run_backtest(holdout=14, min_history=60, limit=10)

    assert report.skus_tested == 1
    assert report.skus_skipped == 1
    assert report.holdout_days == 14
    assert 0.0 <= report.v2_pooled_wmape <= report.v1_pooled_wmape
    assert report.interval_coverage is not None
    assert 0.0 <= report.interval_coverage <= 1.0
    assert report.improved >= 1 and report.regressed == 0
    assert report.model_distribution

    text = backtest.render(report)
    assert "wMAPE" in text
    assert "v1 (legacy)" in text
    assert "v2 (ensemble)" in text


@pytest.mark.asyncio
async def test_run_backtest_empty_history(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_load(min_days: int, limit: int) -> dict[int, list[tuple[date, float]]]:
        return {}

    monkeypatch.setattr(backtest, "load_history", fake_load)

    report = await backtest.run_backtest(holdout=14, min_history=60, limit=10)

    assert report.skus_tested == 0
    assert report.v1_pooled_wmape == 0.0
    assert report.v2_pooled_wmape == 0.0
    assert report.interval_coverage is None
    assert "0 skus tested" in backtest.render(report)
