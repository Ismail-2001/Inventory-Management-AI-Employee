import pytest
from unittest.mock import AsyncMock

from api.routes import purchase_orders


class FakeSession:
    def __init__(self, existing=None):
        self._existing = existing
        self.commits = 0
        self.added = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, query):
        class Result:
            def __init__(self, row):
                self._row = row

            def scalar_one_or_none(self):
                return self._row

        return Result(self._existing)

    async def commit(self):
        self.commits += 1

    def add(self, item):
        self.added.append(item)


@pytest.mark.asyncio
async def test_same_idempotency_key_only_changes_state_once(monkeypatch):
    calls = {"count": 0}

    async def fake_impl(po_id, approved_by, quantity):
        calls["count"] += 1
        return {"status": "approved", "po_id": po_id}

    class FakeIdempotencyKey:
        pass

    async def fake_session_factory():
        return FakeSession(None)

    monkeypatch.setattr(purchase_orders, "async_session_factory", fake_session_factory)
    monkeypatch.setattr(purchase_orders, "_approve_po_impl", fake_impl)

    first = await purchase_orders._run_with_idempotency("same-key", "/api/v1/po/1/approve", lambda: fake_impl(1, "merchant", None))
    second = await purchase_orders._run_with_idempotency("same-key", "/api/v1/po/1/approve", lambda: fake_impl(1, "merchant", None))

    assert first == second
    assert calls["count"] == 1
