"""Seed demo data for US business demonstration.

Populates PostgreSQL with realistic SKUs, inventory levels,
sales history, and a sample supplier — so the demo pipeline
produces meaningful results immediately on first run.

Usage:
    python seed_demo_data.py

Requires DATABASE_URL in .env (points to PostgreSQL).
"""

import asyncio
import os
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agent.config import settings
from agent.models import SalesHistory, Sku

engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# ── Demo SKUs for a US DTC retailer ──────────────────────────────

DEMO_SKUS = [
    {
        "shopify_variant_id": "gid://shopify/Variant/1001",
        "sku_code": "HWD-BT-001",
        "title": "Wireless Bluetooth Headphones",
        "current_stock": 5,
        "location_id": "warehouse-a",
        "lead_time_days": 7,
    },
    {
        "shopify_variant_id": "gid://shopify/Variant/1002",
        "sku_code": "HWD-BT-002",
        "title": "Wireless Bluetooth Headphones (Black)",
        "current_stock": 120,
        "location_id": "warehouse-a",
        "lead_time_days": 7,
    },
    {
        "shopify_variant_id": "gid://shopify/Variant/1003",
        "sku_code": "HWD-BT-003",
        "title": "Wireless Bluetooth Headphones (White)",
        "current_stock": 45,
        "location_id": "warehouse-a",
        "lead_time_days": 7,
    },
    {
        "shopify_variant_id": "gid://shopify/Variant/2001",
        "sku_code": "LPT-USB-C-001",
        "title": "USB-C Laptop Charger 65W",
        "current_stock": 3,
        "location_id": "warehouse-b",
        "lead_time_days": 10,
    },
    {
        "shopify_variant_id": "gid://shopify/Variant/2002",
        "sku_code": "LPT-USB-C-002",
        "title": "USB-C Laptop Charger 65W (White)",
        "current_stock": 200,
        "location_id": "warehouse-b",
        "lead_time_days": 10,
    },
    {
        "shopify_variant_id": "gid://shopify/Variant/3001",
        "sku_code": "CBL-LIGHT-001",
        "title": "Lightning Cable 6ft",
        "current_stock": 2,
        "location_id": "warehouse-a",
        "lead_time_days": 5,
    },
    {
        "shopify_variant_id": "gid://shopify/Variant/3002",
        "sku_code": "CBL-LIGHT-002",
        "title": "Lightning Cable 6ft (White)",
        "current_stock": 180,
        "location_id": "warehouse-a",
        "lead_time_days": 5,
    },
    {
        "shopify_variant_id": "gid://shopify/Variant/4001",
        "sku_code": "PHN-STND-001",
        "title": "Phone Stand Adjustable",
        "current_stock": 0,
        "location_id": "warehouse-c",
        "lead_time_days": 7,
    },
    {
        "shopify_variant_id": "gid://shopify/Variant/5001",
        "sku_code": "TAP-BLU-001",
        "title": "Mechanical Keyboard Blue Switch",
        "current_stock": 8,
        "location_id": "warehouse-a",
        "lead_time_days": 14,
    },
    {
        "shopify_variant_id": "gid://shopify/Variant/6001",
        "sku_code": "MON-27-4K-001",
        "title": '27" 4K Monitor',
        "current_stock": 15,
        "location_id": "warehouse-b",
        "lead_time_days": 21,
    },
]


def _generate_sales_history(sku_id: int, days: int = 90) -> list[tuple]:
    """Generate realistic sales history for a SKU over the last N days.

    Each SKU gets a different velocity pattern so the forecasting
    engine produces varied, realistic results.
    """
    import random

    random.seed(sku_id * 7 + 42)
    history = []
    base_velocity = random.uniform(1.0, 40.0)

    for day_offset in range(days):
        d = date.today() - timedelta(days=days - day_offset)
        weekly_multiplier = 1.0
        if d.weekday() in (4, 5):
            weekly_multiplier = 0.3  # lower on weekends
        seasonal = 1.0 + 0.2 * (1 if d.month in (11, 12) else -0.1 if d.month in (1, 2) else 0)
        units = max(0, int(base_velocity * weekly_multiplier * seasonal + random.gauss(0, 3)))
        if units > 0:
            history.append((sku_id, d, units))

    return history


async def seed_demo_data():
    async with engine.begin() as conn:
        await conn.run_sync(Sku.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        existing = (await session.execute(select(Sku))).scalars().all()
        if existing:
            print("   ℹ️  Database already has SKUs — skipping seed.")
            return

        print("   📦 Inserting 10 demo SKUs...")
        for s in DEMO_SKUS:
            sku = Sku(
                shopify_variant_id=s["shopify_variant_id"],
                sku_code=s["sku_code"],
                title=s["title"],
                current_stock=s["current_stock"],
                location_id=s["location_id"],
                merchant_id=0,
            )
            session.add(sku)
            await session.flush()

            s["_id"] = sku.id

        await session.commit()

        print("   📊 Generating 90-day sales history...")
        all_rows = []
        for s in DEMO_SKUS:
            rows = _generate_sales_history(s["_id"], days=90)
            all_rows.extend(rows)

        for sku_id, sale_date, units in all_rows:
            stmt = (
                __import__("sqlalchemy.dialects.postgresql", fromlist=["insert"])
                .insert(SalesHistory)
                .values(sku_id=sku_id, date=sale_date, units_sold=units)
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_sales_history_sku_date",
                set_={"units_sold": SalesHistory.units_sold + stmt.excluded.units_sold},
            )
            await session.execute(stmt)

        await session.commit()

        print(f"   ✅ Inserted {len(DEMO_SKUS)} SKUs + {len(all_rows)} sales records.")
        print("   🚨 SKUs at critical/low stock:")
        for s in DEMO_SKUS:
            if s["current_stock"] <= 5:
                print(f"      ⚠️  {s['sku_code']} — {s['title']} — stock: {s['current_stock']}")


if __name__ == "__main__":
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://inventory:inventory@localhost:5432/inventory_agent")
    asyncio.run(seed_demo_data())
