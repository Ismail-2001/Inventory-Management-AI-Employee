"""Usage metrics and dashboard endpoints for monitoring and monetization."""
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.orm import aliased

from agent.auth import verify_api_key
from agent.db import async_session_factory, async_session_factory_readonly
from agent.models import (
    Forecast,
    LlmUsage,
    POStatus,
    PurchaseOrder,
    RiskAlert,
    Sku,
    AuditLog,
)

router = APIRouter()


def _session():
    factory = async_session_factory_readonly or async_session_factory
    return factory()


@router.get("/api/v1/usage/summary")
async def usage_summary(merchant=Depends(verify_api_key)):
    """Aggregate usage metrics for the current merchant."""
    today = date.today()
    week_ago = today - timedelta(days=7)
    merchant_filter = merchant.id if merchant.id else None

    async with _session() as session:
        po_q = select(func.count(PurchaseOrder.id)).where(PurchaseOrder.created_at >= week_ago)
        pending_q = select(func.count(PurchaseOrder.id)).where(
            PurchaseOrder.status == POStatus.pending_approval, PurchaseOrder.created_at >= week_ago,
        )
        approved_q = select(func.count(PurchaseOrder.id)).where(
            PurchaseOrder.status == POStatus.approved, PurchaseOrder.created_at >= week_ago,
        )
        if merchant_filter:
            po_q = po_q.where(PurchaseOrder.merchant_id == merchant_filter)
            pending_q = pending_q.where(PurchaseOrder.merchant_id == merchant_filter)
            approved_q = approved_q.where(PurchaseOrder.merchant_id == merchant_filter)

        po_count = (await session.execute(po_q)).scalar() or 0
        pending_pos = (await session.execute(pending_q)).scalar() or 0
        approved_pos = (await session.execute(approved_q)).scalar() or 0

        alert_q = (
            select(func.count(RiskAlert.id))
            .join(Sku, RiskAlert.sku_id == Sku.id)
            .where(RiskAlert.created_at >= week_ago)
        )
        if merchant_filter:
            alert_q = alert_q.where(Sku.merchant_id == merchant_filter)
        alert_count = (await session.execute(alert_q)).scalar() or 0

        forecast_q = (
            select(func.count(Forecast.id))
            .join(Sku, Forecast.sku_id == Sku.id)
            .where(Forecast.created_at >= week_ago)
        )
        if merchant_filter:
            forecast_q = forecast_q.where(Sku.merchant_id == merchant_filter)
        forecast_count = (await session.execute(forecast_q)).scalar() or 0

        llm_cost = (
            await session.execute(
                select(func.coalesce(func.sum(LlmUsage.estimated_cost), 0.0)).where(
                    LlmUsage.created_at >= week_ago
                )
            )
        ).scalar() or 0.0

    return {
        "period": "7d",
        "purchase_orders": {"total": po_count, "pending": pending_pos, "approved": approved_pos},
        "risk_alerts": alert_count,
        "forecasts": forecast_count,
        "llm_cost_usd": round(float(llm_cost), 4),
    }


@router.get("/api/v1/usage/daily")
async def usage_daily(days: int = 14, merchant=Depends(verify_api_key)):
    """Time-series of daily usage for charting."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    merchant_filter = merchant.id if merchant.id else None

    async with _session() as session:
        po_q = (
            select(
                func.date(PurchaseOrder.created_at).label("day"),
                func.count(PurchaseOrder.id).label("count"),
            ).where(PurchaseOrder.created_at >= cutoff)
            .group_by(func.date(PurchaseOrder.created_at))
            .order_by(func.date(PurchaseOrder.created_at))
        )
        if merchant_filter:
            po_q = po_q.where(PurchaseOrder.merchant_id == merchant_filter)
        po_data = (await session.execute(po_q)).all()

        alert_q = (
            select(
                func.date(RiskAlert.created_at).label("day"),
                func.count(RiskAlert.id).label("count"),
            )
            .join(Sku, RiskAlert.sku_id == Sku.id)
            .where(RiskAlert.created_at >= cutoff)
            .group_by(func.date(RiskAlert.created_at))
            .order_by(func.date(RiskAlert.created_at))
        )
        if merchant_filter:
            alert_q = alert_q.where(Sku.merchant_id == merchant_filter)
        alert_data = (await session.execute(alert_q)).all()

        llm_data = (
            await session.execute(
                select(
                    func.date(LlmUsage.created_at).label("day"),
                    func.coalesce(func.sum(LlmUsage.estimated_cost), 0.0).label("cost"),
                ).where(
                    LlmUsage.created_at >= cutoff,
                ).group_by(func.date(LlmUsage.created_at))
                .order_by(func.date(LlmUsage.created_at))
            )
        ).all()

    return {
        "purchase_orders": [{"date": str(r.day), "count": r.count} for r in po_data],
        "risk_alerts": [{"date": str(r.day), "count": r.count} for r in alert_data],
        "llm_cost": [{"date": str(r.day), "cost": round(float(r.cost), 4)} for r in llm_data],
    }
