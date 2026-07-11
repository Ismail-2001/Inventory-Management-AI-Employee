from sqlalchemy import select

from agent.db import async_session_factory
from agent.models import Sku
from agent.shopify_sync import sync_products_and_inventory, sync_sales_history
from agent.telemetry import trace_node


from agent.config import settings


@trace_node("sync")
async def sync_node(state: dict) -> dict:
    if not settings.shopify_store_domain or "placeholder" in settings.shopify_store_domain:
        return {"skus": [], "synced_products": 0, "synced_sales": 0}

    synced_products = await sync_products_and_inventory()
    synced_sales = await sync_sales_history(days=90)

    async with async_session_factory() as session:
        result = await session.execute(select(Sku))
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
        "skus": sku_list,
        "synced_products": synced_products,
        "synced_sales": synced_sales,
    }
