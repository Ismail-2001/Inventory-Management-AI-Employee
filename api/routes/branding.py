"""White-Label Branding API Routes.

Endpoints:
    GET  /api/v1/branding         — Get current merchant's branding
    PUT  /api/v1/branding         — Update merchant branding
    GET  /api/v1/branding/{id}    — Get branding by merchant ID (admin)
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from agent.auth import require_role, verify_api_key
from agent.models import Merchant
from shared.whitelabel import MerchantBranding, get_branding, update_branding

router = APIRouter(prefix="/api/v1/branding", tags=["branding"])


class BrandingUpdateRequest(BaseModel):
    logo_url: str | None = None
    primary_color: str | None = None
    secondary_color: str | None = None
    company_name: str | None = None
    support_email: str | None = None
    custom_domain: str | None = None
    favicon_url: str | None = None
    login_heading: str | None = None
    login_subheading: str | None = None


class BrandingResponse(BaseModel):
    merchant_id: int
    logo_url: str
    primary_color: str
    secondary_color: str
    company_name: str
    support_email: str
    custom_domain: str
    favicon_url: str
    login_heading: str
    login_subheading: str


def _to_response(branding: MerchantBranding) -> BrandingResponse:
    return BrandingResponse(
        merchant_id=branding.merchant_id,
        logo_url=branding.logo_url,
        primary_color=branding.primary_color,
        secondary_color=branding.secondary_color,
        company_name=branding.company_name,
        support_email=branding.support_email,
        custom_domain=branding.custom_domain,
        favicon_url=branding.favicon_url,
        login_heading=branding.login_heading,
        login_subheading=branding.login_subheading,
    )


@router.get("", response_model=BrandingResponse)
async def get_my_branding(merchant: Merchant = Depends(verify_api_key)) -> BrandingResponse:
    branding = await get_branding(merchant.id)
    return _to_response(branding)


@router.put("", response_model=BrandingResponse)
async def update_my_branding(
    body: BrandingUpdateRequest,
    merchant: Merchant = Depends(require_role("admin")),
) -> BrandingResponse:
    update_data = {k: v for k, v in body.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        branding = await update_branding(merchant.id, update_data)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _to_response(branding)


@router.get("/{target_merchant_id}", response_model=BrandingResponse)
async def get_branding_by_id(
    target_merchant_id: int,
    merchant: Merchant = Depends(require_role("admin")),
) -> BrandingResponse:
    branding = await get_branding(target_merchant_id)
    return _to_response(branding)
