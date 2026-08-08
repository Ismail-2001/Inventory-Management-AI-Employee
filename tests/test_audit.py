
import pytest

from agent import audit as audit_module
from agent.models import AuditLog


class FakeSession:
    def __init__(self):
        self.added = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True


class FakeSessionFactory:
    def __init__(self, session=None):
        self._session = session or FakeSession()

    def __call__(self):
        return self._session


@pytest.mark.asyncio
async def test_log_creates_audit_entry(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(audit_module, "async_session_factory", FakeSessionFactory(session))

    await audit_module.log(
        merchant_id=42,
        actor_type="user",
        actor_id="u-1",
        action="approve_po",
        target_type="purchase_order",
        target_id="po-99",
        details={"reason": "looks good"},
    )

    assert len(session.added) == 1
    entry = session.added[0]
    assert isinstance(entry, AuditLog)
    assert entry.merchant_id == 42
    assert entry.actor_type == "user"
    assert entry.actor_id == "u-1"
    assert entry.action == "approve_po"
    assert entry.target_type == "purchase_order"
    assert entry.target_id == "po-99"
    assert entry.details == {"reason": "looks good"}
    assert entry.created_at is not None
    assert entry.created_at.tzinfo is not None
    assert session.committed is True


@pytest.mark.asyncio
async def test_log_defaults(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(audit_module, "async_session_factory", FakeSessionFactory(session))

    await audit_module.log(action="test_action")

    entry = session.added[0]
    assert entry.merchant_id is None
    assert entry.actor_type == "system"
    assert entry.actor_id is None
    assert entry.action == "test_action"
    assert entry.target_type is None
    assert entry.target_id is None
    assert entry.details is None
