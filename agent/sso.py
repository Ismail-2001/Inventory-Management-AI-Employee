"""SSO Authentication — OIDC and SAML support alongside API key auth.

Supports:
- OpenID Connect (Google Workspace, Azure AD, Okta, Auth0)
- SAML 2.0 (enterprise IdPs)
- JWT session tokens for SSO-authenticated users
- Fallback to API key auth when SSO not configured

Usage:
    from agent.sso import sso_authenticate, create_session_token
"""

import hashlib
import hmac
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from agent.config import settings


@dataclass
class SSOProvider:
    name: str
    provider_type: str  # "oidc" or "saml"
    client_id: str
    client_secret: str
    discovery_url: str = ""  # OIDC .well-known/openid-configuration
    idp_entity_id: str = ""  # SAML IdP entity ID
    sso_url: str = ""  # SAML SSO URL
    slo_url: str = ""  # SAML Single Logout URL
    certificate: str = ""  # SAML X.509 cert
    allowed_domains: list[str] = field(default_factory=list)
    callback_url: str = ""


OIDC_TOKEN_URL = ""  # Resolved from discovery
OIDC_USERINFO_URL = ""  # Resolved from discovery


class SSOSession:
    """JWT-like session token for SSO users."""

    def __init__(self, secret: str):
        self._secret = secret

    def create_token(self, user_id: int, merchant_id: int, email: str, role: str, ttl_seconds: int = 28800) -> str:
        expiry = int(time.time()) + ttl_seconds
        payload = f"{user_id}:{merchant_id}:{email}:{role}:{expiry}"
        sig = hmac.new(self._secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return f"{payload}:{sig}"

    def verify_token(self, token: str) -> dict[str, Any] | None:
        try:
            parts = token.split(":")
            if len(parts) != 6:
                return None
            user_id = int(parts[0])
            merchant_id = int(parts[1])
            email = parts[2]
            role = parts[3]
            expiry = int(parts[4])
            sig = parts[5]

            if time.time() > expiry:
                return None

            expected_payload = f"{user_id}:{merchant_id}:{email}:{role}:{expiry}"
            expected_sig = hmac.new(self._secret.encode(), expected_payload.encode(), hashlib.sha256).hexdigest()

            if not hmac.compare_digest(sig, expected_sig):
                return None

            return {
                "user_id": user_id,
                "merchant_id": merchant_id,
                "email": email,
                "role": role,
                "expiry": expiry,
            }
        except (ValueError, IndexError):
            return None


_sso_session: SSOSession | None = None


def get_sso_session() -> SSOSession:
    global _sso_session
    if _sso_session is None:
        _sso_session = SSOSession(settings.agent_api_key)
    return _sso_session


async def oidc_discover(discovery_url: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(discovery_url)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {}


async def oidc_exchange_code(code: str, provider: SSOProvider) -> dict[str, Any]:
    token_url = (
        provider.discovery_url.replace("/.well-known/openid-configuration", "/oauth/token")
        if provider.discovery_url
        else ""
    )

    if not token_url:
        raise ValueError("OIDC token URL not configured")

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": provider.client_id,
                "client_secret": provider.client_secret,
                "redirect_uri": provider.callback_url,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {}


async def oidc_get_userinfo(access_token: str, provider: SSOProvider) -> dict[str, Any]:
    userinfo_url = (
        provider.discovery_url.replace("/.well-known/openid-configuration", "/userinfo")
        if provider.discovery_url
        else ""
    )

    if not userinfo_url:
        raise ValueError("OIDC userinfo URL not configured")

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(userinfo_url, headers={"Authorization": f"Bearer {access_token}"})
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {}


def validate_email_domain(email: str, allowed_domains: list[str]) -> bool:
    if not allowed_domains:
        return True
    domain = email.split("@")[-1].lower()
    return domain in [d.lower() for d in allowed_domains]


def get_sso_providers() -> list[SSOProvider]:
    providers = []
    if settings.sso_oidc_client_id:
        providers.append(
            SSOProvider(
                name=settings.sso_oidc_name or "OIDC",
                provider_type="oidc",
                client_id=settings.sso_oidc_client_id,
                client_secret=settings.sso_oidc_client_secret,
                discovery_url=settings.sso_oidc_discovery_url,
                allowed_domains=[d.strip() for d in settings.sso_allowed_domains.split(",") if d.strip()],
                callback_url=f"{settings.public_api_url}/api/v1/auth/sso/callback",
            )
        )
    if settings.sso_saml_entity_id:
        providers.append(
            SSOProvider(
                name=settings.sso_saml_name or "SAML",
                provider_type="saml",
                client_id=settings.sso_saml_entity_id,
                client_secret="",
                idp_entity_id=settings.sso_saml_idp_entity_id or settings.sso_saml_entity_id,
                sso_url=settings.sso_saml_sso_url,
                slo_url=settings.sso_saml_slo_url,
                certificate=settings.sso_saml_certificate,
                allowed_domains=[d.strip() for d in settings.sso_allowed_domains.split(",") if d.strip()],
                callback_url=f"{settings.public_api_url}/api/v1/auth/sso/callback",
            )
        )
    return providers
