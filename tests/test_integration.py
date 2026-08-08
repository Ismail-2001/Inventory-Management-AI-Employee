"""E2E integration test exercising the full LangGraph pipeline with a real Postgres database.

Requires:
- A running Postgres at DATABASE_URL (CI provides this via service container)
- Alembic migrations applied (``alembic upgrade head`` runs before pytest in CI)

Marked with ``@pytest.mark.integration`` so it can be excluded from quick local runs.
"""
import os
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from agent.config import settings
from agent.db import async_session_factory, engine
from agent.models import Forecast, Merchant, PurchaseOrder, RiskAlert, Sku, Supplier

pytestmark = [
    pytest.mark.skipif(
        not os.getenv("DATABASE_URL"),
        reason="DATABASE_URL not set — requires real Postgres",
    ),
    pytest.mark.asyncio,
]


@pytest.fixture(autouse=True)
async def _clean_tables():
    """Reset tables between tests for isolation."""
    cleanup_engine = create_async_engine(settings.database_url)
    async with cleanup_engine.begin() as conn:
        for table in ("risk_alerts", "forecasts", "purchase_orders", "suppliers", "skus", "merchants"):
            await conn.execute(text(f"DELETE FROM {table}"))
    await cleanup_engine.dispose()
    await engine.dispose()


async def _seed_sku(session: AsyncSession, merchant_id: int = 0) -> Sku:
    merchant = Merchant(id=merchant_id, name="Integration Test Merchant", hashed_api_key="test", shopify_store_domain="test.myshopify.com")
    session.add(merchant)
    await session.flush()
    sku = Sku(
        shopify_variant_id=f"gid://shopify/Variant/{uuid.uuid4().int % 10**10}",
        merchant_id=merchant_id,
        sku_code="INTEGRATION-TEST-SKU",
        title="Integration Test Widget",
        current_stock=10,
    )
    session.add(sku)
    await session.commit()
    await session.refresh(sku)
    return sku


async def _seed_supplier(session: AsyncSession) -> Supplier:
    sup = Supplier(
        name="Integration Test Supplier",
        default_lead_time_days=7,
        default_moq=5,
        moq_by_sku={},
        unit_cost_by_sku={},
    )
    session.add(sup)
    await session.commit()
    await session.refresh(sup)
    return sup


@pytest.fixture
async def seeded_sku() -> Sku:
    async with async_session_factory() as session:
        sku = await _seed_sku(session)
        await _seed_supplier(session)
        return sku


async def test_migration_applied():
    """Verify that Alembic migrations have been applied and all tables exist."""
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT COUNT(*) FROM skus"))
        assert result is not None
    await engine.dispose()


async def test_full_pipeline_creates_forecasts_risk_alerts_and_pos(seeded_sku):
    """Run the full sync → forecast → risk → po_draft pipeline and verify every
    state key is populated.  This is the same flow as POST /api/v1/run-sync."""
    from langgraph.checkpoint.memory import MemorySaver

    from agent.graph import build_graph

    graph = build_graph().compile(checkpointer=MemorySaver())

    state = {
        "merchant_id": 0,
    }

    result = await graph.ainvoke(state, {"configurable": {"thread_id": "integration-test"}})

    assert "skus" in result, "sync_node did not populate skus"
    assert len(result["skus"]) >= 1, "at least the seeded SKU should be present"

    assert "forecasts" in result, "forecast_node did not populate forecasts"
    assert len(result["forecasts"]) >= 1, "at least one forecast should exist"
    forecast = result["forecasts"][0]
    assert "sku_id" in forecast
    assert "predicted_daily_demand" in forecast
    assert forecast["predicted_daily_demand"] >= 0

    assert "risk_alerts" in result, "risk_node did not populate risk_alerts"
    assert len(result["risk_alerts"]) >= 1, "low stock should trigger a risk alert"
    forecast_sku_ids = {f["sku_id"] for f in result["forecasts"]}
    alert = next(a for a in result["risk_alerts"] if a["sku_id"] in forecast_sku_ids)
    assert alert["risk_level"] in ("critical", "warning")
    assert alert["sku_id"] in forecast_sku_ids

    assert "purchase_orders" in result, "po_draft_node did not populate purchase_orders"
    assert len(result["purchase_orders"]) >= 1, "critical risk should create a PO"
    po = result["purchase_orders"][0]
    assert po["status"] == "pending_approval"
    assert po["quantity"] > 0
    assert po["total_cost"] >= 0
    assert "reasoning" in po


async def test_db_records_persisted_correctly(seeded_sku):
    """Verify that records written inside graph nodes are queryable from the DB
    after the run completes."""
    from langgraph.checkpoint.memory import MemorySaver

    from agent.graph import build_graph

    graph = build_graph().compile(checkpointer=MemorySaver())

    await graph.ainvoke({"merchant_id": 0}, {"configurable": {"thread_id": "integration-db-test"}})

    async with async_session_factory() as session:
        forecasts = (await session.execute(select(Forecast))).scalars().all()
        assert len(forecasts) >= 1

        alerts = (await session.execute(select(RiskAlert))).scalars().all()
        assert len(alerts) >= 1

        pos = (await session.execute(select(PurchaseOrder))).scalars().all()
        assert len(pos) >= 1
        assert pos[0].status.value == "pending_approval"


async def test_no_duplicate_pos_on_concurrent_runs(seeded_sku):
    """Two back-to-back invocations should not create duplicate POs for the same
    SKU within the dedup window."""
    from langgraph.checkpoint.memory import MemorySaver

    from agent.graph import build_graph

    graph = build_graph().compile(checkpointer=MemorySaver())

    # First run
    await graph.ainvoke({"merchant_id": 0}, {"configurable": {"thread_id": "run-1"}})
    # Second run (different thread, same merchant, same SKU)
    await graph.ainvoke({"merchant_id": 0}, {"configurable": {"thread_id": "run-2"}})

    async with async_session_factory() as session:
        pos = (await session.execute(select(PurchaseOrder))).scalars().all()
        sku_ids = [(po.sku_id, po.status.value) for po in pos]
        # Each SKU should have at most one pending_approval PO
        pending_by_sku = {}
        for sku_id, status in sku_ids:
            if status == "pending_approval":
                pending_by_sku[sku_id] = pending_by_sku.get(sku_id, 0) + 1
        for sku_id, count in pending_by_sku.items():
            assert count == 1, f"SKU {sku_id} has {count} pending POs (expected 1)"
