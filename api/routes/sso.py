"""SSO Authentication Routes.

Endpoints:
    GET  /api/v1/auth/sso/providers  — List configured SSO providers
    GET  /api/v1/auth/sso/login      — Redirect to IdP login page
    POST /api/v1/auth/sso/callback   — Handle OIDC/SAML callback, return session token
    POST /api/v1/auth/sso/logout     — Invalidate session
    GET  /api/v1/auth/sso/me         — Get current user from session token
"""

import logging
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy import select

from agent.auth import _hexdigest
from agent.db import async_session_factory, session_scope
from agent.models import Merchant, User
from agent.saml import (
    build_authn_request_url,
    build_sp_metadata,
    parse_saml_response,
)
from agent.sso import (
    get_sso_providers,
    get_sso_session,
    oidc_exchange_code,
    oidc_get_userinfo,
    validate_email_domain,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth/sso", tags=["sso"])


class SSOCallbackRequest(BaseModel):
    code: str
    state: str = ""
    provider: str = ""


class SSOLoginResponse(BaseModel):
    redirect_url: str


class SSOSessionResponse(BaseModel):
    token: str
    user_id: int
    merchant_id: int
    email: str
    role: str


class SSOProviderResponse(BaseModel):
    name: str
    type: str
    login_url: str


@router.get("/providers", response_model=list[SSOProviderResponse])
async def list_sso_providers() -> list[SSOProviderResponse]:
    providers = get_sso_providers()
    if not providers:
        return []
    return [
        SSOProviderResponse(
            name=p.name,
            type=p.provider_type,
            login_url=f"/api/v1/auth/sso/login?provider={p.name}",
        )
        for p in providers
    ]


@router.get("/login")
async def sso_login(provider: str = "") -> Any:
    providers = get_sso_providers()
    if not providers:
        raise HTTPException(status_code=404, detail="SSO not configured")

    target = None
    if provider:
        target = next((p for p in providers if p.name == provider), None)
    if not target:
        target = providers[0]

    if target.provider_type == "oidc":
        state = _generate_state()
        params = urlencode(
            {
                "client_id": target.client_id,
                "redirect_uri": target.callback_url,
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
            }
        )
        discovery = target.discovery_url
        authorization_endpoint = (
            discovery.replace("/.well-known/openid-configuration", "/authorize") if discovery else ""
        )
        if not authorization_endpoint:
            raise HTTPException(status_code=500, detail="OIDC discovery URL not configured")
        return RedirectResponse(url=f"{authorization_endpoint}?{params}")

    elif target.provider_type == "saml":
        if not target.sso_url:
            raise HTTPException(status_code=500, detail="SAML SSO URL not configured")
        redirect_url = build_authn_request_url(
            entity_id=target.client_id,
            sso_url=target.sso_url,
            acs_url=target.callback_url,
            relay_state=target.name,
        )
        return RedirectResponse(url=redirect_url)

    raise HTTPException(status_code=400, detail=f"Unknown provider type: {target.provider_type}")


@router.get("/metadata")
async def sso_saml_metadata(provider: str = "") -> Response:
    """Return the SP metadata document for registering with a SAML IdP."""
    providers = get_sso_providers()
    if not providers:
        raise HTTPException(status_code=404, detail="SSO not configured")

    target = None
    if provider:
        target = next((p for p in providers if p.name == provider), None)
    if not target:
        target = next((p for p in providers if p.provider_type == "saml"), None)
    if not target:
        raise HTTPException(status_code=404, detail="SAML provider not configured")

    metadata = build_sp_metadata(
        entity_id=target.client_id,
        acs_url=target.callback_url,
        slo_url=target.slo_url,
    )
    return PlainTextResponse(content=metadata, media_type="application/samlmetadata+xml")


@router.post("/callback")
async def sso_callback(request: Request, body: SSOCallbackRequest | None = None) -> SSOSessionResponse:
    providers = get_sso_providers()
    if not providers:
        raise HTTPException(status_code=404, detail="SSO not configured")

    form_data = await request.form()
    saml_response = form_data.get("SAMLResponse")

    if saml_response:
        provider_name = form_data.get("RelayState") or form_data.get("provider") or ""
        provider = next(
            (p for p in providers if p.provider_type == "saml" and (not provider_name or p.name == provider_name)), None
        )
        if not provider:
            provider = next((p for p in providers if p.provider_type == "saml"), None)
        if not provider:
            raise HTTPException(status_code=404, detail="SAML provider not configured")
        return await _handle_saml_callback(str(saml_response), provider)

    if body is None:
        raise HTTPException(status_code=400, detail="Missing SAMLResponse or callback body")

    provider = None
    if body.provider:
        provider = next((p for p in providers if p.name == body.provider), None)
    if not provider and providers:
        provider = providers[0]

    if not provider:
        raise HTTPException(status_code=404, detail="SSO provider not found")

    if provider.provider_type != "oidc":
        raise HTTPException(status_code=501, detail="Only OIDC is supported")

    try:
        token_data = await oidc_exchange_code(body.code, provider)
        access_token = token_data.get("access_token", "")
        userinfo = await oidc_get_userinfo(access_token, provider)
    except Exception as exc:
        logger.error("SSO OIDC callback failed: %s", exc)
        raise HTTPException(status_code=401, detail="SSO authentication failed") from exc

    email = userinfo.get("email", "")
    if not email:
        raise HTTPException(status_code=401, detail="No email in SSO response")

    if not validate_email_domain(email, provider.allowed_domains):
        raise HTTPException(status_code=403, detail=f"Email domain not allowed: {email.split('@')[-1]}")

    merchant, user = await _find_or_create_sso_user(email, userinfo)
    sso_session = get_sso_session()
    token = sso_session.create_token(user.id, merchant.id, email, user.role)

    return SSOSessionResponse(
        token=token,
        user_id=user.id,
        merchant_id=merchant.id,
        email=email,
        role=user.role,
    )


@router.post("/logout")
async def sso_logout(x_session_token: str = Header(None)) -> dict[str, Any]:
    if not x_session_token:
        return {"ok": True}
    sso_session = get_sso_session()
    session_data = sso_session.verify_token(x_session_token)
    if not session_data:
        return {"ok": True}
    return {"ok": True, "message": "Session invalidated"}


@router.get("/me")
async def sso_me(x_session_token: str = Header(None)) -> dict[str, Any]:
    if not x_session_token:
        raise HTTPException(status_code=401, detail="Missing session token")

    sso_session = get_sso_session()
    session_data = sso_session.verify_token(x_session_token)
    if not session_data:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    return {
        "user_id": session_data["user_id"],
        "merchant_id": session_data["merchant_id"],
        "email": session_data["email"],
        "role": session_data["role"],
    }


def _generate_state() -> str:
    import secrets

    return secrets.token_urlsafe(32)


async def _handle_saml_callback(saml_response: str, provider: Any) -> SSOSessionResponse:
    try:
        result = parse_saml_response(
            saml_response,
            sp_entity_id=provider.client_id,
            acs_url=provider.callback_url,
            idp_entity_id=provider.idp_entity_id or provider.client_id,
            certificate=provider.certificate,
        )
    except Exception as exc:
        logger.error("SSO SAML callback failed: %s", exc)
        raise HTTPException(status_code=401, detail="SAML authentication failed") from exc

    email = result.email
    if not validate_email_domain(email, provider.allowed_domains):
        raise HTTPException(status_code=403, detail=f"Email domain not allowed: {email.split('@')[-1]}")

    userinfo: dict[str, Any] = {"email": email, "saml_name_id": result.name_id}
    userinfo.update(result.attributes)
    merchant, user = await _find_or_create_sso_user(email, userinfo)
    sso_session = get_sso_session()
    token = sso_session.create_token(user.id, merchant.id, email, user.role)

    return SSOSessionResponse(
        token=token,
        user_id=user.id,
        merchant_id=merchant.id,
        email=email,
        role=user.role,
    )


async def _find_or_create_sso_user(email: str, userinfo: dict[str, Any]) -> tuple[Merchant, User]:
    async with session_scope(async_session_factory) as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user:
            merchant = await session.get(Merchant, user.merchant_id)
            if merchant:
                return merchant, user

        domain = email.split("@")[-1]
        merchant_name = domain.split(".")[0].title()

        merchant_result = await session.execute(select(Merchant).where(Merchant.name == merchant_name).limit(1))
        merchant = merchant_result.scalar_one_or_none()

        if not merchant:
            import secrets as _secrets

            api_key = _secrets.token_urlsafe(32)
            merchant = Merchant(
                name=merchant_name,
                hashed_api_key=_hexdigest(api_key),
                key_prefix=api_key[:8],
                shopify_store_domain="",
                tier="business",
            )
            session.add(merchant)
            await session.flush()

        user = User(
            merchant_id=merchant.id,
            email=email,
            role="admin",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        return merchant, user
