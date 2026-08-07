"""Nightly export of AuditLog entries to S3-compatible storage.

Uses httpx — no boto3 dependency. Works with AWS S3, MinIO, DigitalOcean Spaces, etc.
S3 API via REST: https://docs.aws.amazon.com/AmazonS3/latest/API/sigv4-query-string-auth.html
"""
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select

from agent.config import settings
from agent.db import async_session_factory
from agent.models import AuditLog


def _s3_sign(method: str, path: str, headers: dict, body: bytes, region: str, bucket: str, access_key: str, secret_key: str) -> tuple[str, dict]:
    """Minimal AWS Signature V4 signing for S3 PUT."""
    service = "s3"
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    headers["x-amz-date"] = amz_date
    headers["host"] = f"{bucket}.s3.{region}.amazonaws.com"

    canonical_headers = "".join(f"{k.lower()}:{v.strip()}\n" for k, v in sorted(headers.items()))
    signed_headers = ";".join(sorted(k.lower() for k in headers))

    payload_hash = hashlib.sha256(body).hexdigest()
    canonical_request = f"{method}\n{path}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"

    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = f"AWS4-HMAC-SHA256\n{amz_date}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode()).hexdigest()}"

    def _sign(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    k_date = _sign(f"AWS4{secret_key}".encode(), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    k_signing = _sign(k_service, "aws4_request")
    signature = hmac.new(k_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()

    headers["Authorization"] = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return amz_date, headers


async def export_audit_logs_to_s3() -> int:
    """Export all AuditLog entries from the last 24h to S3 and return count."""
    if not settings.audit_s3_bucket or not settings.audit_s3_access_key:
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    async with async_session_factory() as session:
        result = await session.execute(
            select(AuditLog).where(AuditLog.created_at >= cutoff)
        )
        entries = result.scalars().all()

    if not entries:
        return 0

    lines = "\n".join(
        json.dumps(
            {
                "id": e.id,
                "merchant_id": e.merchant_id,
                "actor_type": e.actor_type,
                "actor_id": e.actor_id,
                "action": e.action,
                "target_type": e.target_type,
                "target_id": e.target_id,
                "details": e.details,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            },
            default=str,
        )
        for e in entries
    )
    body = lines.encode()

    date_prefix = cutoff.strftime("%Y/%m/%d")
    key = f"audit/{date_prefix}/{cutoff.strftime('%H%M%S')}-{len(entries)}-entries.jsonl"

    region = settings.audit_s3_region
    bucket = settings.audit_s3_bucket
    path = f"/{key}"
    url = f"https://{bucket}.s3.{region}.amazonaws.com{path}"
    headers = {"Content-Type": "application/jsonl"}

    amz_date, signed_headers = _s3_sign(
        "PUT", path, headers, body,
        region, bucket, settings.audit_s3_access_key, settings.audit_s3_secret_key,
    )

    async with httpx.AsyncClient() as client:
        resp = await client.put(url, content=body, headers=signed_headers)
        resp.raise_for_status()

    return len(entries)
