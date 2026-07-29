from types import SimpleNamespace

import pytest
from agent.forecast import exponential_smoothing
from agent.nodes.forecast_node import calculate_forecast


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


@pytest.mark.asyncio
async def test_calculate_forecast_sorts_history_before_smoothing(monkeypatch):
    class FakeSession:
        def __init__(self, rows):
            self._rows = rows

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, query):
            return SimpleNamespace(all=lambda: self._rows)

        def add(self, obj):
            return None

        async def commit(self):
            return None

        async def refresh(self, obj):
            return None

    class FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class FakeSessionFactory:
        def __init__(self, rows):
            self.rows = rows

        def __call__(self):
            return FakeSession(self.rows)

    class FakeDate:
        def __init__(self, value):
            self.value = value

        def isoformat(self):
            return self.value

        def __lt__(self, other):
            return self.value < other.value

        def __gt__(self, other):
            return self.value > other.value

    rows = [
        (10, FakeDate("2024-01-03")),
        (20, FakeDate("2024-01-01")),
        (30, FakeDate("2024-01-02")),
    ]

    def fake_session_factory():
        return FakeSession(rows)

    monkeypatch.setattr("agent.nodes.forecast_node.async_session_factory", fake_session_factory)

    result = await calculate_forecast(1, 100, 7)

    assert result.predicted_daily_demand >= 0
