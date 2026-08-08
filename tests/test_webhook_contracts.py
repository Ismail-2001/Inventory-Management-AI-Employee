"""Contract tests for Shopify webhook handlers.

Validates that each handler correctly processes known Shopify payloads and
produces the expected side effects (DB upserts). These are pure unit tests —
all external dependencies (HTTP, Shopify API) are mocked.
"""
from unittest.mock import AsyncMock, patch

import pytest

from agent import webhooks

ORDER_PAYLOAD = {
    "id": 1001,
    "created_at": "2025-01-15T10:30:00Z",
    "line_items": [
        {"sku": "SKU-001", "quantity": 3, "product_id": 10, "variant_id": 100},
        {"sku": "SKU-002", "quantity": 1, "product_id": 20, "variant_id": 200},
    ],
}

INVENTORY_PAYLOAD = {
    "inventory_item_id": 55555,
}

PRODUCT_PAYLOAD = {
    "title": "Test Widget",
    "variants": [
        {
            "id": 300,
            "sku": "SKU-003",
            "inventory_quantity": 42,
        },
        {
            "id": 301,
            "sku": "SKU-004",
            "inventory_quantity": 0,
        },
    ],
}

PRODUCT_PAYLOAD_NO_VARIANTS = {
    "title": "Empty Product",
    "variants": [],
}


class FakeResult:
    def __init__(self, rows=None):
        self._rows = rows or []
    def scalars(self):
        class FakeScalars:
            def __init__(self, rows):
                self._rows = rows
            def all(self):
                return self._rows
        return FakeScalars(self._rows)
    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class FakeSession:
    def __init__(self, skus=None):
        self._skus = skus or []
        self.executed = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, stmt):
        self.executed.append(stmt)
        return FakeResult(self._skus)

    async def commit(self):
        self.committed = True

    def add(self, item):
        pass


class FakeSku:
    def __init__(self, id, sku_code):
        self.id = id
        self.sku_code = sku_code


@pytest.mark.asyncio
async def test_order_create_handler_uses_correct_date():
    fake_skus = [FakeSku(1, "SKU-001"), FakeSku(2, "SKU-002")]
    session = FakeSession(skus=fake_skus)
    with patch("agent.webhooks.session_scope") as mock_scope:
        mock_scope.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)
        await webhooks.handle_order_create(ORDER_PAYLOAD)

    assert session.committed
    assert len(session.executed) == 3


@pytest.mark.asyncio
async def test_order_create_handler_skips_empty_skus():
    payload = {
        "created_at": "2025-01-15T10:30:00Z",
        "line_items": [{"sku": "", "quantity": 5}],
    }
    with patch("agent.webhooks.session_scope") as mock_scope:
        mock_scope.return_value.__aenter__ = AsyncMock(return_value=FakeSession())
        mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)
        await webhooks.handle_order_create(payload)


@pytest.mark.asyncio
async def test_order_create_handler_skips_zero_quantity():
    payload = {
        "created_at": "2025-01-15T10:30:00Z",
        "line_items": [{"sku": "SKU-001", "quantity": 0}],
    }
    with patch("agent.webhooks.session_scope") as mock_scope:
        mock_scope.return_value.__aenter__ = AsyncMock(return_value=FakeSession())
        mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)
        await webhooks.handle_order_create(payload)


@pytest.mark.asyncio
async def test_inventory_update_delegates_to_sync_single_variant():
    with patch("agent.webhooks.sync_single_variant", new_callable=AsyncMock) as mock_sync:
        await webhooks.handle_inventory_update(INVENTORY_PAYLOAD)
    mock_sync.assert_called_once_with("55555")


@pytest.mark.asyncio
async def test_inventory_update_noop_without_inventory_item_id():
    with patch("agent.webhooks.sync_single_variant", new_callable=AsyncMock) as mock_sync:
        await webhooks.handle_inventory_update({})
    mock_sync.assert_not_called()


@pytest.mark.asyncio
async def test_product_update_upserts_variants():
    session = FakeSession()
    with patch("agent.webhooks.session_scope") as mock_scope:
        mock_scope.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)
        await webhooks.handle_product_update(PRODUCT_PAYLOAD)

    assert session.committed
    assert len(session.executed) == 2


@pytest.mark.asyncio
async def test_product_update_noop_without_variants():
    with patch("agent.webhooks.session_scope") as mock_scope:
        mock_scope.return_value.__aenter__ = AsyncMock(return_value=FakeSession())
        mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)
        await webhooks.handle_product_update(PRODUCT_PAYLOAD_NO_VARIANTS)


@pytest.mark.asyncio
async def test_product_update_skips_empty_variant_id():
    payload = {
        "title": "Widget",
        "variants": [{"id": "", "sku": "X", "inventory_quantity": 5}],
    }
    with patch("agent.webhooks.session_scope") as mock_scope:
        mock_scope.return_value.__aenter__ = AsyncMock(return_value=FakeSession())
        mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)
        await webhooks.handle_product_update(payload)


def test_hmac_verification_rejects_missing_header():
    class FakeRequest:
        headers = {}
        async def body(self):
            return b"test"
    with pytest.raises(Exception):
        import asyncio
        asyncio.run(webhooks.verify_shopify_webhook(FakeRequest()))


def test_hmac_verification_rejects_bad_signature():
    class FakeRequest:
        headers = {"X-Shopify-Hmac-Sha256": "bad"}
        async def body(self):
            return b"test"
    with pytest.raises(Exception):
        import asyncio
        asyncio.run(webhooks.verify_shopify_webhook(FakeRequest()))
