import base64
import hashlib
import hmac
import json
from datetime import datetime
from inspect import isawaitable
from typing import Awaitable, Callable

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from agent.config import settings
from agent.db import async_session_factory, session_scope
from agent.models import Sku, SalesHistory, WebhookEvent
from agent.shopify_sync import sync_products_and_inventory, sync_single_variant

_processed_webhook_events: set[str] = set()


async def verify_shopify_webhook(request: Request):
    body = await request.body()
    hmac_header = request.headers.get("X-Shopify-Hmac-Sha256", "")
    if not hmac_header:
        raise HTTPException(status_code=401, detail="Missing HMAC header")

    secret = settings.shopify_webhook_secret.encode() if settings.shopify_webhook_secret else b""
    if not secret:
        raise HTTPException(status_code=401, detail="Webhook secret not configured")

    expected_sig = base64.b64encode(
        hmac.new(secret, body, hashlib.sha256).digest()
    ).decode()

    if not hmac.compare_digest(expected_sig, hmac_header):
        raise HTTPException(status_code=401, detail="Invalid HMAC signature")

    return body


async def _webhook_already_processed(event_id: str | None) -> bool:
    if not event_id:
        return False
    if event_id in _processed_webhook_events:
        return True
    async with session_scope(async_session_factory) as session:
        result = await session.execute(select(WebhookEvent).where(WebhookEvent.event_id == event_id))
        return result.scalar_one_or_none() is not None


async def _mark_webhook_processed(event_id: str | None, event_type: str | None):
    if not event_id:
        return
    _processed_webhook_events.add(event_id)
    async with session_scope(async_session_factory) as session:
        session.add(WebhookEvent(event_id=event_id, event_type=event_type))
        await session.commit()


async def handle_webhook_event(request: Request, event_type: str, handler: Callable[[dict], Awaitable[None]]):
    event_id = request.headers.get("X-Shopify-Webhook-Id")
    if await _webhook_already_processed(event_id):
        return {"status": "ignored", "reason": "duplicate_webhook", "event_id": event_id}

    verified_body = verify_shopify_webhook(request)
    body = await verified_body if isawaitable(verified_body) else verified_body
    payload = json.loads(body)
    await handler(payload)

    await _mark_webhook_processed(event_id, event_type)
    return {"status": "ok", "event_id": event_id}


async def handle_inventory_update(payload: dict):
    """A single stock level changed. Fetch and upsert only that one variant
    via its inventory_item_id - never a full catalog resync."""
    inventory_item_id = str(payload.get("inventory_item_id", ""))
    if inventory_item_id:
        await sync_single_variant(inventory_item_id)


async def handle_order_create(payload: dict):
    """Shopify's orders/create payload already contains the line items with
    SKU and quantity - write straight into sales_history from the payload
    instead of calling back out to the Shopify API at all."""
    line_items = payload.get("line_items", [])
    created_at = payload.get("created_at")
    order_date = (
        datetime.fromisoformat(created_at.replace("Z", "+00:00")).date()
        if created_at
        else datetime.utcnow().date()
    )

    sku_codes = [li.get("sku") for li in line_items if li.get("sku")]
    if not sku_codes:
        return

    async with session_scope(async_session_factory) as session:
        result = await session.execute(select(Sku).where(Sku.sku_code.in_(sku_codes)))
        sku_by_code = {s.sku_code: s for s in result.scalars().all()}

        for li in line_items:
            sku_code = li.get("sku")
            quantity = li.get("quantity", 0)
            sku = sku_by_code.get(sku_code)
            if not sku or quantity <= 0:
                continue

            stmt = pg_insert(SalesHistory).values(
                sku_id=sku.id, date=order_date, units_sold=quantity
            )
            stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
            await session.execute(stmt)

        await session.commit()


async def handle_product_update(payload: dict):
    """Shopify's products/update payload already includes the full variants
    array with current inventory_quantity - upsert straight from the
    payload instead of a full catalog resync."""
    title = payload.get("title", "")
    variants = payload.get("variants", [])
    if not variants:
        return

    async with session_scope(async_session_factory) as session:
        for v in variants:
            variant_id = str(v.get("id", ""))
            if not variant_id:
                continue
            stmt = pg_insert(Sku).values(
                shopify_variant_id=variant_id,
                sku_code=v.get("sku") or variant_id,
                title=title,
                current_stock=v.get("inventory_quantity") or 0,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["shopify_variant_id"],
                set_={
                    "sku_code": stmt.excluded.sku_code,
                    "title": stmt.excluded.title,
                    "current_stock": stmt.excluded.current_stock,
                },
            )
            await session.execute(stmt)
        await session.commit()
