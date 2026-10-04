"""Tool-layer tests: SQL-backed chat tools with a table-dispatching fake session."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from agent.chat import tools as chat_tools
from agent.chat.tools import ToolContext, execute_tool
from agent.models import Forecast, Sku, Supplier

CTX = ToolContext(merchant_id=0)


class FakeResult:
    def __init__(self, rows: list[Any] | None = None, scalar: Any = None, one: Any = None) -> None:
        self._rows = rows if rows is not None else []
        self._scalar = scalar
        self._one = one

    def scalars(self) -> FakeResult:
        return self

    def all(self) -> list[Any]:
        return self._rows

    def one(self) -> Any:
        if self._one is not None:
            return self._one
        return (self._scalar,)

    def scalar_one(self) -> Any:
        return self._scalar

    def scalar_one_or_none(self) -> Any:
        return self._scalar


class FakeSession:
    """Dispatches queries by the table name rendered in the SQL text."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self.data = data or {}
        self.added: list[Any] = []
        self.commits = 0
        self._po_scalar_calls = 0

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False

    async def execute(self, stmt: Any) -> FakeResult:
        text = str(stmt).lower()
        if "from suppliers" in text:
            return FakeResult(scalar=self.data.get("supplier"))
        if "from chat_messages" in text:
            return FakeResult(rows=self.data.get("chat_messages", []))
        if "from risk_alerts" in text:
            return FakeResult(rows=self.data.get("alerts", []))
        if "from sales_history" in text:
            return FakeResult(rows=self.data.get("sales", []))
        if "from forecasts" in text:
            if "avg(" in text:
                return FakeResult(one=self.data.get("accuracy_row", (0, None, None)))
            return FakeResult(rows=self.data.get("forecasts", []))
        if "from purchase_orders" in text:
            if "group by" in text:
                return FakeResult(rows=self.data.get("open_orders", []))
            self._po_scalar_calls += 1
            key = "pending_total" if self._po_scalar_calls == 1 else "recent_total"
            return FakeResult(scalar=self.data.get(key, 0.0))
        if "from skus" in text:
            rows = self.data.get("skus", [])
            return FakeResult(rows=rows, scalar=rows[0] if rows else None)
        return FakeResult()

    async def commit(self) -> None:
        self.commits += 1

    async def refresh(self, obj: Any) -> None:
        if getattr(obj, "id", None) is None:
            obj.id = 99

    def add(self, obj: Any) -> None:
        self.added.append(obj)


def _install(monkeypatch: pytest.MonkeyPatch, data: dict[str, Any]) -> FakeSession:
    session = FakeSession(data)
    monkeypatch.setattr(chat_tools, "async_session_factory", lambda: session)
    return session


def _sku(**overrides: Any) -> Sku:
    defaults: dict[str, Any] = dict(
        id=1,
        shopify_variant_id="var-1",
        merchant_id=None,
        sku_code="WID-1",
        title="Widget",
        current_stock=10,
    )
    defaults.update(overrides)
    return Sku(**defaults)


