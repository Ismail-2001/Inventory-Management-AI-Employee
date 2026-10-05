"""Tools the chat agent can call.

All tools are read-only except ``draft_purchase_order``, which proposes an
action payload but never writes to the database — persistence happens only
after a human confirms via POST /api/v1/chat/actions/{id}/confirm, and even
then the PO is created as ``pending_approval`` (never auto-approved).

Every successful result carries a ``summary`` (one line, shown in the UI as
a tool chip and usable verbatim by the LLM). Failures return
``{"ok": False, "error": str, "summary": str}``.
"""

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import and_, func, or_, select

from agent.db import async_session_factory
from agent.metrics import calculate_forecast_error_summary
from agent.models import Forecast, POStatus, PurchaseOrder, RiskAlert, SalesHistory, Sku, Supplier
from agent.ordering import calculate_reorder_quantity
from agent.risk import determine_risk_level

_RISK_ORDER = {"critical": 0, "warning": 1, "safe": 2}
_IN_TRANSIT_WINDOW_DAYS = 14


@dataclass
class ToolContext:
    """Per-request scope passed to every tool."""

    merchant_id: int


class SkuRef(BaseModel):
    sku: str = Field(description="SKU code, product title, or numeric SKU id")


class FindAtRiskArgs(BaseModel):
    days_ahead: int = Field(default=14, ge=1, le=90, description="Look-ahead window in days")
    severity: str = Field(default="any", pattern="^(any|critical|warning)$", description="Risk level filter")


class DraftPOArgs(BaseModel):
    sku: str = Field(description="SKU code, product title, or numeric SKU id")
    quantity: int | None = Field(default=None, ge=1, description="Override the suggested reorder quantity")
    reason: str = Field(default="", max_length=500, description="Why this order is needed")


class CashImpactArgs(BaseModel):
    horizon_days: int = Field(default=30, ge=1, le=120, description="Spend window in days")


class ForecastAccuracyArgs(BaseModel):
    period: Literal["7d", "30d", "90d"] = Field(default="30d", description="Evaluation window")


def _scoped(query: Any, model: Any, ctx: ToolContext) -> Any:
    if ctx.merchant_id and ctx.merchant_id != 0:
        return query.where(model.merchant_id == ctx.merchant_id)
    return query


async def _load_supplier(session: Any) -> dict[str, Any]:
    row = (await session.execute(select(Supplier).limit(1))).scalar_one_or_none()
    if not row:
        return {"supplier_id": None, "lead_time_days": 7, "moq": 1, "moq_by_sku": {}, "unit_cost_by_sku": {}}
    return {
        "supplier_id": row.id,
        "lead_time_days": row.default_lead_time_days or 7,
        "moq": row.default_moq or 1,
        "moq_by_sku": row.moq_by_sku if isinstance(row.moq_by_sku, dict) else {},
        "unit_cost_by_sku": row.unit_cost_by_sku if isinstance(row.unit_cost_by_sku, dict) else {},
    }


async def _list_skus(session: Any, ctx: ToolContext) -> list[Sku]:
    result = await session.execute(_scoped(select(Sku), Sku, ctx).order_by(Sku.id))
    return list(result.scalars().all())


async def _find_sku(session: Any, ref: str, ctx: ToolContext) -> Sku | None:
    needle = ref.strip()
    if not needle:
        return None
    conditions = [func.lower(Sku.sku_code) == needle.lower(), func.lower(Sku.title) == needle.lower()]
    if needle.isdigit():
        conditions.append(Sku.id == int(needle))
    query = _scoped(select(Sku), Sku, ctx).where(or_(*conditions)).order_by(Sku.id).limit(1)
    row = (await session.execute(query)).scalar_one_or_none()
    return row if isinstance(row, Sku) else None


async def _latest_forecasts(session: Any, sku_ids: list[int]) -> dict[int, Forecast]:
    if not sku_ids:
        return {}
    result = await session.execute(
        select(Forecast).where(Forecast.sku_id.in_(sku_ids)).order_by(Forecast.created_at.desc())
    )
    latest: dict[int, Forecast] = {}
    for row in result.scalars().all():
        latest.setdefault(row.sku_id, row)
    return latest


