import pytest
from fastapi import HTTPException
from types import SimpleNamespace

from agent import security as security_module
from agent.models import Merchant


class FakeResult:
    def __init__(self, items=None, one=None):
        self._items = items or []
        self._one = one

    def scalars(self):
        return self

    def all(self):
        return self._items

    def scalar_one_or_none(self):
        return self._one


class FakeSession:
    def __init__(self, merchants=None, existing=None):
        self._merchants = merchants or []
        self._existing = existing
        self.added = []
        self.deleted = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, query):
        return FakeResult(self._merchants, self._existing)

    def add(self, obj):
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def commit(self):
        self.committed = True


class FakeSessionFactory:
    def __init__(self, session=None):
        self._session = session

    def __call__(self):
        return self._session


class FakeSessionScope:
    def __init__(self, session):
        self._session = session

    def __call__(self, factory):
        return self._session


@pytest.mark.asyncio
async def test_generate_api_key_format():
    raw, prefix, hashed = security_module.generate_api_key()
    assert raw.startswith("sk_live_")
    assert len(raw) == 72  # "sk_live_" + 64 hex chars
    assert prefix == raw[:8]
    assert len(hashed) > 0
    assert raw != hashed


@pytest.mark.asyncio
async def test_generate_api_key_unique():
    keys = set()
    for _ in range(10):
        raw, _, _ = security_module.generate_api_key()
        keys.add(raw)
    assert len(keys) == 10


@pytest.mark.asyncio
async def test_create_merchant_api_key(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(security_module, "session_scope", FakeSessionScope(session))

    raw = await security_module.create_merchant_api_key("Test Shop", "test.myshopify.com")
    assert raw.startswith("sk_live_")
    assert len(session.added) == 1
    merchant = session.added[0]
    assert merchant.name == "Test Shop"
    assert merchant.shopify_store_domain == "test.myshopify.com"
    assert merchant.tier == "developer"


@pytest.mark.asyncio
async def test_create_merchant_invalid_tier_defaults_to_developer(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(security_module, "session_scope", FakeSessionScope(session))

    await security_module.create_merchant_api_key("Shop", "s.myshopify.com", tier="invalid")
    assert session.added[0].tier == "developer"


@pytest.mark.asyncio
async def test_rotate_api_key(monkeypatch):
    existing = SimpleNamespace(id=1, hashed_api_key="old", key_prefix="old_pfx")
    session = FakeSession(existing=existing)
    monkeypatch.setattr(security_module, "session_scope", FakeSessionScope(session))

    raw = await security_module.rotate_api_key(1)
    assert raw.startswith("sk_live_")
    assert existing.hashed_api_key != "old"


@pytest.mark.asyncio
async def test_rotate_api_key_404(monkeypatch):
    session = FakeSession(existing=None)
    monkeypatch.setattr(security_module, "session_scope", FakeSessionScope(session))

    with pytest.raises(HTTPException) as exc:
        await security_module.rotate_api_key(999)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_revoke_api_key_found(monkeypatch):
    existing = SimpleNamespace(id=1)
    session = FakeSession(existing=existing)
    monkeypatch.setattr(security_module, "session_scope", FakeSessionScope(session))

    result = await security_module.revoke_api_key("sk_live_")
    assert result is True
    assert len(session.deleted) == 1


@pytest.mark.asyncio
async def test_revoke_api_key_not_found(monkeypatch):
    session = FakeSession(existing=None)
    monkeypatch.setattr(security_module, "session_scope", FakeSessionScope(session))

    result = await security_module.revoke_api_key("nonexistent")
    assert result is False


@pytest.mark.asyncio
async def test_list_merchant_keys_empty_for_zero():
    result = await security_module.list_merchant_keys(0)
    assert result == []


@pytest.mark.asyncio
async def test_list_merchant_keys(monkeypatch):
    merchants = [
        SimpleNamespace(
            key_prefix="sk_live_",
            name="Shop",
            shopify_store_domain="s.myshopify.com",
            created_at=None,
        )
    ]
    session = FakeSession(merchants=merchants)
    monkeypatch.setattr(security_module, "session_scope", FakeSessionScope(session))

    result = await security_module.list_merchant_keys(1)
    assert len(result) == 1
    assert result[0]["name"] == "Shop"
