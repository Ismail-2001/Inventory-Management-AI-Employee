import httpx

from agent.config import settings
from agent.signing import sign_token
from agent.telemetry import trace_node


def _make_domain() -> str:
    return settings.shopify_store_domain or "localhost:8002"


@trace_node("notify")
async def notify_node(state: dict) -> dict:
    alerts = state.get("risk_alerts", [])
    pos = state.get("purchase_orders", [])

    if not alerts and not pos:
        return {}

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

    summary = "\n".join(summary_lines)

    if settings.slack_webhook_url:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(settings.slack_webhook_url, json={"text": summary})

    return {"notification_summary": summary}