async def _open_order_map(session: Any, sku_ids: list[int]) -> dict[int, int]:
    if not sku_ids:
        return {}
    cutoff = datetime.now(UTC) - timedelta(days=_IN_TRANSIT_WINDOW_DAYS)
    result = await session.execute(
        select(PurchaseOrder.sku_id, func.coalesce(func.sum(PurchaseOrder.quantity), 0))
        .where(
            PurchaseOrder.sku_id.in_(sku_ids),
            or_(
                PurchaseOrder.status == POStatus.pending_approval,
                and_(PurchaseOrder.status == POStatus.approved, PurchaseOrder.approved_at >= cutoff),
            ),
        )
        .group_by(PurchaseOrder.sku_id)
    )
    return {int(sid): int(qty) for sid, qty in result.all()}


async def _open_alerts(session: Any, sku_ids: list[int]) -> dict[int, list[RiskAlert]]:
    if not sku_ids:
        return {}
    result = await session.execute(
        select(RiskAlert).where(RiskAlert.sku_id.in_(sku_ids), RiskAlert.resolved.is_(False)).order_by(RiskAlert.id)
    )
    by_sku: dict[int, list[RiskAlert]] = {}
    for alert in result.scalars().all():
        by_sku.setdefault(alert.sku_id, []).append(alert)
    return by_sku


async def _sales_totals(session: Any, sku_ids: list[int], days: int) -> dict[int, dict[str, float]]:
    if not sku_ids:
        return {}
    cutoff = date.today() - timedelta(days=days)
    result = await session.execute(
        select(SalesHistory).where(SalesHistory.sku_id.in_(sku_ids), SalesHistory.date >= cutoff)
    )
    totals: dict[int, dict[str, float]] = {}
    for row in result.scalars().all():
        bucket = totals.setdefault(row.sku_id, {"units": 0, "days_with_sales": 0})
        bucket["units"] += row.units_sold
        if row.units_sold > 0:
            bucket["days_with_sales"] += 1
    return totals


def _sku_block(sku: Sku) -> dict[str, Any]:
    return {
        "id": sku.id,
        "sku_code": sku.sku_code,
        "title": sku.title,
        "current_stock": sku.current_stock,
        "merchant_id": sku.merchant_id,
    }


def _forecast_block(forecast: Forecast | None) -> dict[str, Any] | None:
    if not forecast:
        return None
    return {
        "predicted_daily_demand": round(forecast.predicted_daily_demand, 2),
        "days_of_stock_remaining": round(forecast.days_of_stock_remaining, 1)
        if forecast.days_of_stock_remaining is not None
        else None,
        "model_version": forecast.model_version,
        "backtest_wmape": round(forecast.backtest_wmape, 3) if forecast.backtest_wmape is not None else None,
        "backtest_bias": round(forecast.backtest_bias, 3) if forecast.backtest_bias is not None else None,
        "horizon_days": forecast.horizon_days,
        "created_at": forecast.created_at.isoformat() if forecast.created_at else None,
    }


