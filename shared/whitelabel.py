"""White-Label Branding — per-merchant custom branding and tenant isolation.

Stores branding config (logo, colors, custom domain) per merchant.
Serves branding via API and injects into frontend via /api/v1/config.
"""
import logging
from dataclasses import dataclass
from typing import Any

from agent.db import async_session_factory, session_scope
from agent.models import Merchant

logger = logging.getLogger(__name__)


@dataclass
class MerchantBranding:
    merchant_id: int
    logo_url: str = ""
    primary_color: str = "#2563eb"
    secondary_color: str = "#1e40af"
    company_name: str = ""
    support_email: str = ""
    custom_domain: str = ""
    favicon_url: str = ""
    login_heading: str = "Inventory Agent"
    login_subheading: str = "AI-powered inventory management"


_BRANDING_CACHE: dict[int, MerchantBranding] = {}


async def get_branding(merchant_id: int) -> MerchantBranding:
    if merchant_id in _BRANDING_CACHE:
        return _BRANDING_CACHE[merchant_id]

    async with session_scope(async_session_factory) as session:
        merchant = await session.get(Merchant, merchant_id)
        if not merchant:
            return MerchantBranding(merchant_id=merchant_id)

        branding_data = getattr(merchant, "branding", None) or {}
        branding = MerchantBranding(
            merchant_id=merchant_id,
            logo_url=branding_data.get("logo_url", ""),
            primary_color=branding_data.get("primary_color", "#2563eb"),
            secondary_color=branding_data.get("secondary_color", "#1e40af"),
            company_name=branding_data.get("company_name", merchant.name),
            support_email=branding_data.get("support_email", ""),
            custom_domain=branding_data.get("custom_domain", ""),
            favicon_url=branding_data.get("favicon_url", ""),
            login_heading=branding_data.get("login_heading", "Inventory Agent"),
            login_subheading=branding_data.get("login_subheading", "AI-powered inventory management"),
        )
        _BRANDING_CACHE[merchant_id] = branding
        return branding


async def update_branding(merchant_id: int, branding_data: dict[str, Any]) -> MerchantBranding:
    async with session_scope(async_session_factory) as session:
        merchant = await session.get(Merchant, merchant_id)
        if not merchant:
            raise ValueError(f"Merchant {merchant_id} not found")

        current = getattr(merchant, "branding", None) or {}
        current.update(branding_data)
        merchant.branding = current
        await session.commit()

    _BRANDING_CACHE.pop(merchant_id, None)
    return await get_branding(merchant_id)


def get_branding_for_domain(domain: str) -> int | None:
    for merchant_id, branding in _BRANDING_CACHE.items():
        if branding.custom_domain == domain:
            return merchant_id
    return None


def clear_branding_cache(merchant_id: int | None = None) -> None:
    if merchant_id:
        _BRANDING_CACHE.pop(merchant_id, None)
    else:
        _BRANDING_CACHE.clear()
