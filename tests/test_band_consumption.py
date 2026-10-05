from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.nodes.po_draft_node import po_draft_node
from agent.nodes.risk_node import risk_node


class _Supplier:
    id = 1
    default_moq = 1
    moq_by_sku: dict = {}
    unit_cost_by_sku: dict = {}


def _risk_session() -> AsyncMock:
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


def _po_session() -> AsyncMock:
    session = AsyncMock()
    session.__aenter__.return_value = session
    result = MagicMock()
    result.scalar_one_or_none.return_value = _Supplier()
    result.scalars.return_value.all.return_value = []
    result.all.return_value = []
    session.execute.return_value = result
    session.refresh = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_risk_node_escalates_using_p90_cover_band():
    state = {
        "skus": [{"id": 1, "lead_time_days": 7}],
        "forecasts": [
            {"sku_id": 1, "days_of_stock_remaining": 20.0, "days_of_cover_p90": 4.0},
        ],
    }
    session = _risk_session()

    with patch("agent.nodes.risk_node.async_session_factory", return_value=session):
        result = await risk_node(state)

    assert len(result["risk_alerts"]) == 1
    alert = result["risk_alerts"][0]
    assert alert["risk_level"] == "critical"
    assert "p90" in alert["reason"]
    session.add.assert_called_once()


@pytest.mark.asyncio
async def test_risk_node_no_alert_when_band_stays_safe():
    state = {
        "skus": [{"id": 1, "lead_time_days": 7}],
        "forecasts": [
            {"sku_id": 1, "days_of_stock_remaining": 20.0, "days_of_cover_p90": 15.0},
        ],
    }

    result = await risk_node(state)

    assert result["risk_alerts"] == []


def _po_state(p90: float | None) -> dict:
    forecast = {
        "sku_id": 1,
        "predicted_daily_demand": 5.0,
        "days_of_stock_remaining": 5.0,
    }
    if p90 is not None:
        forecast["p90_daily_demand"] = p90
    return {
        "risk_alerts": [{"sku_id": 1, "risk_level": "critical"}],
        "skus": [
            {"id": 1, "title": "Widget", "sku_code": "W1", "current_stock": 0, "lead_time_days": 7},
        ],
        "forecasts": [forecast],
    }


@pytest.mark.asyncio
async def test_po_draft_quantities_plan_against_p90_band():
    session = _po_session()

    with (
        patch("agent.nodes.po_draft_node.async_session_factory", return_value=session),
        patch("agent.nodes.po_draft_node._generate_reasoning", AsyncMock(return_value="reason")),
    ):
        result = await po_draft_node(_po_state(8.0))

    assert len(result["purchase_orders"]) == 1
    assert result["purchase_orders"][0]["quantity"] == 112


@pytest.mark.asyncio
async def test_po_draft_without_band_keeps_point_forecast_quantity():
    session = _po_session()

    with (
        patch("agent.nodes.po_draft_node.async_session_factory", return_value=session),
        patch("agent.nodes.po_draft_node._generate_reasoning", AsyncMock(return_value="reason")),
    ):
        result = await po_draft_node(_po_state(None))

    assert len(result["purchase_orders"]) == 1
    assert result["purchase_orders"][0]["quantity"] == 70


@pytest.mark.asyncio
async def test_po_draft_keeps_point_when_band_is_lower():
    session = _po_session()

    with (
        patch("agent.nodes.po_draft_node.async_session_factory", return_value=session),
        patch("agent.nodes.po_draft_node._generate_reasoning", AsyncMock(return_value="reason")),
    ):
        result = await po_draft_node(_po_state(3.0))

    assert len(result["purchase_orders"]) == 1
    assert result["purchase_orders"][0]["quantity"] == 70
