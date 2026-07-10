from fastapi import Depends, HTTPException, Header
from passlib.hash import bcrypt
from sqlalchemy import select

from agent.config import settings
from agent.db import async_session_factory
from agent.models import Merchant, User


def _hexdigest(key: str) -> str:
    return bcrypt.hash(key)


async def verify_api_key(x_api_key: str = Header(None)) -> Merchant:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    if x_api_key == settings.agent_api_key:
        return Merchant(
            id=0,
            name="Demo Merchant",
            hashed_api_key=_hexdigest(x_api_key),
            shopify_store_domain=settings.shopify_store_domain,
        )

    async with async_session_factory() as session:
        result = await session.execute(select(Merchant))
        merchants = result.scalars().all()

    for merchant in merchants:
        try:
            if bcrypt.verify(x_api_key, merchant.hashed_api_key):
                return merchant
        except Exception:
            continue

    raise HTTPException(status_code=401, detail="Invalid API key")


async def get_current_user(merchant: Merchant = Depends(verify_api_key)) -> User | None:
    if merchant.id == 0:
        return User(id=0, merchant_id=0, email="demo@example.com", role="owner")
    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.merchant_id == merchant.id).limit(1)
        )
        return result.scalar_one_or_none()


def require_role(*roles: str):
    async def dependency(current_user: User | None = Depends(get_current_user)):
        if not current_user:
            raise HTTPException(status_code=403, detail="Access denied")
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail=f"Requires one of: {', '.join(roles)}")
        return current_user
    return dependency
