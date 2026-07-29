import pytest
from types import SimpleNamespace

from agent import webhooks


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
async def test_duplicate_webhook_event_id_only_processed_once(monkeypatch):
    processed = []

    async def fake_handler(payload):
        processed.append(payload)

    async def fake_session_factory():
        return FakeSession(None)

    class FakeRequest:
        headers = {"X-Shopify-Webhook-Id": "abc-123"}

        async def body(self):
            return b'{"id": 1}'

    monkeypatch.setattr(webhooks, "async_session_factory", fake_session_factory)
    monkeypatch.setattr(webhooks, "verify_shopify_webhook", lambda request: b'{"id": 1}')

    first = await webhooks.handle_webhook_event(FakeRequest(), "orders_create", fake_handler)
    second = await webhooks.handle_webhook_event(FakeRequest(), "orders_create", fake_handler)

    assert first["status"] == "ok"
    assert second["status"] == "ignored"
    assert len(processed) == 1