async def get_sku_status(args: SkuRef, ctx: ToolContext) -> dict[str, Any]:
    async with async_session_factory() as session:
        sku = await _find_sku(session, args.sku, ctx)
        if not sku:
            return {"ok": False, "error": f"No SKU matches '{args.sku}'", "summary": f"No SKU matches '{args.sku}'."}

        supplier = await _load_supplier(session)
        forecasts = await _latest_forecasts(session, [sku.id])
        forecast = forecasts.get(sku.id)
        on_order_map = await _open_order_map(session, [sku.id])
        alerts = await _open_alerts(session, [sku.id])
        sales = await _sales_totals(session, [sku.id], days=14)

        days_cover = forecast.days_of_stock_remaining if forecast else None
        risk_level, risk_reason = determine_risk_level(days_cover, supplier["lead_time_days"])
        predicted = forecast.predicted_daily_demand if forecast else 0.0
        sku_code = sku.sku_code or str(sku.id)
        moq = supplier["moq_by_sku"].get(sku_code, supplier["moq"]) if sku_code else supplier["moq"]
        unit_cost = supplier["unit_cost_by_sku"].get(sku_code, 0.0) if sku_code else 0.0
        on_order = on_order_map.get(sku.id, 0)
        suggested = calculate_reorder_quantity(
            predicted_daily_demand=predicted,
            current_stock=sku.current_stock,
            lead_time_days=supplier["lead_time_days"],
            moq=moq,
            on_order=on_order,
        )
        sales_block = sales.get(sku.id, {"units": 0, "days_with_sales": 0})

    cover_text = f"{days_cover:.0f} days cover" if days_cover is not None else "no forecast yet"
    return {
        "summary": (
            f"{sku_code}: {sku.current_stock} in stock, {predicted:.1f}/day demand, "
            f"{cover_text}, risk {risk_level}, suggested reorder {suggested}"
        ),
        "sku": _sku_block(sku),
        "forecast": _forecast_block(forecast),
        "risk": {"level": risk_level, "reason": risk_reason},
        "lead_time_days": supplier["lead_time_days"],
        "moq": moq,
        "unit_cost": unit_cost,
        "on_order": on_order,
        "suggested_reorder_quantity": suggested,
        "sales_last_14d": sales_block,
        "open_alerts": [{"risk_level": a.risk_level, "reason": a.reason} for a in alerts.get(sku.id, [])],
    }


async def find_at_risk_skus(args: FindAtRiskArgs, ctx: ToolContext) -> dict[str, Any]:
    async with async_session_factory() as session:
        skus = await _list_skus(session, ctx)
        forecasts = await _latest_forecasts(session, [s.id for s in skus])
        supplier = await _load_supplier(session)
        on_order_map = await _open_order_map(session, [s.id for s in skus])

    rows: list[dict[str, Any]] = []
    for sku in skus:
        forecast = forecasts.get(sku.id)
        days_cover = forecast.days_of_stock_remaining if forecast else None
        level, reason = determine_risk_level(days_cover, supplier["lead_time_days"])
        if level == "safe":
            continue
        if days_cover is None or days_cover > args.days_ahead:
            continue
        if args.severity != "any" and level != args.severity:
            continue
        predicted = forecast.predicted_daily_demand if forecast else 0.0
        sku_code = sku.sku_code or str(sku.id)
        moq = supplier["moq_by_sku"].get(sku_code, supplier["moq"]) if sku_code else supplier["moq"]
        suggested = calculate_reorder_quantity(
            predicted_daily_demand=predicted,
            current_stock=sku.current_stock,
            lead_time_days=supplier["lead_time_days"],
            moq=moq,
            on_order=on_order_map.get(sku.id, 0),
        )
        rows.append(
            {
                "sku": _sku_block(sku),
                "risk_level": level,
                "reason": reason,
                "days_of_stock_remaining": round(days_cover, 1) if days_cover is not None else None,
                "predicted_daily_demand": round(predicted, 2),
                "suggested_reorder_quantity": suggested,
            }
        )

    rows.sort(key=lambda r: (_RISK_ORDER.get(r["risk_level"], 9), r["days_of_stock_remaining"] or 0))
    rows = rows[:20]
    critical = sum(1 for r in rows if r["risk_level"] == "critical")
    return {
        "summary": (
            f"{len(rows)} SKU(s) at risk in the next {args.days_ahead} days ({critical} critical)"
            if rows
            else f"No SKUs at risk in the next {args.days_ahead} days"
        ),
        "days_ahead": args.days_ahead,
        "severity": args.severity,
        "items": rows,
    }


