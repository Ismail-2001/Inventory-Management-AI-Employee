import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict

import httpx
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from agent.config import settings
from agent.db import async_session_factory
from agent.models import SalesHistory, Sku


def _shopify_client() -> httpx.AsyncClient:
    headers = {
        "X-Shopify-Access-Token": settings.shopify_admin_api_token,
        "Content-Type": "application/json",
    }
    base_url = f"https://{settings.shopify_store_domain}/admin/api/{settings.shopify_api_version}/graphql.json"
    client = httpx.AsyncClient(base_url=base_url, headers=headers, timeout=httpx.Timeout(10.0))
    return client


def _extract_stock_from_levels(levels: list, fallback_stock: int, fallback_location_id: int | None = None) -> tuple[int, int | None]:
    stock = fallback_stock
    location_id = fallback_location_id
    for le in levels:
        loc = le["node"].get("location", {})
        location_id = _parse_gid(loc["id"]) if loc.get("id") else location_id
        quantities = le["node"].get("quantities", [])
        if isinstance(quantities, list):
            for qe in quantities:
                stock = qe.get("quantity", stock)
                break
        elif isinstance(quantities, dict):
            edges = quantities.get("edges", [])
            for qe in edges:
                stock = qe.get("node", {}).get("quantity", stock)
                break
        break
    return stock, location_id


