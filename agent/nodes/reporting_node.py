from datetime import date, datetime, timedelta, timezone
import asyncio
import logging

import httpx
from sqlalchemy import select, func

from agent.audit import log
from agent.config import settings
from agent.db import async_session_factory
from agent.models import POStatus, PurchaseOrder, RiskAlert

logger = logging.getLogger(__name__)

_SLACK_MAX_RETRIES = 3
_SLACK_RETRY_DELAY = 2.0


async def _send_slack(text: str) -> bool:
    for attempt in range(_SLACK_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(settings.slack_webhook_url, json={"text": text})
                resp.raise_for_status()
                return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                retry_after = float(e.response.headers.get("Retry-After", _SLACK_RETRY_DELAY * (attempt + 1)))
                logger.warning("Slack rate limited, retrying in %.1fs", retry_after)
                await asyncio.sleep(retry_after)
            else:
                logger.warning("Slack HTTP %d on attempt %d: %s", e.response.status_code, attempt + 1, e)
                return False
        except Exception as e:
            logger.warning("Slack request failed on attempt %d: %s", attempt + 1, e)
            if attempt < _SLACK_MAX_RETRIES - 1:
                await asyncio.sleep(_SLACK_RETRY_DELAY * (attempt + 1))
    return False


async def run_reporting(week_start: date, insights: list[dict]) -> str:
    week_end = week_start + timedelta(days=7)

    async with async_session_factory() as session:
        alert_count = (
            await session.execute(
                select(func.count(RiskAlert.id)).where(
                    RiskAlert.created_at >= week_start,
                    RiskAlert.created_at < week_end,
                )
            )
        ).scalar() or 0

        critical_count = (
            await session.execute(
                select(func.count(RiskAlert.id)).where(
                    RiskAlert.created_at >= week_start,
                    RiskAlert.created_at < week_end,
                    RiskAlert.risk_level == "critical",
                )
            )
        ).scalar() or 0

        po_count = (
            await session.execute(
                select(func.count(PurchaseOrder.id)).where(
                    PurchaseOrder.created_at >= week_start,
                    PurchaseOrder.created_at < week_end,
                )
            )
        ).scalar() or 0

        pending_count = (
            await session.execute(
                select(func.count(PurchaseOrder.id)).where(
                    PurchaseOrder.status == POStatus.pending_approval
                )
            )
        ).scalar() or 0

    lines = [
        f"Weekly Inventory Digest ({week_start.isoformat()} to {week_end.isoformat()})",
        f"{'=' * 50}",
        f"",
        f"Summary:",
        f"  Risk alerts this week: {alert_count} ({critical_count} critical)",
        f"  POs drafted:          {po_count}",
        f"  POs pending approval: {pending_count}",
        f"",
    ]

    if insights:
        lines.append("Reflection Insights:")
        for ins in insights:
            lines.append(f"  {ins['insight_text']}")
            lines.append("")

    lines.append("Action Items:")
    if pending_count:
        lines.append(f"  - {pending_count} PO(s) waiting for your approval")
    else:
        lines.append("  - No pending approvals — you're caught up!")
    lines.append("  - Review weekly insights above and adjust thresholds if needed.")

    digest = "\n".join(lines)

    if settings.slack_webhook_url:
        await _send_slack(digest)

    await log(action="weekly_digest_sent", details={
        "week_start": week_start.isoformat(),
        "alert_count": alert_count,
        "po_count": po_count,
    })

    return digest
