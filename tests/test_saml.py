"""SAML 2.0 tests — SP metadata, AuthnRequest, and SAMLResponse verification.

Uses a real generated IdP keypair + xmlsec to build signed SAMLResponses and
assert that agent.saml verifies them end-to-end.
"""

import base64
import datetime
import zlib
from dataclasses import dataclass

import pytest
import xmlsec
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from lxml import etree

from agent.saml import (
    SAML_NS,
    SAMLP_NS,
    SamlValidationError,
    build_authn_request_url,
    build_sp_metadata,
    parse_saml_response,
)

SP_ENTITY = "https://sp.example.com"
IDP_ENTITY = "https://idp.example.com/metadata"
ACS_URL = "https://sp.example.com/api/v1/auth/sso/callback"
IDP_SSO = "https://idp.example.com/sso"


@dataclass
class IdPFixture:
    key_pem: str
    cert_pem: str
    cert_b64: str


@pytest.fixture(scope="session")
def idp() -> IdPFixture:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "idp.example.com")]))
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "idp.example.com")]))
        .public_key(key.public_key())
        .serial_number(1000)
        .not_valid_before(datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1))
        .not_valid_after(datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    cert_b64 = "".join(cert_pem.splitlines()[1:-1]).strip()
    return IdPFixture(key_pem=key_pem, cert_pem=cert_pem, cert_b64=cert_b64)


def _build_response(
    idp: IdPFixture,
    *,
    email: str = "jane@example.com",
    audience: str = SP_ENTITY,
    recipient: str = ACS_URL,
    issuer: str = IDP_ENTITY,
    status: str = "urn:oasis:names:tc:SAML:2.0:status:Success",
    valid: bool = True,
) -> str:
    """Build a Response document and sign its assertion within the full tree."""
    root = etree.fromstring(
        f'''<samlp:Response xmlns:samlp="{SAMLP_NS}" xmlns:saml="{SAML_NS}" ID="_resp1" InResponseTo="_req1" Version="2.0" IssueInstant="2024-01-01T00:00:00Z">
  <saml:Issuer>{issuer}</saml:Issuer>
  <samlp:Status><samlp:StatusCode Value="{status}"/></samlp:Status>
  <saml:Assertion ID="_a123" IssueInstant="2024-01-01T00:00:00Z" Version="2.0">
    <saml:Issuer>{issuer}</saml:Issuer>
    <saml:Subject>
      <saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">{email}</saml:NameID>
      <saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData {'NotOnOrAfter="2030-01-01T00:00:00Z" ' if valid else ""}Recipient="{recipient}"/>
      </saml:SubjectConfirmation>
    </saml:Subject>
    <saml:Conditions {'NotBefore="2024-01-01T00:00:00Z" ' if valid else ""}NotOnOrAfter="{("2030-01-01T00:00:00Z" if valid else "2024-01-01T00:00:00Z")}">
      <saml:AudienceRestriction><saml:Audience>{audience}</saml:Audience></saml:AudienceRestriction>
    </saml:Conditions>
    <saml:AttributeStatement>
      <saml:Attribute Name="email"><saml:AttributeValue>{email}</saml:AttributeValue></saml:Attribute>
      <saml:Attribute Name="first_name"><saml:AttributeValue>Jane</saml:AttributeValue></saml:Attribute>
    </saml:AttributeStatement>
  </saml:Assertion>
</samlp:Response>'''.encode()
    )

    assertion = root.find(f"{{{SAML_NS}}}Assertion")
    sign_key = xmlsec.Key.from_memory(idp.key_pem.encode(), xmlsec.KeyFormat.PEM)
    sign_key.load_cert_from_memory(idp.cert_pem.encode(), xmlsec.KeyFormat.CERT_PEM)
    tmpl = xmlsec.template.create(assertion, xmlsec.Transform.EXCL_C14N, xmlsec.Transform.RSA_SHA256)
    ref = xmlsec.template.add_reference(tmpl, xmlsec.Transform.SHA256, uri="#_a123")
    xmlsec.template.add_transform(ref, xmlsec.Transform.ENVELOPED)
    keyinfo = xmlsec.template.ensure_key_info(tmpl)
    xmlsec.template.add_x509_data(keyinfo)
    assertion.insert(0, tmpl)
    ctx = xmlsec.SignatureContext()
    ctx.key = sign_key
    xmlsec.tree.add_ids(root, ["ID", "Id", "id"])
    ctx.sign(tmpl)

    return base64.b64encode(etree.tostring(root, xml_declaration=False)).decode()


def test_build_sp_metadata():
    md = build_sp_metadata(SP_ENTITY, ACS_URL)
    assert "SPSSODescriptor" in md
    assert SP_ENTITY in md
    assert ACS_URL in md
    assert "AssertionConsumerService" in md


def test_build_sp_metadata_with_slo():
    md = build_sp_metadata(SP_ENTITY, ACS_URL, slo_url="https://sp.example.com/logout")
    assert "SingleLogoutService" in md
    assert "https://sp.example.com/logout" in md


def test_build_authn_request_url():
    url = build_authn_request_url(SP_ENTITY, IDP_SSO, ACS_URL, relay_state="Okta")
    assert url.startswith(IDP_SSO)
    assert "SAMLRequest=" in url
    assert "RelayState=Okta" in url
    # decoded SAMLRequest should decompress back to an AuthnRequest
    from urllib.parse import parse_qs, urlparse

    query = parse_qs(urlparse(url).query)
    raw = query["SAMLRequest"][0]
    decoded = base64.b64decode(raw)
    inflated = zlib.decompress(decoded, -zlib.MAX_WBITS)
    assert b"AuthnRequest" in inflated
    assert SP_ENTITY.encode() in inflated


def test_parse_valid_saml_response(idp):
    response = _build_response(idp)
    result = parse_saml_response(
        response,
        sp_entity_id=SP_ENTITY,
        acs_url=ACS_URL,
        idp_entity_id=IDP_ENTITY,
        certificate=idp.cert_b64,
    )
    assert result.email == "jane@example.com"
    assert result.name_id == "jane@example.com"
    assert result.attributes["first_name"] == "Jane"


def test_parse_rejects_tampered_response(idp):
    response = _build_response(idp)
    # corrupt the signed assertion content
    payload = base64.b64decode(response).decode()
    payload = payload.replace("jane@example.com", "mallory@example.com")
    tampered = base64.b64encode(payload.encode()).decode()
    with pytest.raises(SamlValidationError):
        parse_saml_response(
            tampered,
            sp_entity_id=SP_ENTITY,
            acs_url=ACS_URL,
            idp_entity_id=IDP_ENTITY,
            certificate=idp.cert_b64,
        )


def test_parse_rejects_wrong_audience(idp):
    response = _build_response(idp, audience="https://evil.example.com")
    with pytest.raises(SamlValidationError):
        parse_saml_response(
            response,
            sp_entity_id=SP_ENTITY,
            acs_url=ACS_URL,
            idp_entity_id=IDP_ENTITY,
            certificate=idp.cert_b64,
        )


def test_parse_rejects_wrong_recipient(idp):
    response = _build_response(idp, recipient="https://evil.example.com/acs")
    with pytest.raises(SamlValidationError):
        parse_saml_response(
            response,
            sp_entity_id=SP_ENTITY,
            acs_url=ACS_URL,
            idp_entity_id=IDP_ENTITY,
            certificate=idp.cert_b64,
        )


def test_parse_rejects_wrong_issuer(idp):
    response = _build_response(idp, issuer="https://evil.example.com/metadata")
    with pytest.raises(SamlValidationError):
        parse_saml_response(
            response,
            sp_entity_id=SP_ENTITY,
            acs_url=ACS_URL,
            idp_entity_id=IDP_ENTITY,
            certificate=idp.cert_b64,
        )


def test_parse_rejects_error_status(idp):
    response = _build_response(idp, status="urn:oasis:names:tc:SAML:2.0:status:AuthnFailed")
    with pytest.raises(SamlValidationError):
        parse_saml_response(
            response,
            sp_entity_id=SP_ENTITY,
            acs_url=ACS_URL,
            idp_entity_id=IDP_ENTITY,
            certificate=idp.cert_b64,
        )


def test_parse_rejects_expired_assertion(idp):
    response = _build_response(idp, valid=False)
    with pytest.raises(SamlValidationError):
        parse_saml_response(
            response,
            sp_entity_id=SP_ENTITY,
            acs_url=ACS_URL,
            idp_entity_id=IDP_ENTITY,
            certificate=idp.cert_b64,
        )


def test_parse_rejects_unsigned_response(idp):
    assertion_xml = f'''<saml:Assertion xmlns:saml="{SAML_NS}" ID="_a123" IssueInstant="2024-01-01T00:00:00Z" Version="2.0">
  <saml:Issuer>{IDP_ENTITY}</saml:Issuer>
  <saml:Subject><saml:NameID>jane@example.com</saml:NameID></saml:Subject>
</saml:Assertion>'''
    response_xml = f'''<samlp:Response xmlns:samlp="{SAMLP_NS}" xmlns:saml="{SAML_NS}" ID="_resp1" Version="2.0" IssueInstant="2024-01-01T00:00:00Z">
  <saml:Issuer>{IDP_ENTITY}</saml:Issuer>
  <samlp:Status><samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/></samlp:Status>
  {assertion_xml}
</samlp:Response>'''
    response = base64.b64encode(response_xml.encode()).decode()
    with pytest.raises(SamlValidationError):
        parse_saml_response(
            response,
            sp_entity_id=SP_ENTITY,
            acs_url=ACS_URL,
            idp_entity_id=IDP_ENTITY,
            certificate=idp.cert_b64,
        )


def test_parse_rejects_garbage():
    with pytest.raises(SamlValidationError):
        parse_saml_response(
            "not-base64-!!",
            sp_entity_id=SP_ENTITY,
            acs_url=ACS_URL,
            idp_entity_id=IDP_ENTITY,
            certificate="AAAABBBB",
        )


def test_parse_cert_pem_and_bare(idp):
    assert (
        parse_saml_response(
            _build_response(idp),
            sp_entity_id=SP_ENTITY,
            acs_url=ACS_URL,
            idp_entity_id=IDP_ENTITY,
            certificate=idp.cert_pem,
        ).email
        == "jane@example.com"
    )