async def explain_forecast(args: SkuRef, ctx: ToolContext) -> dict[str, Any]:
    async with async_session_factory() as session:
        sku = await _find_sku(session, args.sku, ctx)
        if not sku:
            return {"ok": False, "error": f"No SKU matches '{args.sku}'", "summary": f"No SKU matches '{args.sku}'."}
        forecasts = await _latest_forecasts(session, [sku.id])
        forecast = forecasts.get(sku.id)

    if not forecast:
        return {
            "ok": False,
            "error": "No forecast computed for this SKU yet — run the pipeline sync.",
            "summary": f"No forecast yet for {sku.sku_code or sku.id}.",
        }

    days_cover = forecast.days_of_stock_remaining
    parts = [
        f"Forecast for {sku.sku_code or sku.id} (model {forecast.model_version}): "
        f"{forecast.predicted_daily_demand:.1f} units/day expected demand"
    ]
    if days_cover is not None:
        parts.append(f"stock covers about {days_cover:.0f} days")
    if forecast.backtest_wmape is not None:
        parts.append(f"backtest wMAPE {forecast.backtest_wmape * 100:.1f}%")
    if forecast.backtest_bias is not None:
        parts.append(f"bias {forecast.backtest_bias * 100:.1f}%")
    if forecast.p10_daily_demand is not None and forecast.p90_daily_demand is not None:
        parts.append(f"demand band {forecast.p10_daily_demand:.1f}–{forecast.p90_daily_demand:.1f}/day")

    return {
        "summary": "; ".join(parts) + ".",
        "sku": _sku_block(sku),
        "forecast": _forecast_block(forecast),
        "p10_daily_demand": forecast.p10_daily_demand,
        "p90_daily_demand": forecast.p90_daily_demand,
        "days_of_cover_p10": forecast.days_of_cover_p10,
        "days_of_cover_p90": forecast.days_of_cover_p90,
        "model_meta": forecast.model_meta if isinstance(forecast.model_meta, dict) else None,
    }


async def draft_purchase_order(args: DraftPOArgs, ctx: ToolContext) -> dict[str, Any]:
    """Propose a PO. Persists NOTHING — returns action params for confirmation."""
    async with async_session_factory() as session:
        sku = await _find_sku(session, args.sku, ctx)
        if not sku:
            return {"ok": False, "error": f"No SKU matches '{args.sku}'", "summary": f"No SKU matches '{args.sku}'."}
        supplier = await _load_supplier(session)
        forecasts = await _latest_forecasts(session, [sku.id])
        on_order_map = await _open_order_map(session, [sku.id])
        forecast = forecasts.get(sku.id)

    predicted = forecast.predicted_daily_demand if forecast else 0.0
    sku_code = sku.sku_code or str(sku.id)
    moq = supplier["moq_by_sku"].get(sku_code, supplier["moq"]) if sku_code else supplier["moq"]
    unit_cost = float(supplier["unit_cost_by_sku"].get(sku_code, 0.0) if sku_code else 0.0)
    on_order = on_order_map.get(sku.id, 0)
    suggested = calculate_reorder_quantity(
        predicted_daily_demand=predicted,
        current_stock=sku.current_stock,
        lead_time_days=supplier["lead_time_days"],
        moq=moq,
        on_order=on_order,
    )

    quantity = args.quantity if args.quantity is not None else suggested
    if quantity <= 0:
        return {
            "ok": False,
            "error": (
                "Suggested reorder quantity is 0 (stock is adequate). "
                "Pass an explicit quantity to draft an order anyway."
            ),
            "summary": "No reorder needed for this SKU — pass an explicit quantity to draft anyway.",
        }

    days_cover = forecast.days_of_stock_remaining if forecast else None
    reasoning_parts = [
        f"Chat draft: order {quantity} × {sku.title} ({sku_code}).",
        f"Stock {sku.current_stock}",
        f"{predicted:.1f}/day demand",
        f"lead time {supplier['lead_time_days']}d",
        f"MOQ {moq}",
    ]
    if days_cover is not None:
        reasoning_parts.append(f"{days_cover:.0f}d cover")
    if on_order:
        reasoning_parts.append(f"{on_order} already on order")
    if args.reason.strip():
        reasoning_parts.append(f"user reason: {args.reason.strip()}")

    return {
        "summary": (
            f"Proposed PO: {quantity} × {sku_code} at ${unit_cost:.2f} = "
            f"${unit_cost * quantity:.2f} — awaiting your confirmation"
        ),
        "confirmation_required": True,
        "suggested_quantity": suggested,
        "action": {
            "tool": "draft_purchase_order",
            "sku_id": sku.id,
            "sku_code": sku_code,
            "title": sku.title,
            "supplier_id": supplier["supplier_id"],
            "quantity": quantity,
            "unit_cost": unit_cost,
            "total_cost": round(unit_cost * quantity, 2),
            "reasoning": " ".join(reasoning_parts),
        },
    }


