"""Tests for notify_node Slack-message format.

All external dependencies (httpx, shopify_sync, DB) are patched at module
level via autouse fixture — no real network, Shopify, or DB calls are ever made.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.nodes.notify_node import notify_node


@pytest.fixture(autouse=True)
def _block_real_network_calls():
    """Patch every external dependency for ALL tests in this module."""
    with (
        patch("agent.shopify_sync.sync_products_and_inventory", return_value=0),
        patch("agent.shopify_sync.sync_sales_history", return_value=0),
        patch("agent.nodes.notify_node.httpx.AsyncClient"),
    ):
        yield


# ---------------------------------------------------------------------------
# Graph-level test (from remote, preserved)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_graph_sends_pending_notification_before_resume():
    """Verify the Slack message matches what the graph's notify_pending node produces."""
    from agent.nodes.notify_node import notify_pending_node

    state = {
        "risk_alerts": [{"risk_level": "critical", "sku_id": 1, "reason": "Low stock"}],
        "purchase_orders": [{"po_id": 7, "quantity": 3, "total_cost": 9.0}],
    }

    with (
        patch("agent.nodes.notify_node.settings") as mock_settings,
        patch("agent.nodes.notify_node.httpx.AsyncClient") as client_cls,
    ):
        mock_settings.slack_webhook_url = "https://hooks.slack.com/services/TEST"
        mock_settings.public_api_url = "http://localhost:8002"
        client = client_cls.return_value.__aenter__.return_value
        client.post = AsyncMock()

        result = await notify_pending_node(state)

    summary = result["notification_summary"]
    assert summary.startswith("Inventory Risk & PO Report")
    assert "PO #7" in summary
    assert "Approve:" in summary
    assert "Reject:" in summary
    client.post.assert_awaited_once()
    payload = client.post.await_args.kwargs["json"]
    assert "PO #7" in payload["text"]


# ---------------------------------------------------------------------------
# notify_node unit tests
# ---------------------------------------------------------------------------

@pytest.fixture
def state_with_alerts_and_pos():
    return {
        "risk_alerts": [
            {"sku_id": 1, "risk_level": "critical", "reason": "Stockout in 2 days"},
            {"sku_id": 2, "risk_level": "warning", "reason": "Low stock, 10 days left"},
        ],
        "purchase_orders": [
            {"po_id": 10, "quantity": 50, "total_cost": 750.0},
            {"po_id": 11, "quantity": 25, "total_cost": 375.0},
        ],
    }


@pytest.mark.asyncio
async def test_empty_state_returns_unchanged():
    result = await notify_node({"risk_alerts": [], "purchase_orders": []})

    assert result["risk_alerts"] == []
    assert result["purchase_orders"] == []
    assert result["notification_summary"] == ""


@pytest.mark.asyncio
async def test_slack_message_has_critical_and_warning_sections(state_with_alerts_and_pos):
    with patch("agent.nodes.notify_node.httpx.AsyncClient") as mock_client:
        mock_post = AsyncMock()
        mock_client.return_value.__aenter__ = AsyncMock(return_value=type("Ctx", (), {"post": mock_post})())
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await notify_node(state_with_alerts_and_pos)

    summary = result["notification_summary"]
    assert "Inventory Risk & PO Report" in summary
    assert "Critical alerts: 1" in summary
    assert "Warning alerts:  1" in summary
    assert "POs pending approval: 2" in summary
    assert "[critical] SKU #1: Stockout in 2 days" in summary
    assert "[warning] SKU #2: Low stock, 10 days left" in summary
    assert "PO #10: 50 units, $750.00" in summary
    assert "PO #11: 25 units, $375.00" in summary
    assert "Approve:" in summary
    assert "Reject:" in summary


@pytest.mark.asyncio
async def test_slack_post_called_with_webhook_url(state_with_alerts_and_pos):
    with (
        patch("agent.nodes.notify_node.settings") as mock_settings,
        patch("agent.nodes.notify_node.httpx.AsyncClient") as mock_client,
    ):
        mock_settings.slack_webhook_url = "https://hooks.slack.com/services/TEST"
        mock_settings.shopify_store_domain = "test-store.myshopify.com"
        mock_post = AsyncMock()
        mock_client.return_value.__aenter__ = AsyncMock(return_value=type("Ctx", (), {"post": mock_post})())
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await notify_node(state_with_alerts_and_pos)

    summary = result["notification_summary"]
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert call_args[1]["json"]["text"] == summary


@pytest.mark.asyncio
async def test_critical_only_skips_warnings_line():
    state = {
        "risk_alerts": [{"sku_id": 7, "risk_level": "critical", "reason": "Zero stock"}],
        "purchase_orders": [{"po_id": 20, "quantity": 100, "total_cost": 1500.0}],
    }
    with patch("agent.nodes.notify_node.httpx.AsyncClient") as mock_client:
        mock_post = AsyncMock()
        mock_client.return_value.__aenter__ = AsyncMock(return_value=type("Ctx", (), {"post": mock_post})())
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await notify_node(state)

    summary = result["notification_summary"]
    assert "Critical alerts: 1" in summary
    assert "Warning alerts:  0" in summary
    assert "PO #20: 100 units, $1500.00" in summary


@pytest.mark.asyncio
async def test_no_webhook_skips_http(state_with_alerts_and_pos):
    with (
        patch("agent.nodes.notify_node.settings") as mock_settings,
        patch("agent.nodes.notify_node.httpx.AsyncClient") as mock_client,
    ):
        mock_settings.slack_webhook_url = None
        mock_settings.shopify_store_domain = "test-store.myshopify.com"

        result = await notify_node(state_with_alerts_and_pos)

    summary = result["notification_summary"]
    assert "Inventory Risk & PO Report" in summary
    mock_client.assert_not_called()


@pytest.mark.asyncio
async def test_overflow_alerts_truncated():
    alerts = [
        {"sku_id": i, "risk_level": "warning", "reason": f"Alert {i}"}
        for i in range(8)
    ]
    state = {"risk_alerts": alerts, "purchase_orders": []}

    result = await notify_node(state)

    summary = result["notification_summary"]
    assert "Warning alerts:  8" in summary
    assert "... and 3 more" in summary


@pytest.mark.asyncio
async def test_no_real_shopify_calls():
    """Verify sync_functions are never invoked during notify_node."""
    with (
        patch("agent.shopify_sync.sync_products_and_inventory", return_value=0) as mock_sync_products,
        patch("agent.shopify_sync.sync_sales_history", return_value=0) as mock_sync_sales,
        patch("agent.nodes.notify_node.httpx.AsyncClient") as mock_client,
    ):
        mock_post = AsyncMock()
        mock_client.return_value.__aenter__ = AsyncMock(return_value=type("Ctx", (), {"post": mock_post})())
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

        state = {
            "risk_alerts": [{"sku_id": 1, "risk_level": "critical", "reason": "test"}],
            "purchase_orders": [],
        }
        await notify_node(state)

    mock_sync_products.assert_not_called()
    mock_sync_sales.assert_not_called()
    mock_client.assert_not_called()
