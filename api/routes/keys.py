from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from agent.auth import require_role, verify_api_key
from agent.models import Merchant
from agent.security import create_merchant_api_key, list_merchant_keys, revoke_api_key, rotate_api_key
from api.rate_limit import limiter

router = APIRouter()


@router.post("/api/v1/keys")
@limiter.limit("3/minute")
async def create_key(
    request: Request,
    name: str = "default",
    shopify_store_domain: str = "",
    tier: str = "developer",
    merchant: Merchant = Depends(verify_api_key),
    _: Any = Depends(require_role("owner")),
) -> dict[str, Any]:
    raw = await create_merchant_api_key(name, shopify_store_domain, tier)
    return {
        "api_key": raw,
        "tier": tier,
        "warning": "Save this key — it will not be shown again.",
    }


@router.get("/api/v1/keys")
@limiter.limit("10/minute")
async def list_keys(
    request: Request,
    merchant: Merchant = Depends(verify_api_key),
    _: Any = Depends(require_role("owner")),
) -> dict[str, Any]:
    keys = await list_merchant_keys(merchant.id)
    return {"keys": keys}


@router.post("/api/v1/keys/rotate")
@limiter.limit("3/minute")
async def rotate_key(
    request: Request,
    merchant: Merchant = Depends(verify_api_key),
    _: Any = Depends(require_role("owner")),
) -> dict[str, Any]:
    raw = await rotate_api_key(merchant.id)
    return {"api_key": raw, "warning": "Save this key — it will not be shown again."}


@router.delete("/api/v1/keys/{prefix}")
@limiter.limit("3/minute")
async def delete_key(
    request: Request,
    prefix: str,
    merchant: Merchant = Depends(verify_api_key),
    _: Any = Depends(require_role("owner")),
) -> dict[str, Any]:
    ok = await revoke_api_key(prefix)
    if not ok:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"status": "revoked"}
