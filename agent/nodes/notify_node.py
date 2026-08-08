import logging
from typing import Any

from agent.config import settings
from agent.signing import sign_token
from agent.telemetry import trace_node
from shared.slack import send_slack

logger = logging.getLogger(__name__)


def _make_domain() -> str:
    return settings.public_api_url.rstrip("/") if settings.public_api_url else "http://localhost:8002"


def _build_pending_summary(state: dict[str, Any]) -> str:
    alerts = state.get("risk_alerts", [])
    pos = state.get("purchase_orders", [])

    if not alerts and not pos:
        return ""

    critical = [a for a in alerts if a["risk_level"] == "critical"]
    warning = [a for a in alerts if a["risk_level"] == "warning"]
    domain = _make_domain()

    summary_lines = [
        "Inventory Risk & PO Report",
        f"  Critical alerts: {len(critical)}",
        f"  Warning alerts:  {len(warning)}",
        f"  POs pending approval: {len(pos)}",
        "",
    ]

    for a in alerts[:5]:
        summary_lines.append(f"  - [{a['risk_level']}] SKU #{a['sku_id']}: {a['reason']}")
    if len(alerts) > 5:
        summary_lines.append(f"  ... and {len(alerts) - 5} more")

    if pos:
        summary_lines.extend(["", "Pending Purchase Orders:"])
        for po in pos[:3]:
            approve_token = sign_token(po["po_id"], "approve")
            reject_token = sign_token(po["po_id"], "reject")
            summary_lines.append(
                f"  PO #{po['po_id']}: {po['quantity']} units, ${po['total_cost']:.2f}"
            )
            summary_lines.append(f"    Approve: {domain}/api/v1/po/action?token={approve_token}")
            summary_lines.append(f"    Reject:  {domain}/api/v1/po/action?token={reject_token}&reason=")

    return "\n".join(summary_lines)


def _build_confirmed_summary(state: dict[str, Any]) -> str:
    pos = state.get("purchase_orders", [])
    if not pos:
        return ""

    latest_po = pos[-1]
    status = state.get("approval_status") or "updated"
    actor = state.get("approved_by") or "the team"
    if status == "approved":
        return f"PO #{latest_po['po_id']} approved by {actor}"
    if status == "rejected":
        return f"PO #{latest_po['po_id']} rejected: {state.get('rejected_reason', 'no reason provided')}"
    return f"PO #{latest_po['po_id']} {status}"


@trace_node("notify_pending")
async def notify_pending_node(state: dict[str, Any]) -> dict[str, Any]:
    summary = _build_pending_summary(state)
    if not summary:
        return {**state, "notification_summary": ""}

    if settings.slack_webhook_url:
        try:
            await send_slack(settings.slack_webhook_url, summary)
        except Exception:
            pass

    return {**state, "notification_summary": summary}


@trace_node("notify_confirmed")
async def notify_confirmed_node(state: dict[str, Any]) -> dict[str, Any]:
    summary = _build_confirmed_summary(state)
    if not summary:
        return {**state}

    if settings.slack_webhook_url:
        try:
            await send_slack(settings.slack_webhook_url, summary)
        except Exception:
            pass

    return {**state, "confirmation_summary": summary}


async def notify_node(state: dict[str, Any]) -> dict[str, Any]:
    return await notify_pending_node(state)
