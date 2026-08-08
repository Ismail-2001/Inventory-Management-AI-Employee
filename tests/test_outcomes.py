from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from agent import outcomes as outcomes_module
from agent.models import Sku


class FakeResult:
    def __init__(self, items=None, scalar=None):
        self._items = items or []
        self._scalar = scalar

    def scalars(self):
        return self

    def all(self):
        return self._items

    def scalar_one_or_none(self):
        return self._scalar

    def scalar(self):
        return self._scalar


class FakeSession:
    def __init__(self, pos=None, outcomes=None, sku=None, sales_data=None):
        self._pos = pos or []
        self._outcomes = outcomes or []
        self._sku = sku
        self._sales_data = sales_data or {}
        self.added = []
        self.committed = False
        self._execute_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, query):
        self._execute_calls.append(query)
        if self._pos:
            return FakeResult(self._pos)
        if self._outcomes:
            return FakeResult(self._outcomes)
        if self._sku is not None:
            return FakeResult(scalar=self._sku)
        return FakeResult()

    async def get(self, model, id):
        if model == Sku:
            return self._sku
        return None

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True


class FakeSessionFactory:
    def __init__(self, session=None):
        self._session = session

    def __call__(self):
        return self._session


@pytest.mark.asyncio
async def test_evaluate_returns_0_when_no_approved_pos(monkeypatch):
    session = FakeSession(pos=[])
    monkeypatch.setattr(outcomes_module, "async_session_factory", FakeSessionFactory(session))

    result = await outcomes_module.evaluate_pending_outcomes()
    assert result == 0


@pytest.mark.asyncio
async def test_evaluate_skips_duplicate_outcome(monkeypatch):
    po = SimpleNamespace(
        id=1,
        status="approved",
        approved_at=datetime.now(UTC) - timedelta(days=10),
        sku_id=1,
    )
    session = FakeSession(pos=[po], outcomes=[SimpleNamespace(po_id=1)])
    monkeypatch.setattr(outcomes_module, "async_session_factory", FakeSessionFactory(session))

    result = await outcomes_module.evaluate_pending_outcomes()
    assert result == 0


@pytest.mark.asyncio
async def test_evaluate_skips_no_sku(monkeypatch):
    po = SimpleNamespace(
        id=1,
        status="approved",
        approved_at=datetime.now(UTC) - timedelta(days=10),
        sku_id=1,
    )
    session = FakeSession(pos=[po], outcomes=[], sku=None)
    monkeypatch.setattr(outcomes_module, "async_session_factory", FakeSessionFactory(session))

    result = await outcomes_module.evaluate_pending_outcomes()
    assert result == 0


@pytest.mark.asyncio
async def test_evaluate_creates_outcome(monkeypatch):
    po = SimpleNamespace(
        id=1,
        status="approved",
        approved_at=datetime.now(UTC) - timedelta(days=20),
        sku_id=1,
    )
    sku = SimpleNamespace(id=1, current_stock=5)

    class MultiSession:
        def __init__(self):
            self.call_count = 0
            self.added = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def execute(self, query):
            self.call_count += 1
            if self.call_count == 1:
                return FakeResult([po])
            if self.call_count == 2:
                return FakeResult([])
            return FakeResult(scalar=0)

        async def get(self, model, id):
            return sku

        def add(self, obj):
            self.added.append(obj)

        async def commit(self):
            pass

    session = MultiSession()
    monkeypatch.setattr(outcomes_module, "async_session_factory", lambda: session)

    result = await outcomes_module.evaluate_pending_outcomes()
    assert result == 1
    assert len(session.added) == 1
    outcome = session.added[0]
    assert outcome.po_id == 1
    assert outcome.actual_stock_at_delivery == 5
    assert outcome.forecast_error_pct is not None
