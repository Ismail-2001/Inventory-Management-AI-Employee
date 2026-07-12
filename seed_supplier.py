"""Seed a test supplier so POs have real cost data."""
import asyncio
from agent.db import async_session_factory
from agent.models import Supplier, Sku
from sqlalchemy import select


async def main():
    async with async_session_factory() as session:
        # Find the Compare at Price Snowboard
        result = await session.execute(
            select(Sku).where(Sku.title == "The Compare at Price Snowboard").limit(1)
        )
        sku = result.scalar_one_or_none()
        if not sku:
            print("SKU 'The Compare at Price Snowboard' not found!")
            return

        print(f"Found SKU: id={sku.id} title={sku.title!r} sku_code={sku.sku_code!r}")

        # Upsert supplier
        existing = await session.execute(
            select(Supplier).where(Supplier.name == "Test Supplier").limit(1)
        )
        supplier = existing.scalar_one_or_none()

        if supplier:
            print(f"Supplier already exists: id={supplier.id} — updating...")
            supplier.default_lead_time_days = 7
            supplier.moq_by_sku = {sku.sku_code: 10}
            supplier.unit_cost_by_sku = {sku.sku_code: 15.0}
        else:
            supplier = Supplier(
                name="Test Supplier",
                default_lead_time_days=7,
                moq_by_sku={sku.sku_code: 10},
                unit_cost_by_sku={sku.sku_code: 15.0},
            )
            session.add(supplier)

        await session.commit()
        await session.refresh(supplier)
        print(f"Supplier ready: id={supplier.id} name={supplier.name!r}")
        print(f"  lead_time={supplier.default_lead_time_days}")
        print(f"  moq_by_sku={supplier.moq_by_sku}")
        print(f"  unit_cost_by_sku={supplier.unit_cost_by_sku}")


asyncio.run(main())
