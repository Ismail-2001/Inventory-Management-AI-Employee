"""ROI & performance dashboard aggregations.

Every figure is derived from persisted data with an explicit, documented
formula (docs/ROI-DASHBOARD.md):

- stockouts avoided   po_outcomes.expected_stockout_prevented without an
                      actual stockout, valued at PO cost x ROI_REVENUE_MULTIPLIER
- excess reduction    quantities trimmed before approval + rejected POs,
                      valued at cost
- forecast accuracy   forecasts.backtest_wmape/backtest_bias: ensemble_v2
                      rows vs exp_smoothing_v1 (baseline) rows, plus an
                      independent po_outcomes forecast_error_pct view
- PO decisions        purchase_orders + audit_log (po.approve / po.reject)
                      for acceptance and time-to-decision
- hours saved         decided POs x ROI_MANUAL_PO_MINUTES / 60
- LLM cost            llm_usage.estimated_cost + chat_messages.cost_usd
- at-risk SKUs        unresolved critical/warning risk_alerts (current)
- forecast coverage   share of forecast rows carrying p10/p90 intervals;
                      fallback rate from forecasts.model_meta.fallback_used
"""

from datetime import UTC, date, datetime, time, timedelta
from statistics import fmean
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent.config import settings
from agent.db import async_session_factory as _default_factory
from agent.models import (
    AuditLog,
    ChatMessage,
    Forecast,
    LlmUsage,
    POOutcome,
    POStatus,
    PurchaseOrder,
    RiskAlert,
    Sku,
)

SessionFactory = async_sessionmaker[AsyncSession]

_DECISION_ACTIONS = ("po.approve", "po.reject")
_CONFIDENCE_BUCKETS = ("tight", "typical", "wide")
_MAX_SERIES_POINTS = 60


def _window_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    """Inclusive start / exclusive end as UTC datetimes."""
    since = datetime.combine(start, time.min, tzinfo=UTC)
    until = datetime.combine(end + timedelta(days=1), time.min, tzinfo=UTC)
    return since, until


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


async def calculate_stockouts_avoided(
    merchant_id: int = 0,
    since: datetime | None = None,
    until: datetime | None = None,
    revenue_multiplier: float | None = None,
    session_factory: SessionFactory | None = None,
) -> dict[str, Any]:
    """Units on AI-proposed POs whose arrival prevented a stockout.

    A stockout is 'avoided' when outcome.expected_stockout_prevented is true
    (pre-delivery demand exceeded stock on hand) and no actual stockout was
    observed. Revenue protected = units x unit_cost x revenue_multiplier.
    """
    if since is None or until is None:
        today = date.today()
        since, until = _window_bounds(today - timedelta(days=30), today)
    multiplier = settings.roi_revenue_multiplier if revenue_multiplier is None else revenue_multiplier

    query = (
        select(POOutcome, PurchaseOrder)
        .join(PurchaseOrder, POOutcome.po_id == PurchaseOrder.id)
        .where(POOutcome.evaluated_at >= since, POOutcome.evaluated_at < until)
    )
    if merchant_id and merchant_id != 0:
        query = query.where(PurchaseOrder.merchant_id == merchant_id)

    factory = session_factory or _default_factory
    async with factory() as session:
        rows = (await session.execute(query)).all()

    avoided = [(o, po) for o, po in rows if o.expected_stockout_prevented and not o.actual_stockout_occurred]
    units = sum(po.quantity for _, po in avoided)
    protected_cost = sum(po.quantity * float(po.unit_cost or 0) for _, po in avoided)
    return {
        "events": len(avoided),
        "units": units,
        "revenue_protected_usd": round(protected_cost * multiplier, 2),
    }


