"""Calendar-aligned hold-out actuals (scripts/forecast_backtest.py)."""

import importlib.util
import sys
from datetime import date, timedelta
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "forecast_backtest",
    Path(__file__).resolve().parents[1] / "scripts" / "forecast_backtest.py",
)
assert _spec is not None and _spec.loader is not None
forecast_backtest = importlib.util.module_from_spec(_spec)
sys.modules["forecast_backtest"] = forecast_backtest  # dataclass resolution needs this
_spec.loader.exec_module(forecast_backtest)
aligned_actual = forecast_backtest.aligned_actual


def _d(i: int) -> date:
    return date(2026, 1, 1) + timedelta(days=i)


def test_dense_window_equals_raw_test_rows():
    train = [(_d(i), 5.0) for i in range(10)]
    test = [(_d(10 + i), 3.0 + i) for i in range(14)]
    assert aligned_actual(train, test) == [3.0 + i for i in range(14)]


def test_gap_days_are_zero_filled():
    train = [(_d(i), 5.0) for i in range(10)]  # last train day: day 9
    test = [(_d(11), 4.0), (_d(12), 6.0)]  # day 10 has no sale row
    assert aligned_actual(train, test) == [0.0, 4.0, 6.0]


def test_gap_between_train_and_test_included():
    train = [(_d(i), 5.0) for i in range(10)]
    test = [(_d(12), 7.0), (_d(13), 8.0)]  # days 10-11 empty
    assert aligned_actual(train, test) == [0.0, 0.0, 7.0, 8.0]


def test_sum_invariant_to_gap_filling():
    train = [(_d(i), 5.0) for i in range(10)]
    test = [(_d(11), 4.0), (_d(13), 6.0)]
    actual = aligned_actual(train, test)
    assert sum(actual) == sum(v for _, v in test)
    assert len(actual) == (test[-1][0] - train[-1][0]).days
