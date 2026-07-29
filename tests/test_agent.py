"""
Tests for Inventory Agent
Run: pytest tests/ -v
"""

import pytest
from agent.inventory_agent import InventoryAgent, InventoryItem, Config


@pytest.fixture
def agent():
    return InventoryAgent()


@pytest.fixture
def sample_item():
    return InventoryItem(
        product_id="SKU-001",
        name="Wireless Headphones",
        current_stock=150,
        daily_sales=8.5,
        lead_time_days=7,
        unit_cost=25.00,
        unit_price=79.99,
        category="electronics"
    )


@pytest.fixture
def critical_item():
    return InventoryItem(
        product_id="SKU-002",
        name="Phone Case",
        current_stock=5,
        daily_sales=12.0,
        lead_time_days=10,
        unit_cost=3.00,
        unit_price=19.99,
        category="accessories"
    )


@pytest.fixture
def overstocked_item():
    return InventoryItem(
        product_id="SKU-003",
        name="Old Model Watch",
        current_stock=500,
        daily_sales=2.0,
        lead_time_days=14,
        unit_cost=50.00,
        unit_price=149.99,
        category="accessories"
    )


def test_agent_initialization(agent):
    assert agent is not None
    assert agent.system_prompt is not None
    assert "MAINTAIN" in agent.system_prompt
    assert "REORDER" in agent.system_prompt
    assert "CLEARANCE" in agent.system_prompt


def test_item_model():
    item = InventoryItem(
        product_id="TEST-001",
        name="Test Product",
        current_stock=100,
        daily_sales=5.0,
        lead_time_days=7
    )
    assert item.product_id == "TEST-001"
    assert item.supplier_moq == 1
    assert item.supplier_reliability == 0.95


@pytest.mark.asyncio
async def test_analyze_maintain(agent, sample_item):
    result = await agent.analyze(sample_item)
    assert result.product_id == "SKU-001"
    assert result.recommended_action in ["maintain", "reorder", "clearance", "discontinue"]
    assert result.urgency in ["low", "medium", "high", "critical"]
    assert result.current_stock == 150


@pytest.mark.asyncio
async def test_analyze_critical(agent, critical_item):
    result = await agent.analyze(critical_item)
    assert result.product_id == "SKU-002"
    assert result.current_stock == 5
    assert result.days_of_stock_remaining < 1


@pytest.mark.asyncio
async def test_analyze_overstocked(agent, overstocked_item):
    result = await agent.analyze(overstocked_item)
    assert result.product_id == "SKU-003"
    assert result.recommended_action in ["clearance", "discontinue"]


@pytest.mark.asyncio
async def test_bulk_analysis(agent, sample_item, critical_item):
    items = [sample_item, critical_item]
    result = await agent.analyze_bulk(items)
    assert len(result.results) == 2
    assert result.summary["total_items"] == 2
    assert result.summary["critical_items"] >= 1


@pytest.mark.asyncio
async def test_forecast(agent, sample_item):
    result = await agent.forecast_demand(sample_item)
    assert "next_30_days" in result
    assert "next_60_days" in result
    assert "next_90_days" in result


def test_rule_based_fallback(agent, sample_item):
    result = agent._rule_based_fallback(sample_item)
    assert result.product_id == "SKU-001"
    assert result.days_of_stock_remaining > 0