def _forecast(**overrides: Any) -> Forecast:
    defaults: dict[str, Any] = dict(
        id=1,
        sku_id=1,
        predicted_daily_demand=3.0,
        days_of_stock_remaining=5.0,
        model_version="exp_smoothing_v1",
        created_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    return Forecast(**defaults)


def _supplier(**overrides: Any) -> Supplier:
    defaults: dict[str, Any] = dict(
        id=1,
        name="Acme",
        default_lead_time_days=7,
        default_moq=10,
        moq_by_sku={"WID-1": 10},
        unit_cost_by_sku={"WID-1": 2.5},
    )
    defaults.update(overrides)
    return Supplier(**defaults)


@pytest.mark.asyncio
async def test_get_sku_status_reports_risk_and_reorder(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(
        monkeypatch,
        {
            "skus": [_sku()],
            "supplier": _supplier(),
            "forecasts": [_forecast()],
            "open_orders": [(1, 5)],
            "alerts": [],
            "sales": [],
        },
    )
    result, elapsed = await execute_tool("get_sku_status", {"sku": "WID-1"}, CTX)

    assert result.get("ok") is not False
    assert elapsed >= 0
    assert result["risk"]["level"] == "critical"
    assert result["lead_time_days"] == 7
    assert result["on_order"] == 5
    # demand 3/day * (7 lead + 7 buffer) = 42 needed - 10 stock - 5 on order = 27
    assert result["suggested_reorder_quantity"] == 27
    assert "WID-1" in result["summary"]


@pytest.mark.asyncio
async def test_get_sku_status_unknown_sku(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, {"skus": [], "supplier": None})
    result, _ = await execute_tool("get_sku_status", {"sku": "NOPE"}, CTX)

    assert result["ok"] is False
    assert "No SKU matches" in result["error"]


@pytest.mark.asyncio
async def test_find_at_risk_skus_filters_safe_and_window(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(
        monkeypatch,
        {
            "skus": [
                _sku(id=1, sku_code="CRIT-1", current_stock=5),
                _sku(id=2, sku_code="SAFE-1", current_stock=500),
                _sku(id=3, sku_code="FAR-1", current_stock=60),
            ],
            "supplier": _supplier(),
            "forecasts": [
                _forecast(id=1, sku_id=1, days_of_stock_remaining=5.0),
                _forecast(id=2, sku_id=2, days_of_stock_remaining=40.0),
                _forecast(id=3, sku_id=3, days_of_stock_remaining=9.0),
            ],
            "open_orders": [],
        },
    )
    result, _ = await execute_tool("find_at_risk_skus", {"days_ahead": 7, "severity": "any"}, CTX)

    assert result.get("ok") is not False
    codes = [item["sku"]["sku_code"] for item in result["items"]]
    assert codes == ["CRIT-1"]
    assert "1 SKU(s) at risk" in result["summary"]

    # Widen the window: the warning SKU (9 days cover) comes back too.
    result, _ = await execute_tool("find_at_risk_skus", {"days_ahead": 30, "severity": "any"}, CTX)
    codes = [item["sku"]["sku_code"] for item in result["items"]]
    assert codes == ["CRIT-1", "FAR-1"]


@pytest.mark.asyncio
async def test_draft_purchase_order_returns_action_and_writes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _install(
        monkeypatch,
        {
            "skus": [_sku()],
            "supplier": _supplier(),
            "forecasts": [_forecast()],
            "open_orders": [],
        },
    )
    result, _ = await execute_tool(
        "draft_purchase_order", {"sku": "WID-1", "quantity": 30, "reason": "promo next week"}, CTX
    )

    assert result["confirmation_required"] is True
    assert result["action"]["quantity"] == 30
    assert result["action"]["unit_cost"] == 2.5
    assert result["action"]["total_cost"] == 75.0
    assert "promo next week" in result["action"]["reasoning"]
    assert session.added == []
    assert session.commits == 0


@pytest.mark.asyncio
async def test_draft_purchase_order_refuses_when_no_reorder_needed(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(
        monkeypatch,
        {
            "skus": [_sku(current_stock=500)],
            "supplier": _supplier(),
            "forecasts": [_forecast(predicted_daily_demand=1.0)],
            "open_orders": [],
        },
    )
    result, _ = await execute_tool("draft_purchase_order", {"sku": "WID-1"}, CTX)

    assert result["ok"] is False
    assert "explicit quantity" in result["error"]


@pytest.mark.asyncio
async def test_get_cash_impact_sums_commitments(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(
        monkeypatch,
        {
            "pending_total": 120.5,
            "recent_total": 300.0,
            "skus": [_sku()],
            "supplier": _supplier(),
            "forecasts": [_forecast()],
            "open_orders": [],
        },
    )
    result, _ = await execute_tool("get_cash_impact", {"horizon_days": 30}, CTX)

    assert result["open_commitments"] == 120.5
    assert result["recent_spend"] == 300.0
    # at-risk SKU with stock 10, demand 3/day, moq 10 -> needs reorder
    assert result["projected_replenishment"] > 0
    assert "$120.50" in result["summary"]


@pytest.mark.asyncio
async def test_get_forecast_accuracy_uses_outcome_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, {"accuracy_row": (12, 0.18, -0.04)})
    called: dict[str, Any] = {}

    async def fake_summary(since: Any = None, session_factory: Any = None) -> dict[str, Any]:
        called["since"] = since
        return {"count": 8, "mean_error_pct": 12.3}

    monkeypatch.setattr(chat_tools, "calculate_forecast_error_summary", fake_summary)
    result, _ = await execute_tool("get_forecast_accuracy", {"period": "30d"}, CTX)

    assert result["evaluated"] == 12
    assert result["avg_backtest_wmape"] == 0.18
    assert result["outcomes"]["count"] == 8
    assert called["since"] is not None
    assert "avg wMAPE 18.0%" in result["summary"]


@pytest.mark.asyncio
async def test_explain_forecast_without_data_is_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, {"skus": [_sku()], "forecasts": []})
    result, _ = await execute_tool("explain_forecast", {"sku": "WID-1"}, CTX)

    assert result["ok"] is False
    assert "run the pipeline" in result["error"]


@pytest.mark.asyncio
async def test_execute_tool_validation_error_is_reported_not_raised() -> None:
    result, _ = await execute_tool("get_cash_impact", {"horizon_days": "lots"}, CTX)

    assert result["ok"] is False
    assert "Invalid arguments" in result["error"]


@pytest.mark.asyncio
async def test_execute_tool_unknown_name() -> None:
    result, _ = await execute_tool("delete_everything", {}, CTX)

    assert result["ok"] is False
    assert "Unknown tool" in result["error"]


def test_tool_schemas_are_well_formed() -> None:
    for spec in chat_tools.TOOL_SPECS:
        openai = spec.openai_schema()
        assert openai["type"] == "function"
        assert openai["function"]["name"] == spec.name
        assert "properties" in openai["function"]["parameters"]

        gemini = spec.gemini_schema()
        assert gemini["name"] == spec.name
        assert "title" not in gemini.get("parameters", {})


def test_only_draft_purchase_order_is_mutating() -> None:
    mutating = [spec.name for spec in chat_tools.TOOL_SPECS if spec.mutating]
    assert mutating == ["draft_purchase_order"]
