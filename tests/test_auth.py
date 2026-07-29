import pytest
from fastapi import HTTPException
from types import SimpleNamespace

from agent import auth as auth_module
from agent.auth import get_current_user, require_role, verify_api_key
from agent.models import Merchant, User


class FakeResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return self._items


class FakeSession:
    def __init__(self, merchants=None):
        self._merchants = merchants or []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, query):
        return FakeResult(self._merchants)


@pytest.mark.asyncio
async def test_verify_api_key_rejects_invalid_key(monkeypatch):
    async def fake_session_factory():
        return FakeSession([])

    monkeypatch.setattr(auth_module, "async_session_factory", fake_session_factory)

    with pytest.raises(HTTPException) as exc:
        await verify_api_key("wrong-key")

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_demo_key_rejected_when_demo_disabled(monkeypatch):
    monkeypatch.setattr(auth_module.settings, "allow_demo_key", False)
    monkeypatch.setattr(auth_module.settings, "agent_api_key", "demo-key-2024")

    async def fake_session_factory():
        return FakeSession([])

    monkeypatch.setattr(auth_module, "async_session_factory", fake_session_factory)

    with pytest.raises(HTTPException) as exc:
        await verify_api_key("demo-key-2024")

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_viewer_role_cannot_approve(monkeypatch):
    dependency = require_role("owner", "staff")
    viewer = User(id=1, merchant_id=1, email="viewer@example.com", role="viewer")

    with pytest.raises(HTTPException) as exc:
        await dependency(viewer)

    assert exc.value.status_code == 403