async def calculate_po_decisioning(
    merchant_id: int = 0,
    since: datetime | None = None,
    until: datetime | None = None,
    session_factory: SessionFactory | None = None,
) -> dict[str, Any]:
    """Acceptance rate, time-to-decision, and excess commitment avoided.

    Time-to-decision uses audit_log (po.approve/po.reject) timestamps when
    present, falling back to approved_at for approvals without an audit row.
    Excess = quantities trimmed before approval + rejected POs, at cost.
    """
    if since is None or until is None:
        today = date.today()
        since, until = _window_bounds(today - timedelta(days=30), today)

    po_query = select(PurchaseOrder).where(
        PurchaseOrder.created_at >= since,
        PurchaseOrder.created_at < until,
        PurchaseOrder.status.in_([POStatus.approved, POStatus.rejected]),
    )
    audit_query = select(AuditLog).where(
        AuditLog.action.in_(_DECISION_ACTIONS),
        AuditLog.created_at >= since,
    )
    if merchant_id and merchant_id != 0:
        po_query = po_query.where(PurchaseOrder.merchant_id == merchant_id)
        audit_query = audit_query.where(AuditLog.merchant_id == merchant_id)

    factory = session_factory or _default_factory
    async with factory() as session:
        pos = (await session.execute(po_query)).scalars().all()
        audits = (await session.execute(audit_query)).scalars().all()

    decided_at: dict[str, datetime] = {}
    for entry in audits:
        if entry.target_id:
            decided_at[str(entry.target_id)] = entry.created_at

    accepted = [p for p in pos if p.status == POStatus.approved]
    rejected = [p for p in pos if p.status == POStatus.rejected]
    as_is = [p for p in accepted if not p.edited_before_approval]
    edited = [p for p in accepted if p.edited_before_approval]

    durations: list[float] = []
    for po in pos:
        stamp = decided_at.get(str(po.id)) or po.approved_at
        if stamp is None or po.created_at is None:
            continue
        durations.append((_aware(stamp) - _aware(po.created_at)).total_seconds() / 3600.0)

    trimmed_units = 0
    trimmed_capital = 0.0
    trimmed_pos = 0
    for po in edited:
        original = po.original_quantity or 0
        if original > po.quantity:
            delta = original - po.quantity
            trimmed_pos += 1
            trimmed_units += delta
            trimmed_capital += delta * float(po.unit_cost or 0)

    rejected_units = sum(p.quantity for p in rejected)
    rejected_capital = sum(float(p.total_cost or 0) or p.quantity * float(p.unit_cost or 0) for p in rejected)

    decided = len(pos)
    return {
        "decided": decided,
        "accepted": len(accepted),
        "rejected": len(rejected),
        "accepted_as_is": len(as_is),
        "edited_then_approved": len(edited),
        "acceptance_rate_pct": round(len(accepted) / decided * 100, 1) if decided else 0.0,
        "avg_hours_to_decision": round(fmean(durations), 1) if durations else None,
        "decisions_with_timestamp": len(durations),
        "excess_reduction": {
            "units": trimmed_units + rejected_units,
            "capital_freed_usd": round(trimmed_capital + rejected_capital, 2),
            "trimmed_pos": trimmed_pos,
            "rejected_pos": len(rejected),
        },
    }


async def calculate_forecast_accuracy(
    merchant_id: int = 0,
    since: datetime | None = None,
    until: datetime | None = None,
    session_factory: SessionFactory | None = None,
) -> dict[str, Any]:
    """Ensemble vs baseline backtest accuracy plus a daily trend series.

    backtest_wmape/backtest_bias are stored as fractions and reported here as
    percentages. improvement_pct > 0 means the ensemble beats the baseline.
    """
    if since is None or until is None:
        today = date.today()
        since, until = _window_bounds(today - timedelta(days=30), today)

    forecast_query = (
        select(Forecast)
        .join(Sku, Forecast.sku_id == Sku.id)
        .where(Forecast.created_at >= since, Forecast.created_at < until)
    )
    outcome_query = (
        select(func.count(POOutcome.id), func.avg(POOutcome.forecast_error_pct))
        .join(PurchaseOrder, POOutcome.po_id == PurchaseOrder.id)
        .where(POOutcome.evaluated_at >= since, POOutcome.evaluated_at < until)
    )
    if merchant_id and merchant_id != 0:
        forecast_query = forecast_query.where(Sku.merchant_id == merchant_id)
        outcome_query = outcome_query.where(PurchaseOrder.merchant_id == merchant_id)

    factory = session_factory or _default_factory
    async with factory() as session:
        rows = (await session.execute(forecast_query)).scalars().all()
        outcome_count, outcome_avg = (await session.execute(outcome_query)).one()

    def _pct(values: list[float]) -> float | None:
        return round(fmean(values) * 100, 1) if values else None

    def _wmape_values(items: list[Forecast]) -> list[float]:
        return [float(f.backtest_wmape) for f in items if f.backtest_wmape is not None]

    ensemble = [f for f in rows if f.model_version == "ensemble_v2" and f.backtest_wmape is not None]
    baseline = [f for f in rows if f.model_version == "exp_smoothing_v1" and f.backtest_wmape is not None]
    ensemble_wmape = _pct(_wmape_values(ensemble))
    baseline_wmape = _pct(_wmape_values(baseline))
    ensemble_bias = _pct([float(f.backtest_bias) for f in ensemble if f.backtest_bias is not None])
    baseline_bias = _pct([float(f.backtest_bias) for f in baseline if f.backtest_bias is not None])

    improvement: float | None = None
    if ensemble_wmape is not None and baseline_wmape not in (None, 0):
        improvement = round((float(baseline_wmape) - float(ensemble_wmape)) / float(baseline_wmape) * 100, 1)

    by_day: dict[date, dict[str, list[Forecast]]] = {}
    for f in rows:
        if f.backtest_wmape is None or f.created_at is None:
            continue
        day = _aware(f.created_at).date()
        key = "ensemble" if f.model_version == "ensemble_v2" else "baseline"
        by_day.setdefault(day, {"ensemble": [], "baseline": []})[key].append(f)

    series = [
        {
            "date": day.isoformat(),
            "ensemble_wmape_pct": _pct(_wmape_values(buckets["ensemble"])),
            "baseline_wmape_pct": _pct(_wmape_values(buckets["baseline"])),
        }
        for day, buckets in sorted(by_day.items())
    ]

    return {
        "ensemble_wmape_pct": ensemble_wmape,
        "ensemble_bias_pct": ensemble_bias,
        "ensemble_count": len(ensemble),
        "baseline_wmape_pct": baseline_wmape,
        "baseline_bias_pct": baseline_bias,
        "baseline_count": len(baseline),
        "wmape_improvement_pct": improvement,
        "outcome_mape_pct": round(float(outcome_avg), 1) if outcome_avg is not None else None,
        "outcome_count": int(outcome_count),
        "series": series[-_MAX_SERIES_POINTS:],
    }


