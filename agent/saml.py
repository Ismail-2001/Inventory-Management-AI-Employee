"""SAML 2.0 SP support — SP metadata, AuthnRequest generation, SAMLResponse verification.

Implemented directly on top of lxml + xmlsec (the modern pure-pip crypto
binding) rather than pysaml2, because pysaml2's XMLSecurity crypto backend
targets the removed legacy ``xmlsec.parse_xml/sign/verify`` API and otherwise
requires a native ``xmlsec1`` binary, which is not reliably available on all
deployment targets (notably Windows).

Functions:
    build_sp_metadata(provider)      -> str  (XML)
    build_authn_request_url(provider)-> str  (HTTP-Redirect redirect URL)
    parse_saml_response(response, provider) -> dict  (verified attributes)
"""

from __future__ import annotations

import base64
import logging
import secrets
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlencode

import xmlsec
from lxml import etree

logger = logging.getLogger(__name__)

SAML_NS = "urn:oasis:names:tc:SAML:2.0:assertion"
SAMLP_NS = "urn:oasis:names:tc:SAML:2.0:protocol"
METADATA_NS = "urn:oasis:names:tc:SAML:2.0:metadata"
XMLDSIG_NS = "http://www.w3.org/2000/09/xmldsig#"

NAMEID_EMAIL = "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
NAMEID_PERSISTENT = "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
NAMEID_TRANSIENT = "urn:oasis:names:tc:SAML:2.0:nameid-format:transient"

BINDING_REDIRECT = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
BINDING_POST = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"

_NSMAP = {
    "saml": SAML_NS,
    "samlp": SAMLP_NS,
    "md": METADATA_NS,
    "ds": XMLDSIG_NS,
}


@dataclass
class SamlResult:
    name_id: str
    email: str
    attributes: dict[str, str]
    session_index: str | None = None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_cert(cert: str) -> str:
    """Return the base64 cert body from PEM or bare base64 input."""
    cert = cert.strip()
    if "BEGIN CERTIFICATE" in cert:
        return "".join(line for line in cert.splitlines() if line and "CERTIFICATE" not in line).strip()
    return cert.replace("\n", "").replace(" ", "").strip()


def build_sp_metadata(entity_id: str, acs_url: str, slo_url: str = "", name_id_format: str = NAMEID_EMAIL) -> str:
    """Build the SP EntityDescriptor metadata document."""
    name_id_line = f"    <md:NameIDFormat>{name_id_format}</md:NameIDFormat>\n" if name_id_format else ""
    slo_line = f'    <md:SingleLogoutService Binding="{BINDING_REDIRECT}" Location="{slo_url}"/>\n' if slo_url else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<md:EntityDescriptor xmlns:md="{METADATA_NS}" entityID="{entity_id}">
  <md:SPSSODescriptor protocolSupportEnumeration="{SAMLP_NS}" AuthnRequestsSigned="false" WantAssertionsSigned="true">
{name_id_line}{slo_line}    <md:AssertionConsumerService Binding="{BINDING_POST}" Location="{acs_url}" index="0" isDefault="true"/>
  </md:SPSSODescriptor>
</md:EntityDescriptor>
"""


def build_authn_request_url(
    entity_id: str,
    sso_url: str,
    acs_url: str,
    relay_state: str = "",
    name_id_format: str = NAMEID_EMAIL,
) -> str:
    """Build an AuthnRequest and return the HTTP-Redirect URL to the IdP."""
    req_id = f"_{secrets.token_urlsafe(24)}"
    issue_instant = _now_iso()
    nameid_policy = f'<samlp:NameIDPolicy Format="{name_id_format}" AllowCreate="true"/>' if name_id_format else ""
    request_xml = f"""<samlp:AuthnRequest xmlns:samlp="{SAMLP_NS}" xmlns:saml="{SAML_NS}"
    ID="{req_id}" Version="2.0" IssueInstant="{issue_instant}"
    Destination="{sso_url}" AssertionConsumerServiceURL="{acs_url}"
    ProtocolBinding="{BINDING_POST}">
  <saml:Issuer>{entity_id}</saml:Issuer>
  {nameid_policy}
