import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from agent.config import settings
from agent.db import async_session_factory
from agent.models import InventorySnapshot, Sku, Supplier
from agent.shopify_sync import sync_products_and_inventory, sync_sales_history
from agent.state import State
from agent.telemetry import trace_node

logger = logging.getLogger(__name__)


def _supplier_lead_time(raw: object) -> int:
    """Defensive: tests/fakes may return non-int rows; default matches Supplier."""
    if isinstance(raw, bool) or not isinstance(raw, int):
        return 7
    return raw if raw > 0 else 7


@trace_node("sync")
async def sync_node(state: State) -> State:
    synced_products = 0
    synced_sales = 0

    if settings.shopify_store_domain:
        synced_products = await sync_products_and_inventory()
        synced_sales = await sync_sales_history(days=settings.sync_days)

    lead_time_days = 7
    async with async_session_factory() as session:
        supplier_lt = (
            (await session.execute(select(Supplier.default_lead_time_days).order_by(Supplier.id).limit(1)))
            .scalars()
            .first()
        )
        lead_time_days = _supplier_lead_time(supplier_lt)

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
                "lead_time_days": lead_time_days,
            }
            for s in skus
        ]

        # Accrue stock snapshots for evidence-based stockout detection.
        # Best-effort: a lagging schema must never break the pipeline.
        try:
            today = date.today()
            for s in skus:
                stmt = pg_insert(InventorySnapshot).values(
                    sku_id=s.id, date=today, stock_level=s.current_stock, source="sync"
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["sku_id", "date"],
                    set_={"stock_level": stmt.excluded.stock_level, "source": "sync"},
                )
                await session.execute(stmt)
            await session.commit()
        except Exception:
            logger.warning("inventory snapshot upsert failed", exc_info=True)
            await session.rollback()

    return {
        **state,
        "skus": sku_list,
        "synced_products": synced_products,
        "synced_sales": synced_sales,
    }