async def calculate_llm_usage(
    merchant_id: int = 0,
    since: datetime | None = None,
    until: datetime | None = None,
    session_factory: SessionFactory | None = None,
) -> dict[str, Any]:
    """LLM spend and call volume: pipeline nodes + chat (both persisted)."""
    if since is None or until is None:
        today = date.today()
        since, until = _window_bounds(today - timedelta(days=30), today)

    usage_query = select(
        func.count(LlmUsage.id),
        func.coalesce(func.sum(LlmUsage.tokens_in), 0),
        func.coalesce(func.sum(LlmUsage.tokens_out), 0),
        func.coalesce(func.sum(LlmUsage.estimated_cost), 0.0),
    ).where(LlmUsage.created_at >= since, LlmUsage.created_at < until)
    chat_query = select(
        func.count(ChatMessage.id),
        func.coalesce(func.sum(ChatMessage.tokens_in), 0),
        func.coalesce(func.sum(ChatMessage.tokens_out), 0),
        func.coalesce(func.sum(ChatMessage.cost_usd), 0.0),
    ).where(
        ChatMessage.role == "assistant",
        ChatMessage.created_at >= since,
        ChatMessage.created_at < until,
    )
    if merchant_id and merchant_id != 0:
        chat_query = chat_query.where(ChatMessage.merchant_id == merchant_id)

    factory = session_factory or _default_factory
    async with factory() as session:
        usage_count, usage_in, usage_out, usage_cost = (await session.execute(usage_query)).one()
        chat_count, chat_in, chat_out, chat_cost = (await session.execute(chat_query)).one()

    pipeline_cost = float(usage_cost or 0)
    chat_cost_f = float(chat_cost or 0)
    return {
        "cost_usd": round(pipeline_cost + chat_cost_f, 4),
        "pipeline_cost_usd": round(pipeline_cost, 4),
        "chat_cost_usd": round(chat_cost_f, 4),
        "calls": int(usage_count or 0) + int(chat_count or 0),
        "tokens_in": int(usage_in or 0) + int(chat_in or 0),
        "tokens_out": int(usage_out or 0) + int(chat_out or 0),
    }


async def calculate_at_risk(
    merchant_id: int = 0,
    session_factory: SessionFactory | None = None,
) -> dict[str, Any]:
    """Current (unresolved) at-risk SKUs — a live snapshot, not windowed."""
    query = (
        select(RiskAlert, Sku)
        .join(Sku, RiskAlert.sku_id == Sku.id)
        .where(RiskAlert.resolved.is_(False), RiskAlert.risk_level.in_(["critical", "warning"]))
    )
    if merchant_id and merchant_id != 0:
        query = query.where(Sku.merchant_id == merchant_id)

    factory = session_factory or _default_factory
    async with factory() as session:
        rows = (await session.execute(query)).all()

    latest: dict[int, tuple[RiskAlert, Sku]] = {}
    for alert, sku in rows:
        current = latest.get(alert.sku_id)
        if current is None or _aware(alert.created_at) > _aware(current[0].created_at):
            latest[alert.sku_id] = (alert, sku)

    ordered = sorted(latest.values(), key=lambda pair: (pair[0].risk_level != "critical", pair[0].sku_id))
    critical = sum(1 for alert, _ in latest.values() if alert.risk_level == "critical")
    return {
        "total": len(latest),
        "critical": critical,
        "warning": len(latest) - critical,
        "skus": [
            {
                "sku_id": alert.sku_id,
                "sku_code": sku.sku_code,
                "risk_level": alert.risk_level,
                "reason": alert.reason,
            }
            for alert, sku in ordered[:8]
        ],
    }


