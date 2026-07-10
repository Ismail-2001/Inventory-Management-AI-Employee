import json

from fastapi import APIRouter, Depends, Request

from agent.webhooks import (
    verify_shopify_webhook,
    handle_inventory_update,
    handle_order_create,
    handle_product_update,
)

router = APIRouter()


@router.post("/api/v1/webhooks/inventory_levels_update")
async def webhook_inventory_update(body: bytes = Depends(verify_shopify_webhook)):
    payload = json.loads(body)
    await handle_inventory_update(payload)
    return {"status": "ok"}


@router.post("/api/v1/webhooks/orders_create")
async def webhook_order_create(body: bytes = Depends(verify_shopify_webhook)):
    payload = json.loads(body)
    await handle_order_create(payload)
    return {"status": "ok"}


@router.post("/api/v1/webhooks/products_update")
async def webhook_product_update(body: bytes = Depends(verify_shopify_webhook)):
    payload = json.loads(body)
    await handle_product_update(payload)
    return {"status": "ok"}