</samlp:AuthnRequest>
"""
    # HTTP-Redirect binding: DEFLATE -> base64 -> URL-encode
    compressed = zlib.compress(request_xml.encode("utf-8"))[2:-4]  # strip zlib header/trailer
    saml_request = base64.b64encode(compressed).decode("ascii")
    params = {"SAMLRequest": saml_request}
    if relay_state:
        params["RelayState"] = relay_state
    sep = "&" if "?" in sso_url else "?"
    return f"{sso_url}{sep}{urlencode(params)}"


class SamlError(Exception):
    pass


class SamlValidationError(SamlError):
    pass


def _verify_signature(root: etree._Element, cert_b64: str) -> None:
    """Verify the XMLDSig signature embedded in the document."""
    sig_el = root.find(f".//{{{XMLDSIG_NS}}}Signature")
    if sig_el is None:
        raise SamlValidationError("SAMLResponse is not signed")

    cert_pem = _pem_wrap(cert_b64)
    key = xmlsec.Key.from_memory(cert_pem.encode("utf-8"), xmlsec.KeyFormat.CERT_PEM)  # type: ignore[attr-defined]
    ctx = xmlsec.SignatureContext()
    ctx.key = key
    xmlsec.tree.add_ids(root, ["ID", "Id", "id"])
    try:
        ctx.verify(sig_el)
    except Exception as exc:
        raise SamlValidationError(f"SAML signature verification failed: {exc}") from exc


def _pem_wrap(cert_b64: str) -> str:
    body = _parse_cert(cert_b64)
    lines = [body[i : i + 64] for i in range(0, len(body), 64)]
    return "-----BEGIN CERTIFICATE-----\n" + "\n".join(lines) + "\n-----END CERTIFICATE-----\n"


def _check_conditions(assertion: etree._Element, expected_audience: str, acs_url: str) -> None:
    now = datetime.now(UTC)
    ns = {"saml": SAML_NS}

    cond = assertion.find("saml:Conditions", ns)
    if cond is None:
        raise SamlValidationError("Assertion has no Conditions")
    for attr, op in (("NotOnOrAfter", "lt"), ("NotBefore", "gt")):
        raw = cond.get(attr)
        if raw:
            try:
                when = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                raise SamlValidationError(f"Invalid {attr} in Conditions") from None
            if op == "lt" and now >= when:
                raise SamlValidationError(f"Assertion expired ({attr}={raw})")
            if op == "gt" and now <= when:
                raise SamlValidationError(f"Assertion not yet valid ({attr}={raw})")

    audience = cond.find("saml:AudienceRestriction/saml:Audience", ns)
    if audience is not None and audience.text and audience.text != expected_audience:
        raise SamlValidationError(f"Audience mismatch: expected {expected_audience}, got {audience.text}")

    conf = assertion.find("saml:Subject/saml:SubjectConfirmation/saml:SubjectConfirmationData", ns)
    if conf is not None:
        recipient = conf.get("Recipient")
        if recipient and acs_url and recipient != acs_url:
            raise SamlValidationError(f"Recipient mismatch: expected {acs_url}, got {recipient}")


def _extract_attributes(assertion: etree._Element) -> dict[str, str]:
    ns = {"saml": SAML_NS}
    attrs: dict[str, str] = {}
    for attr_el in assertion.findall(".//saml:Attribute", ns):
        name = attr_el.get("Name") or attr_el.get("FriendlyName") or ""
        vals = [v.text or "" for v in attr_el.findall("saml:AttributeValue", ns)]
        if name and vals:
            attrs[name] = vals[0] if len(vals) == 1 else ",".join(vals)
    return attrs


def parse_saml_response(
    saml_response: str,
    *,
    sp_entity_id: str,
    acs_url: str,
    idp_entity_id: str,
    certificate: str,
) -> SamlResult:
    """Decode, verify, and extract identity from a SAMLResponse.

    ``saml_response`` is the raw base64-encoded POST binding payload.
    """
    if not saml_response:
        raise SamlValidationError("Empty SAMLResponse")

    try:
        decoded = base64.b64decode(saml_response, validate=False)
        root = etree.fromstring(decoded, parser=etree.XMLParser(resolve_entities=False))
    except Exception as exc:
        raise SamlValidationError(f"Could not decode SAMLResponse: {exc}") from exc

    if root.tag != f"{{{SAMLP_NS}}}Response":
        raise SamlValidationError("Not a SAML Response document")

    # Status check
    status_code = root.find(f".//{{{SAMLP_NS}}}Status/{{{SAMLP_NS}}}StatusCode")
    if status_code is not None and status_code.get("Value") != "urn:oasis:names:tc:SAML:2.0:status:Success":
        raise SamlValidationError(f"SAML status not Success: {status_code.get('Value')}")

    assertion = root.find(f".//{{{SAML_NS}}}Assertion")
    if assertion is None:
        raise SamlValidationError("SAMLResponse contains no Assertion")

    issuer = root.find(f".//{{{SAML_NS}}}Issuer")
    if issuer is not None and issuer.text and idp_entity_id and issuer.text != idp_entity_id:
        raise SamlValidationError(f"Unexpected issuer: {issuer.text}")

    cert_b64 = _parse_cert(certificate)
    _verify_signature(root, cert_b64)
    _check_conditions(assertion, sp_entity_id, acs_url)

    ns = {"saml": SAML_NS}
    name_id_el = assertion.find("saml:Subject/saml:NameID", ns)
    name_id = name_id_el.text if name_id_el is not None and name_id_el.text else ""
    if not name_id:
        raise SamlValidationError("Assertion has no NameID")

    attrs = _extract_attributes(assertion)
    email = attrs.get("email") or attrs.get("EmailAddress") or attrs.get("mail") or name_id
    if "@" not in email:
        raise SamlValidationError(f"No email address in SAML assertion: {email}")

    session_index = None
    authn = assertion.find("saml:AuthnStatement", ns)
    if authn is not None:
        session_index = authn.get("SessionIndex")

    return SamlResult(name_id=name_id, email=email, attributes=attrs, session_index=session_index)