async def calculate_forecast_health(
    merchant_id: int = 0,
    since: datetime | None = None,
    until: datetime | None = None,
    session_factory: SessionFactory | None = None,
) -> dict[str, Any]:
    """Interval coverage, confidence-width distribution, engine + fallback mix."""
    if since is None or until is None:
        today = date.today()
        since, until = _window_bounds(today - timedelta(days=30), today)

    query = (
        select(Forecast)
        .join(Sku, Forecast.sku_id == Sku.id)
        .where(Forecast.created_at >= since, Forecast.created_at < until)
    )
    if merchant_id and merchant_id != 0:
        query = query.where(Sku.merchant_id == merchant_id)

    factory = session_factory or _default_factory
    async with factory() as session:
        rows = (await session.execute(query)).scalars().all()

    total = len(rows)
    with_intervals = [f for f in rows if f.p10_daily_demand is not None and f.p90_daily_demand is not None]

    counts = {bucket: 0 for bucket in _CONFIDENCE_BUCKETS}
    for f in with_intervals:
        p50 = float(f.predicted_daily_demand or 0)
        width = (float(f.p90_daily_demand or 0) - float(f.p10_daily_demand or 0)) / max(p50, 0.01)
        bucket = "tight" if width <= 0.5 else "typical" if width <= 1.0 else "wide"
        counts[bucket] += 1

    model_counts: dict[str, int] = {}
    fallbacks = 0
    for f in rows:
        model_counts[f.model_version] = model_counts.get(f.model_version, 0) + 1
        meta = f.model_meta or {}
        if meta.get("fallback_used"):
            fallbacks += 1

    return {
        "forecast_confidence": {
            "total_forecasts": total,
            "with_intervals": len(with_intervals),
            "coverage_pct": round(len(with_intervals) / total * 100, 1) if total else 0.0,
            "distribution": [{"bucket": bucket, "count": counts[bucket]} for bucket in _CONFIDENCE_BUCKETS],
        },
        "engine": {
            "total_forecasts": total,
            "fallbacks": fallbacks,
            "fallback_rate_pct": round(fallbacks / total * 100, 1) if total else 0.0,
            "distribution": [
                {"model": model, "count": count}
                for model, count in sorted(model_counts.items(), key=lambda kv: (-kv[1], kv[0]))
            ],
        },
    }


async def calculate_roi_report(
    merchant_id: int,
    start: date,
    end: date,
    session_factory: SessionFactory | None = None,
) -> dict[str, Any]:
    """Full ROI dashboard payload for the inclusive [start, end] window."""
    since, until = _window_bounds(start, end)
    factory = session_factory or _default_factory

    stockouts = await calculate_stockouts_avoided(merchant_id, since, until, session_factory=factory)
    decisions = await calculate_po_decisioning(merchant_id, since, until, session_factory=factory)
    accuracy = await calculate_forecast_accuracy(merchant_id, since, until, session_factory=factory)
    llm = await calculate_llm_usage(merchant_id, since, until, session_factory=factory)
    at_risk = await calculate_at_risk(merchant_id, session_factory=factory)
    health = await calculate_forecast_health(merchant_id, since, until, session_factory=factory)

    excess = decisions["excess_reduction"]
    value = round(float(stockouts["revenue_protected_usd"]) + float(excess["capital_freed_usd"]), 2)
    cost = float(llm["cost_usd"])
    decided = int(decisions["decided"])

    return {
        "period": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "days": (end - start).days + 1,
        },
        "operational": {
            "stockouts_avoided": stockouts,
            "excess_reduction": excess,
            "forecast_accuracy": accuracy,
            "po_decisions": decisions,
        },
        "efficiency": {
            "hours_saved": round(decided * settings.roi_manual_po_minutes / 60, 1),
            "hours_saved_basis": {
                "decided_pos": decided,
                "minutes_per_po": settings.roi_manual_po_minutes,
            },
            "llm": {
                **llm,
                "cost_per_decision_usd": round(cost / decided, 4) if decided else None,
            },
            "value_generated_usd": value,
            "roi_multiple": round(value / cost, 1) if cost > 0 else None,
            "assumptions": {
                "revenue_multiplier": settings.roi_revenue_multiplier,
                "minutes_per_po": settings.roi_manual_po_minutes,
            },
        },
        "health": {
            "at_risk": at_risk,
            "forecast_confidence": health["forecast_confidence"],
            "engine": health["engine"],
        },
    }
