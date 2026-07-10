import pytest
from agent.forecast import exponential_smoothing


def test_exponential_smoothing_constant():
    values = [5.0, 5.0, 5.0, 5.0, 5.0]
    result = exponential_smoothing(values, alpha=0.3)
    assert result == pytest.approx(5.0, abs=0.01)


def test_exponential_smoothing_trend():
    values = [10.0, 12.0, 14.0, 16.0, 18.0]
    result = exponential_smoothing(values, alpha=0.5)
    assert result > 14.0
    assert result < 18.0


def test_exponential_smoothing_empty():
    assert exponential_smoothing([]) == 0.0


def test_exponential_smoothing_single():
    assert exponential_smoothing([42.0]) == 42.0


def test_exponential_smoothing_default_alpha():
    values = [100.0, 90.0, 80.0]
    result = exponential_smoothing(values)
    assert result < 100.0
    assert result > 80.0
