"""Tests for SSO, Audit, and White-Label Enterprise Features."""

from unittest.mock import patch

import pytest

from agent.audit import log, log_audit_event
from agent.config import settings
from agent.sso import SSOSession, get_sso_providers, validate_email_domain
from shared.whitelabel import MerchantBranding, clear_branding_cache

# ── SSO Session Token Tests ──────────────────────────────────────────


def test_sso_session_create_and_verify():
    session = SSOSession("test-secret-key")
    token = session.create_token(user_id=1, merchant_id=42, email="user@acme.com", role="admin")
    assert isinstance(token, str)
    assert len(token) > 20

    data = session.verify_token(token)
    assert data is not None
    assert data["user_id"] == 1
    assert data["merchant_id"] == 42
    assert data["email"] == "user@acme.com"
    assert data["role"] == "admin"


def test_sso_session_rejects_expired():
    session = SSOSession("test-secret-key")
    token = session.create_token(user_id=1, merchant_id=1, email="u@e.com", role="staff", ttl_seconds=-1)
    data = session.verify_token(token)
    assert data is None


def test_sso_session_rejects_tampered():
    session = SSOSession("test-secret-key")
    token = session.create_token(user_id=1, merchant_id=1, email="u@e.com", role="staff")
    tampered = token[:-5] + "XXXXX"
    data = session.verify_token(tampered)
    assert data is None


def test_sso_session_rejects_wrong_secret():
    s1 = SSOSession("secret-1")
    s2 = SSOSession("secret-2")
    token = s1.create_token(user_id=1, merchant_id=1, email="u@e.com", role="staff")
    data = s2.verify_token(token)
    assert data is None


def test_sso_session_rejects_garbage():
    session = SSOSession("test")
    assert session.verify_token("not-a-token") is None
    assert session.verify_token("") is None
    assert session.verify_token("a:b:c") is None


# ── Email Domain Validation Tests ────────────────────────────────────


def test_validate_email_domain_no_restrictions():
    assert validate_email_domain("user@example.com", []) is True


def test_validate_email_domain_allowed():
    assert validate_email_domain("user@acme.com", ["acme.com"]) is True
    assert validate_email_domain("user@Acme.COM", ["acme.com"]) is True


def test_validate_email_domain_not_allowed():
    assert validate_email_domain("user@evil.com", ["acme.com"]) is False


def test_validate_email_domain_multiple():
    assert validate_email_domain("u@acme.com", ["acme.com", "corp.com"]) is True
    assert validate_email_domain("u@corp.com", ["acme.com", "corp.com"]) is True
    assert validate_email_domain("u@other.com", ["acme.com", "corp.com"]) is False


# ── SSO Provider Config Tests ────────────────────────────────────────


def test_get_sso_providers_empty_by_default():
    with patch.object(settings, "sso_oidc_client_id", ""), patch.object(settings, "sso_saml_entity_id", ""):
        providers = get_sso_providers()
        assert providers == []


def test_get_sso_providers_oidc():
    with (
        patch.object(settings, "sso_oidc_client_id", "client-123"),
        patch.object(settings, "sso_oidc_client_secret", "secret-456"),
        patch.object(
            settings, "sso_oidc_discovery_url", "https://accounts.google.com/.well-known/openid-configuration"
        ),
        patch.object(settings, "sso_oidc_name", "Google"),
        patch.object(settings, "sso_saml_entity_id", ""),
        patch.object(settings, "sso_allowed_domains", "acme.com"),
        patch.object(settings, "public_api_url", "http://localhost:8002"),
    ):
        providers = get_sso_providers()
        assert len(providers) == 1
        assert providers[0].name == "Google"
        assert providers[0].provider_type == "oidc"
        assert "acme.com" in providers[0].allowed_domains


# ── Audit Log Tests ──────────────────────────────────────────────────


class FakeAuditSession:
    def __init__(self):
        self.added = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def add(self, item):
        self.added.append(item)

    async def commit(self):
        self.committed = True


class FakeAuditSessionFactory:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return self._session


@pytest.mark.asyncio
async def test_log_audit_event_structure():
    session = FakeAuditSession()
    factory = FakeAuditSessionFactory(session)
    with patch("agent.audit.async_session_factory", factory):
        await log_audit_event(
            merchant_id=10,
            actor_type="api_key",
            actor_id="user@test.com",
            action="po.approve",
            target_type="purchase_order",
            target_id=42,
            details={"quantity": 100},
            ip_address="127.0.0.1",
        )
    assert len(session.added) == 1
    entry = session.added[0]
    assert entry.merchant_id == 10
    assert entry.actor_type == "api_key"
    assert entry.action == "po.approve"
    assert entry.target_type == "purchase_order"
    assert entry.target_id == "42"
    assert entry.details["quantity"] == 100
    assert entry.details["ip_address"] == "127.0.0.1"


@pytest.mark.asyncio
async def test_legacy_log_function():
    session = FakeAuditSession()
    factory = FakeAuditSessionFactory(session)
    with patch("agent.audit.async_session_factory", factory):
        await log(action="test_action", merchant_id=5, details={"key": "val"})
    assert len(session.added) == 1
    entry = session.added[0]
    assert entry.action == "test_action"
    assert entry.merchant_id == 5
    assert entry.details["key"] == "val"


# ── White-Label Branding Tests ───────────────────────────────────────


def test_merchant_branding_defaults():
    branding = MerchantBranding(merchant_id=1)
    assert branding.primary_color == "#2563eb"
    assert branding.secondary_color == "#1e40af"
    assert branding.login_heading == "Inventory Agent"
    assert branding.logo_url == ""


def test_merchant_branding_custom():
    branding = MerchantBranding(
        merchant_id=1,
        logo_url="https://example.com/logo.png",
        primary_color="#ff0000",
        company_name="Acme Corp",
    )
    assert branding.logo_url == "https://example.com/logo.png"
    assert branding.primary_color == "#ff0000"
    assert branding.company_name == "Acme Corp"


def test_clear_branding_cache():
    clear_branding_cache()
    assert True  # No error


def test_get_branding_by_domain_no_match():
    clear_branding_cache()
    from shared.whitelabel import get_branding_for_domain

    result = get_branding_for_domain("nonexistent.com")
    assert result is None
