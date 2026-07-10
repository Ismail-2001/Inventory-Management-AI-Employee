from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, func

from agent.db import async_session_factory
from agent.models import POOutcome, PurchaseOrder, SalesHistory, Sku


async def evaluate_pending_outcomes():
    evaluated = 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=1)

    async with async_session_factory() as session:
        result = await session.execute(
            select(PurchaseOrder).where(
                PurchaseOrder.status == "approved",
                PurchaseOrder.approved_at.isnot(None),
                PurchaseOrder.approved_at < cutoff,
            )
        )
        pos = result.scalars().all()

    for po in pos:
        async with async_session_factory() as session:
            existing = await session.execute(
                select(POOutcome).where(POOutcome.po_id == po.id)
            )
            if existing.scalar_one_or_none():
                continue

            sku = await session.get(Sku, po.sku_id)
            if not sku:
                continue

            expected_delivery = po.approved_at + timedelta(days=7)
            if expected_delivery > datetime.now(timezone.utc):
                continue

            delivery_date = expected_delivery.date()
            two_weeks_before = delivery_date - timedelta(days=14)
            two_weeks_after = delivery_date + timedelta(days=14)

            sales_before = await session.execute(
                select(func.sum(SalesHistory.units_sold))
                .where(
                    SalesHistory.sku_id == po.sku_id,
                    SalesHistory.date >= two_weeks_before,
                    SalesHistory.date < delivery_date,
                )
            )
            demand_before = sales_before.scalar() or 0

            sales_after = await session.execute(
                select(func.sum(SalesHistory.units_sold))
                .where(
                    SalesHistory.sku_id == po.sku_id,
                    SalesHistory.date >= delivery_date,
                    SalesHistory.date <= two_weeks_after,
                )
            )
            demand_after = sales_after.scalar() or 0

            actual_daily_demand = demand_after / 14 if demand_after > 0 else 0
            stockout = sku.current_stock <= 0

            forecast_row = await session.execute(
                select(func.avg(SalesHistory.units_sold))
                .where(
                    SalesHistory.sku_id == po.sku_id,
                    SalesHistory.date >= two_weeks_before,
                    SalesHistory.date < delivery_date,
                )
            )
            forecast_avg = forecast_row.scalar() or 1
            error_pct = abs(forecast_avg - actual_daily_demand) / max(forecast_avg, 0.1) * 100 if forecast_avg > 0 else 0

            outcome = POOutcome(
                po_id=po.id,
                expected_stockout_prevented=demand_before > sku.current_stock,
                actual_stock_at_delivery=sku.current_stock,
                actual_stockout_occurred=stockout,
                forecast_error_pct=round(error_pct, 1),
                evaluated_at=datetime.now(timezone.utc),
            )
            session.add(outcome)
            await session.commit()
            evaluated += 1

    return evaluated
