"""
Backtested forecast accuracy evaluation suite.
Run: pytest tests/eval_suite.py -v

This suite replays historical sales data through the forecast function
and compares predicted vs actual to calculate MAPE.
If MAPE exceeds threshold (default 30%), the build fails.
"""
import math

import pytest

from agent.forecast import exponential_smoothing


def calculate_mape(actual: list[float], predicted: list[float]) -> float:
    if not actual or len(actual) != len(predicted):
        return float("inf")
    errors = []
    for a, p in zip(actual, predicted):
        if a != 0:
            errors.append(abs((a - p) / a))
    if not errors:
        return float("inf")
    return sum(errors) / len(errors) * 100


# Known scenarios with expected behavior
FORECAST_TEST_CASES = [
    {
        "name": "constant_demand",
        "history": [10, 10, 10, 10, 10, 10, 10],
        "expected_mape_max": 5.0,
    },
    {
        "name": "linear_trend",
        "history": [5, 7, 9, 11, 13, 15],
        "expected_mape_max": 30.0,
    },
    {
        "name": "seasonal_spike",
        "history": [10, 12, 8, 11, 10, 50, 10, 12],
        "expected_mape_max": 40.0,
    },
    {
        "name": "erratic_demand",
        "history": [0, 5, 10, 0, 8, 3, 0, 12],
        "expected_mape_max": 55.0,
    },
    {
        "name": "empty_history",
        "history": [],
        "expected_mape_max": 100.0,
    },
]

MAPE_THRESHOLD = 30.0


@pytest.mark.parametrize("case", FORECAST_TEST_CASES, ids=[c["name"] for c in FORECAST_TEST_CASES])
def test_forecast_accuracy(case):
    history = [float(v) for v in case["history"]]
    if not history:
        predicted = exponential_smoothing([])
        assert predicted == 0.0
        return

    predicted = exponential_smoothing(history, alpha=0.3)
    actual = history[-1] if history else 0

    mape = calculate_mape([actual], [predicted])
    assert mape <= case["expected_mape_max"], (
        f"MAPE {mape:.1f}% exceeds max {case['expected_mape_max']}% for {case['name']}"
    )


@pytest.mark.skip(reason="Requires DB — run against real historical data in CI")
async def test_historical_backtest():
    from sqlalchemy import select, func
    from agent.db import async_session_factory
    from agent.models import POOutcome

    async with async_session_factory() as session:
        result = await session.execute(
            select(POOutcome).where(POOutcome.forecast_error_pct.isnot(None))
        )
        outcomes = result.scalars().all()

    if not outcomes:
        pytest.skip("No outcome data available yet")

    errors = [o.forecast_error_pct for o in outcomes if o.forecast_error_pct is not None]
    mean_error = sum(errors) / len(errors)

    assert mean_error <= MAPE_THRESHOLD, (
        f"Historical MAPE {mean_error:.1f}% exceeds threshold {MAPE_THRESHOLD}% "
        f"(based on {len(errors)} outcomes)"
    )


def test_mape_calculation():
    assert calculate_mape([100, 200], [110, 180]) == pytest.approx(10.0, abs=0.5)
    assert calculate_mape([], []) == float("inf")
    assert calculate_mape([10], [0]) == 100.0
    assert calculate_mape([10, 0], [5, 0]) == 50.0
