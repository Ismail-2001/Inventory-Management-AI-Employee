from sqlalchemy import select

from agent.db import async_session_factory
from agent.models import Sku
from agent.shopify_sync import sync_products_and_inventory, sync_sales_history
from agent.telemetry import trace_node


from agent.config import settings


@trace_node("sync")
async def sync_node(state: dict) -> dict:
    synced_products = 0
    synced_sales = 0

    if settings.shopify_store_domain:
        synced_products = await sync_products_and_inventory()
        synced_sales = await sync_sales_history(days=90)

    async with async_session_factory() as session:
        q = select(Sku)
        mid = state.get("merchant_id")
        if mid and mid != 0:
            q = q.where(Sku.merchant_id == mid)
        result = await session.execute(q)
        skus = result.scalars().all()
        sku_list = [
            {
                "id": s.id,
                "shopify_variant_id": s.shopify_variant_id,
                "sku_code": s.sku_code,
                "title": s.title,
                "current_stock": s.current_stock,
                "location_id": s.location_id,
                "lead_time_days": 7,
            }
            for s in skus
        ]

    return {
        **state,
        "skus": sku_list,
        "synced_products": synced_products,
        "synced_sales": synced_sales,
    }