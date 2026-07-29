from agent.db import async_session_factory
from agent.models import RiskAlert
from agent.risk import determine_risk_level
from agent.telemetry import trace_node


@trace_node("risk")
async def risk_node(state: dict) -> dict:
    forecasts = state.get("forecasts", [])
    skus_map = {s["id"]: s for s in state.get("skus", [])}

    alerts = []
    for f in forecasts:
        sku = skus_map.get(f["sku_id"])
        lead_time = sku.get("lead_time_days", 7) if sku else 7

        level, reason = determine_risk_level(
            f.get("days_of_stock_remaining"),
            lead_time,
        )

        if level in ("critical", "warning"):
            async with async_session_factory() as session:
                alert = RiskAlert(
                    sku_id=f["sku_id"],
                    risk_level=level,
                    reason=reason,
                )
                session.add(alert)
                await session.commit()
                alerts.append({
                    "sku_id": f["sku_id"],
                    "risk_level": level,
                    "reason": reason,
                    "alert_id": alert.id,
                })

    return {**state, "risk_alerts": alerts}