async def get_cash_impact(args: CashImpactArgs, ctx: ToolContext) -> dict[str, Any]:
    cutoff = datetime.now(UTC) - timedelta(days=args.horizon_days)
    async with async_session_factory() as session:
        pending_q = _scoped(
            select(func.coalesce(func.sum(PurchaseOrder.total_cost), 0.0)).where(
                PurchaseOrder.status == POStatus.pending_approval
            ),
            PurchaseOrder,
            ctx,
        )
        open_commitments = float((await session.execute(pending_q)).scalar_one())

        recent_q = _scoped(
            select(func.coalesce(func.sum(PurchaseOrder.total_cost), 0.0)).where(
                PurchaseOrder.status == POStatus.approved, PurchaseOrder.created_at >= cutoff
            ),
            PurchaseOrder,
            ctx,
        )
        recent_spend = float((await session.execute(recent_q)).scalar_one())

        skus = await _list_skus(session, ctx)
        forecasts = await _latest_forecasts(session, [s.id for s in skus])
        supplier = await _load_supplier(session)
        on_order_map = await _open_order_map(session, [s.id for s in skus])

    projected_items: list[dict[str, Any]] = []
    for sku in skus:
        forecast = forecasts.get(sku.id)
        days_cover = forecast.days_of_stock_remaining if forecast else None
        level, _ = determine_risk_level(days_cover, supplier["lead_time_days"])
        if level == "safe":
            continue
        predicted = forecast.predicted_daily_demand if forecast else 0.0
        sku_code = sku.sku_code or str(sku.id)
        moq = supplier["moq_by_sku"].get(sku_code, supplier["moq"]) if sku_code else supplier["moq"]
        qty = calculate_reorder_quantity(
            predicted_daily_demand=predicted,
            current_stock=sku.current_stock,
            lead_time_days=supplier["lead_time_days"],
            moq=moq,
            on_order=on_order_map.get(sku.id, 0),
        )
        if qty <= 0:
            continue
        unit_cost = float(supplier["unit_cost_by_sku"].get(sku_code, 0.0) if sku_code else 0.0)
        projected_items.append(
            {
                "sku_code": sku_code,
                "title": sku.title,
                "quantity": qty,
                "unit_cost": unit_cost,
                "estimated_cost": round(unit_cost * qty, 2),
            }
        )

    projected = round(sum(i["estimated_cost"] for i in projected_items), 2)
    projected_items.sort(key=lambda i: i["estimated_cost"], reverse=True)
    return {
        "summary": (
            f"Open POs ${open_commitments:.2f}, approved spend last {args.horizon_days}d "
            f"${recent_spend:.2f}, projected replenishment ${projected:.2f}"
        ),
        "horizon_days": args.horizon_days,
        "open_commitments": round(open_commitments, 2),
        "recent_spend": round(recent_spend, 2),
        "projected_replenishment": projected,
        "projected_items": projected_items[:20],
    }


async def get_forecast_accuracy(args: ForecastAccuracyArgs, ctx: ToolContext) -> dict[str, Any]:
    days = int(args.period.rstrip("d"))
    since = date.today() - timedelta(days=days)
    summary = await calculate_forecast_error_summary(since=since)

    async with async_session_factory() as session:
        result = await session.execute(
            select(
                func.count(Forecast.id),
                func.avg(Forecast.backtest_wmape),
                func.avg(Forecast.backtest_bias),
            ).where(Forecast.backtest_wmape.is_not(None), Forecast.created_at >= since)
        )
        count, avg_wmape, avg_bias = result.one()

    if not count:
        return {
            "summary": f"No forecast accuracy data for the last {days} days.",
            "period": args.period,
            "evaluated": 0,
        }

    block: dict[str, Any] = {
        "period": args.period,
        "evaluated": int(count),
        "avg_backtest_wmape": round(float(avg_wmape), 3) if avg_wmape is not None else None,
        "avg_backtest_bias": round(float(avg_bias), 3) if avg_bias is not None else None,
        "outcomes": summary,
    }
    wmape_pct = f"{float(avg_wmape) * 100:.1f}%" if avg_wmape is not None else "n/a"
    outcome_part = (
        f"; {summary['count']} outcome(s), mean error {summary['mean_error_pct']}%"
        if summary
        else "; no evaluated outcomes yet"
    )
    block["summary"] = f"Forecast accuracy last {days}d: avg wMAPE {wmape_pct} over {int(count)} SKUs{outcome_part}."
    return block


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[[Any, ToolContext], Awaitable[dict[str, Any]]]
    mutating: bool = False

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.args_model.model_json_schema(),
            },
        }

    def gemini_schema(self) -> dict[str, Any]:
        schema = self.args_model.model_json_schema()
        schema.pop("title", None)
        return {"name": self.name, "description": self.description, "parameters": schema}


TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="get_sku_status",
        description=(
            "Current stock, demand forecast, risk level, open alerts and suggested reorder "
            "quantity for one SKU. Use when the user asks about a specific product/SKU."
        ),
        args_model=SkuRef,
        handler=get_sku_status,
    ),
    ToolSpec(
        name="find_at_risk_skus",
        description=(
            "List SKUs at risk of stocking out within a look-ahead window, ordered by "
            "severity. Use for questions like 'what needs reordering' or 'what's at risk'."
        ),
        args_model=FindAtRiskArgs,
        handler=find_at_risk_skus,
    ),
    ToolSpec(
        name="explain_forecast",
        description=(
            "Latest demand forecast for one SKU with model version, demand band, days of "
            "cover and backtest accuracy. Use when the user asks how a forecast was derived."
        ),
        args_model=SkuRef,
        handler=explain_forecast,
    ),
    ToolSpec(
        name="draft_purchase_order",
        description=(
            "PROPOSE a purchase order for one SKU. Does not create the order: returns a "
            "proposed action that the user must confirm. Use when the user asks to order, "
            "reorder or restock a product. The order is created as pending approval."
        ),
        args_model=DraftPOArgs,
        handler=draft_purchase_order,
        mutating=True,
    ),
    ToolSpec(
        name="get_cash_impact",
        description=(
            "Cash exposure: open (pending) PO commitments, approved spend over a horizon, "
            "and projected cost of replenishing at-risk SKUs. Use for spend/cash questions."
        ),
        args_model=CashImpactArgs,
        handler=get_cash_impact,
    ),
    ToolSpec(
        name="get_forecast_accuracy",
        description=(
            "Forecast accuracy for a period (wMAPE/bias aggregates and evaluated outcomes). "
            "Use when the user asks how accurate the forecasts are."
        ),
        args_model=ForecastAccuracyArgs,
        handler=get_forecast_accuracy,
    ),
]

TOOL_REGISTRY: dict[str, ToolSpec] = {spec.name: spec for spec in TOOL_SPECS}


async def execute_tool(name: str, arguments: dict[str, Any], ctx: ToolContext) -> tuple[dict[str, Any], float]:
    """Validate args, run the tool, and measure elapsed milliseconds.

    Returns (result, elapsed_ms). Never raises: validation and handler
    failures come back as ``{"ok": False, "error": ...}``.
    """
    start = time.perf_counter()
    spec = TOOL_REGISTRY.get(name)
    if not spec:
        elapsed = (time.perf_counter() - start) * 1000
        return {"ok": False, "error": f"Unknown tool: {name}", "summary": f"Unknown tool: {name}"}, elapsed
    try:
        parsed = spec.args_model.model_validate(arguments or {})
    except ValidationError as exc:
        elapsed = (time.perf_counter() - start) * 1000
        message = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
        return {
            "ok": False,
            "error": f"Invalid arguments: {message}",
            "summary": f"Invalid arguments: {message}",
        }, elapsed

    try:
        result = await spec.handler(parsed, ctx)
    except Exception as exc:  # noqa: BLE001 — tool failures must not crash the turn
        elapsed = (time.perf_counter() - start) * 1000
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "summary": "Tool failed."}, elapsed

    elapsed = (time.perf_counter() - start) * 1000
    if not isinstance(result, dict):
        return {"ok": False, "error": "Tool returned a non-dict result", "summary": "Tool failed."}, elapsed
    if "summary" not in result:
        result["summary"] = name
    return result, elapsed
