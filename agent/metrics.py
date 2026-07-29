from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, func

from agent.db import async_session_factory
from agent.models import POStatus, PurchaseOrder


async def calculate_acceptance_rate(
    merchant_id: int = 0,
    since: date | None = None,
) -> dict:
    if since is None:
        since = date.today() - timedelta(days=30)

    async with async_session_factory() as session:
        result = await session.execute(
            select(PurchaseOrder).where(
                PurchaseOrder.created_at >= since,
                PurchaseOrder.status.in_([POStatus.approved, POStatus.rejected]),
            )
        )
        pos = result.scalars().all()

    total = len(pos)
    if total == 0:
        return {"total": 0, "accepted_as_is": 0, "accepted_as_is_pct": 0,
                "edited_then_approved": 0, "edited_then_approved_pct": 0,
                "rejected": 0, "rejected_pct": 0}

    accepted = [p for p in pos if p.status == POStatus.approved]
    rejected = [p for p in pos if p.status == POStatus.rejected]

    as_is = [p for p in accepted if not p.edited_before_approval]
    edited = [p for p in accepted if p.edited_before_approval]

    return {
        "total": total,
        "accepted_as_is": len(as_is),
        "accepted_as_is_pct": round(len(as_is) / total * 100, 1),
        "edited_then_approved": len(edited),
        "edited_then_approved_pct": round(len(edited) / total * 100, 1),
        "rejected": len(rejected),
        "rejected_pct": round(len(rejected) / total * 100, 1),
    }


async def calculate_forecast_error_summary(since: date | None = None) -> dict | None:
    from agent.models import POOutcome

    if since is None:
        since = date.today() - timedelta(days=90)

    async with async_session_factory() as session:
        result = await session.execute(
            select(POOutcome).where(POOutcome.evaluated_at >= since)
        )
        outcomes = result.scalars().all()

    if not outcomes:
        return None

    errors = [o.forecast_error_pct for o in outcomes if o.forecast_error_pct is not None]
    if not errors:
        return None

    return {
        "count": len(errors),
        "mean_error_pct": round(sum(errors) / len(errors), 1),
        "min_error_pct": round(min(errors), 1),
        "max_error_pct": round(max(errors), 1),
        "stockout_rate": round(sum(1 for o in outcomes if o.actual_stockout_occurred) / len(outcomes) * 100, 1),
    }