PRODUCTS_QUERY = """
query ProductsQuery($cursor: String) {
  products(first: 50, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id
        title
        variants(first: 50) {
          edges {
            node {
              id
              sku
              inventoryQuantity
              inventoryItem {
                id
                inventoryLevels(first: 5) {
                  edges {
                    node {
                      location { id }
                      quantities(names: "available") { quantity }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""


def _parse_gid(gid: str) -> str:
    return gid.split("/")[-1]


async def _shopify_call(client: httpx.AsyncClient, json: dict) -> dict:
    for attempt in range(3):
        resp = await client.post("", json=json)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "5"))
            await asyncio.sleep(retry_after * (2 ** attempt))
            continue
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            raise RuntimeError(f"Shopify GraphQL error: {data['errors']}")
        return data
    raise RuntimeError("Shopify API rate limited after 3 retries")


async def sync_products_and_inventory() -> int:
    synced = 0
    async with _shopify_client() as client:
        cursor: str | None = None
        has_next = True

        while has_next:
            data = await _shopify_call(
                client,
                {"query": PRODUCTS_QUERY, "variables": {"cursor": cursor}},
            )

            products = data["data"]["products"]
            batch = []
            for edge in products["edges"]:
                product = edge["node"]
                product_title = product["title"]
                for ve in product["variants"]["edges"]:
                    variant = ve["node"]
                    variant_id = _parse_gid(variant["id"])
                    sku_code = variant.get("sku") or variant_id
                    stock = variant.get("inventoryQuantity") or 0

                    location_id = None
                    inv_item = variant.get("inventoryItem")
                    if inv_item:
                        levels = inv_item.get("inventoryLevels", {}).get("edges", [])
                        stock, location_id = _extract_stock_from_levels(levels, stock)

                    stmt = pg_insert(Sku).values(
                        shopify_variant_id=variant_id,
                        sku_code=sku_code,
                        title=product_title,
                        current_stock=stock,
                        location_id=location_id,
                    )
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["shopify_variant_id"],
                        set_={
                            "sku_code": stmt.excluded.sku_code,
                            "title": stmt.excluded.title,
                            "current_stock": stmt.excluded.current_stock,
                            "location_id": stmt.excluded.location_id,
                            "updated_at": func.now(),
                        },
                    )
                    batch.append(stmt)

            if batch:
                async with async_session_factory() as session:
                    for stmt in batch:
                        await session.execute(stmt)
                    await session.commit()
                    synced += len(batch)

            has_next = products["pageInfo"]["hasNextPage"]
            cursor = products["pageInfo"]["endCursor"]

    return synced


async def sync_single_variant(shopify_inventory_item_id: str) -> bool:
    """Fetch and upsert exactly one variant via its inventory item id - used
    by the inventory_levels webhook so a single stock change doesn't trigger
    a full catalog resync. Shopify's inventory_levels/update payload gives us
    an inventory_item_id, which is a distinct gid type from a variant id, so
    this queries InventoryItem and reads the linked variant off it.
    """
    gid = f"gid://shopify/InventoryItem/{shopify_inventory_item_id}"
    query = """
    query InventoryItemQuery($id: ID!) {
      inventoryItem(id: $id) {
        id
        variant {
          id
          sku
          inventoryQuantity
          product { title }
        }
        inventoryLevels(first: 5) {
          edges { node { location { id } quantities(names: "available") { name quantity } } }
        }
      }
    }
    """
    async with _shopify_client() as client:
        data = await _shopify_call(
            client,
            {"query": query, "variables": {"id": gid}},
        )

        item = data["data"].get("inventoryItem")
        if not item or not item.get("variant"):
            return False

        variant = item["variant"]
        variant_id = _parse_gid(variant["id"])
        sku_code = variant.get("sku") or variant_id
        stock = variant.get("inventoryQuantity") or 0
        title = variant.get("product", {}).get("title", "")

        location_id = None
        levels = item.get("inventoryLevels", {}).get("edges", [])
        stock, location_id = _extract_stock_from_levels(levels, stock)

        async with async_session_factory() as session:
            stmt = pg_insert(Sku).values(
                shopify_variant_id=variant_id,
                sku_code=sku_code,
                title=title,
                current_stock=stock,
                location_id=location_id,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["shopify_variant_id"],
                set_={
                    "sku_code": stmt.excluded.sku_code,
                    "title": stmt.excluded.title,
                    "current_stock": stmt.excluded.current_stock,
                    "location_id": stmt.excluded.location_id,
                    "updated_at": func.now(),
                },
            )
            await session.execute(stmt)
            await session.commit()

    return True


ORDERS_QUERY = """
query OrdersQuery($cursor: String, $since: String!) {
  orders(first: 50, after: $cursor, query: $since, sortKey: CREATED_AT) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        createdAt
        lineItems(first: 50) {
          edges {
            node {
              sku
              quantity
              product { id }
              variant { id sku }
            }
          }
        }
      }
    }
  }
}
"""


def _parse_shopify_date(d: str) -> date:
    return datetime.fromisoformat(d.replace("Z", "+00:00")).date()


async def sync_sales_history(days: int = 90) -> int:
    since_ts = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")
    since = f"created_at:>={since_ts}"
    synced = 0
    async with _shopify_client() as client:
        cursor: str | None = None
        has_next = True

        while has_next:
            data = await _shopify_call(
                client,
                {
                    "query": ORDERS_QUERY,
                    "variables": {"cursor": cursor, "since": since},
                },
            )

            orders = data["data"]["orders"]
            batch = []
            sku_lookups: list[tuple[int, str, int, date]] = []

            for edge in orders["edges"]:
                order = edge["node"]
                order_date = _parse_shopify_date(order["createdAt"])
                for le in order["lineItems"]["edges"]:
                    li = le["node"]
                    variant_id: str | None = None
                    var = li.get("variant")
                    if var and var.get("id"):
                        variant_id = _parse_gid(var["id"])
                    quantity = li.get("quantity", 0)
                    if quantity <= 0:
                        continue

                    sku_code: str | None = (var or {}).get("sku") or li.get("sku")
                    if not sku_code and not variant_id:
                        continue

                    sku_lookups.append((0, sku_code or "", variant_id or "", quantity))
                    batch.append((order_date, quantity, sku_code, variant_id))

            if not batch:
                has_next = orders["pageInfo"]["hasNextPage"]
                cursor = orders["pageInfo"]["endCursor"]
                continue

            async with async_session_factory() as session:
                sku_by_code: dict[str, Sku] = {}
                sku_by_vid: dict[str, Sku] = {}

                all_sku_codes = [b[2] for b in batch if b[2]]
                all_variant_ids = [b[3] for b in batch if b[3]]

                if all_sku_codes:
                    result = await session.execute(
                        select(Sku).where(Sku.sku_code.in_(all_sku_codes))
                    )
                    for s in result.scalars().all():
                        sku_by_code[s.sku_code] = s

                if all_variant_ids:
                    result = await session.execute(
                        select(Sku).where(Sku.shopify_variant_id.in_(all_variant_ids))
                    )
                    for s in result.scalars().all():
                        sku_by_vid[s.shopify_variant_id] = s

                for order_date, quantity, sku_code, variant_id in batch:
                    sku = None
                    if sku_code and sku_code in sku_by_code:
                        sku = sku_by_code[sku_code]
                    if sku is None and variant_id and variant_id in sku_by_vid:
                        sku = sku_by_vid[variant_id]
                    if sku is None:
                        continue

                    stmt = pg_insert(SalesHistory).values(
                        sku_id=sku.id,
                        date=order_date,
                        units_sold=quantity,
                    )
                    stmt = stmt.on_conflict_do_update(
                        constraint="uq_sales_history_sku_date",
                        set_={"units_sold": SalesHistory.units_sold + quantity},
                    )
                    await session.execute(stmt)
                    synced += 1

                await session.commit()

            has_next = orders["pageInfo"]["hasNextPage"]
            cursor = orders["pageInfo"]["endCursor"]

    return synced
