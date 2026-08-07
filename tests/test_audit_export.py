import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock

from agent import audit_export as export_module


def test_s3_sign_returns_amz_date_and_headers():
    now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    with patch("agent.audit_export.datetime") as mock_dt:
        mock_dt.now.return_value = now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        amz_date, headers = export_module._s3_sign(
            method="PUT",
            path="/audit/2026/01/15/test.jsonl",
            headers={"Content-Type": "application/jsonl"},
            body=b'{"test": true}',
            region="us-east-1",
            bucket="my-bucket",
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        )

    assert amz_date == "20260115T120000Z"
    assert "Authorization" in headers
    assert "AWS4-HMAC-SHA256" in headers["Authorization"]
    assert "x-amz-date" in headers
    assert headers["host"] == "my-bucket.s3.us-east-1.amazonaws.com"


def test_s3_sign_deterministic():
    now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    with patch("agent.audit_export.datetime") as mock_dt:
        mock_dt.now.return_value = now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        _, h1 = export_module._s3_sign("PUT", "/k", {"Content-Type": "text/plain"}, b"body", "us-east-1", "b", "ak", "sk")
        _, h2 = export_module._s3_sign("PUT", "/k", {"Content-Type": "text/plain"}, b"body", "us-east-1", "b", "ak", "sk")

    assert h1["Authorization"] == h2["Authorization"]


@pytest.mark.asyncio
async def test_export_returns_0_when_no_s3_config(monkeypatch):
    monkeypatch.setattr(export_module.settings, "audit_s3_bucket", "")
    monkeypatch.setattr(export_module.settings, "audit_s3_access_key", "")

    result = await export_module.export_audit_logs_to_s3()
    assert result == 0


@pytest.mark.asyncio
async def test_export_returns_0_when_no_entries(monkeypatch):
    monkeypatch.setattr(export_module.settings, "audit_s3_bucket", "my-bucket")
    monkeypatch.setattr(export_module.settings, "audit_s3_access_key", "AKIAIOSFODNN7EXAMPLE")

    class FakeResult:
        def scalars(self):
            return self
        def all(self):
            return []

    class FakeSession:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def execute(self, q):
            return FakeResult()

    class FakeFactory:
        def __call__(self):
            return FakeSession()

    monkeypatch.setattr(export_module, "async_session_factory", FakeFactory())

    result = await export_module.export_audit_logs_to_s3()
    assert result == 0
