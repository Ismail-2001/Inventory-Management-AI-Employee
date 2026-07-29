import time
import pytest
from agent.signing import sign_token, verify_token


def test_sign_and_verify():
    token = sign_token(1, "approve", ttl_seconds=3600)
    payload = verify_token(token)
    assert payload is not None
    assert payload["po_id"] == 1
    assert payload["action"] == "approve"


def test_expired_token():
    token = sign_token(1, "approve", ttl_seconds=-1)
    payload = verify_token(token)
    assert payload is None


def test_tampered_token():
    token = sign_token(1, "approve", ttl_seconds=3600)
    tampered = token[:-5] + "XXXXX"
    payload = verify_token(tampered)
    assert payload is None


def test_invalid_format():
    assert verify_token("not-a-valid-token") is None
    assert verify_token("") is None


def test_different_secret():
    token = sign_token(1, "reject", ttl_seconds=3600)
    payload = verify_token(token)
    assert payload is not None
    assert payload["action"] == "reject"
