import secrets
from typing import Any

from fastapi import HTTPException
from passlib.hash import bcrypt
from sqlalchemy import select

from agent.db import async_session_factory, session_scope
from agent.models import Merchant

_KEY_PREFIX = "sk_live_"


def generate_api_key() -> tuple[str, str, str]:
    """Returns (raw_key, key_prefix, hashed_key)."""
    raw = _KEY_PREFIX + secrets.token_hex(32)
    prefix = raw[:8]
    hashed = bcrypt.hash(raw)
    return raw, prefix, hashed


async def create_merchant_api_key(name: str, shopify_store_domain: str, tier: str = "developer") -> str:
    """Create a new merchant and return the raw API key (shown once)."""
    if tier not in ("developer", "business", "enterprise"):
        tier = "developer"
    raw, prefix, hashed = generate_api_key()
    merchant = Merchant(
        name=name,
        hashed_api_key=hashed,
        key_prefix=prefix,
        shopify_store_domain=shopify_store_domain,
        tier=tier,
    )
    async with session_scope(async_session_factory) as session:
        session.add(merchant)
        await session.commit()
    return raw


async def rotate_api_key(merchant_id: int) -> str:
    """Generate a new key for an existing merchant, return raw key."""
    raw, prefix, hashed = generate_api_key()
    async with session_scope(async_session_factory) as session:
        result = await session.execute(select(Merchant).where(Merchant.id == merchant_id))
        merchant = result.scalar_one_or_none()
        if not merchant:
            raise HTTPException(status_code=404, detail="Merchant not found")
        merchant.hashed_api_key = hashed
        merchant.key_prefix = prefix
        await session.commit()
    return raw


async def revoke_api_key(prefix: str) -> bool:
    """Delete a merchant by key prefix. Returns True if deleted."""
    async with session_scope(async_session_factory) as session:
        result = await session.execute(select(Merchant).where(Merchant.key_prefix == prefix))
        merchant = result.scalar_one_or_none()
        if not merchant:
            return False
        await session.delete(merchant)
        await session.commit()
    return True


async def list_merchant_keys(merchant_id: int) -> list[dict[str, Any]]:
    """List key prefixes and names for a merchant."""
    if merchant_id == 0:
        return []
    async with session_scope(async_session_factory) as session:
        result = await session.execute(
            select(Merchant).where(Merchant.id == merchant_id)
        )
        merchants = result.scalars().all()
    return [
        {
            "key_prefix": m.key_prefix,
            "name": m.name,
            "shopify_store_domain": m.shopify_store_domain,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in merchants
    ]
