from datetime import date, datetime, timedelta
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


async def sync_products_and_inventory() -> int:
    synced = 0
    async with _shopify_client() as client:
        cursor: str | None = None
        has_next = True

        while has_next:
            resp = await client.post(
                "",
                json={"query": PRODUCTS_QUERY, "variables": {"cursor": cursor}},
            )
            resp.raise_for_status()
            data = resp.json()
            if "errors" in data:
                raise RuntimeError(f"Shopify GraphQL error: {data['errors']}")

            products = data["data"]["products"]
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
                        for le in levels:
                            loc = le["node"].get("location", {})
                            location_id = _parse_gid(loc["id"]) if loc.get("id") else None
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

                    async with async_session_factory() as session:
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
                        await session.execute(stmt)
                        await session.commit()
                        synced += 1

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
        resp = await client.post("", json={"query": query, "variables": {"id": gid}})
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            raise RuntimeError(f"Shopify GraphQL error: {data['errors']}")

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
        for le in levels:
            loc = le["node"].get("location", {})
            location_id = _parse_gid(loc["id"]) if loc.get("id") else None
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
    since_ts = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")
    since = f"created_at:>={since_ts}"
    synced = 0
    async with _shopify_client() as client:
        cursor: str | None = None
        has_next = True

        while has_next:
            resp = await client.post(
                "",
                json={
                    "query": ORDERS_QUERY,
                    "variables": {"cursor": cursor, "since": since},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if "errors" in data:
                raise RuntimeError(f"Shopify GraphQL error: {data['errors']}")

            orders = data["data"]["orders"]
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

                    async with async_session_factory() as session:
                        sku = None
                        if sku_code:
                            result = await session.execute(
                                select(Sku).where(Sku.sku_code == sku_code).limit(1)
                            )
                            sku = result.scalar_one_or_none()
                        if sku is None and variant_id:
                            result = await session.execute(
                                select(Sku).where(Sku.shopify_variant_id == variant_id).limit(1)
                            )
                            sku = result.scalar_one_or_none()
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
                        await session.commit()
                        synced += 1

            has_next = orders["pageInfo"]["hasNextPage"]
            cursor = orders["pageInfo"]["endCursor"]

    return synced
