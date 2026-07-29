from fastapi import APIRouter, Request

from agent.webhooks import (
    handle_inventory_update,
    handle_order_create,
    handle_product_update,
    handle_webhook_event,
)

router = APIRouter()


@router.post("/api/v1/webhooks/inventory_levels_update")
async def webhook_inventory_update(request: Request):
    return await handle_webhook_event(request, "inventory_levels_update", handle_inventory_update)


@router.post("/api/v1/webhooks/orders_create")
async def webhook_order_create(request: Request):
    return await handle_webhook_event(request, "orders_create", handle_order_create)


@router.post("/api/v1/webhooks/products_update")
async def webhook_product_update(request: Request):
    return await handle_webhook_event(request, "products_update", handle_product_update)
