import pytest
from datetime import date, timedelta
from types import SimpleNamespace

from agent import metrics as metrics_module
from agent.models import POStatus


class FakeResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return self._items


class FakeSession:
    def __init__(self, items=None):
        self._items = items or []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, query):
        return FakeResult(self._items)


class FakeSessionFactory:
    def __init__(self, items=None):
        self._items = items or []

    def __call__(self):
        return FakeSession(self._items)


def _make_po(status, edited=False, created_at=None):
    return SimpleNamespace(
        id=1,
        status=status,
        edited_before_approval=edited,
        created_at=created_at or date.today(),
        sku_id=1,
        merchant_id=1,
    )


def _make_outcome(error_pct=None, stockout=False):
    return SimpleNamespace(
        id=1,
        po_id=1,
        forecast_error_pct=error_pct,
        actual_stockout_occurred=stockout,
        evaluated_at=date.today(),
    )


@pytest.mark.asyncio
async def test_acceptance_rate_empty():
    result = await metrics_module.calculate_acceptance_rate(
        session_factory=FakeSessionFactory([])
    )
    assert result["total"] == 0
    assert result["accepted_as_is_pct"] == 0
    assert result["rejected_pct"] == 0


@pytest.mark.asyncio
async def test_acceptance_rate_all_approved_as_is():
    pos = [_make_po(POStatus.approved, edited=False) for _ in range(3)]
    result = await metrics_module.calculate_acceptance_rate(
        session_factory=FakeSessionFactory(pos)
    )
    assert result["total"] == 3
    assert result["accepted_as_is"] == 3
    assert result["accepted_as_is_pct"] == 100.0
    assert result["edited_then_approved"] == 0
    assert result["rejected"] == 0


@pytest.mark.asyncio
async def test_acceptance_rate_mixed():
    pos = [
        _make_po(POStatus.approved, edited=False),
        _make_po(POStatus.approved, edited=True),
        _make_po(POStatus.rejected),
    ]
    result = await metrics_module.calculate_acceptance_rate(
        session_factory=FakeSessionFactory(pos)
    )
    assert result["total"] == 3
    assert result["accepted_as_is"] == 1
    assert result["accepted_as_is_pct"] == 33.3
    assert result["edited_then_approved"] == 1
    assert result["edited_then_approved_pct"] == 33.3
    assert result["rejected"] == 1
    assert result["rejected_pct"] == 33.3


@pytest.mark.asyncio
async def test_forecast_error_summary_none_when_empty():
    result = await metrics_module.calculate_forecast_error_summary(
        session_factory=FakeSessionFactory([])
    )
    assert result is None


@pytest.mark.asyncio
async def test_forecast_error_summary_computes_stats():
    outcomes = [
        _make_outcome(error_pct=10.0, stockout=False),
        _make_outcome(error_pct=20.0, stockout=True),
        _make_outcome(error_pct=30.0, stockout=False),
    ]
    result = await metrics_module.calculate_forecast_error_summary(
        session_factory=FakeSessionFactory(outcomes)
    )
    assert result["count"] == 3
    assert result["mean_error_pct"] == 20.0
    assert result["min_error_pct"] == 10.0
    assert result["max_error_pct"] == 30.0
    assert result["stockout_rate"] == 33.3
