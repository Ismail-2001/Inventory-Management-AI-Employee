"""ROI dashboard tests: critical aggregations, report assembly, route validation."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import api.routes.roi as roi_route
from agent import roi
from agent.config import settings
from agent.models import POStatus

SINCE = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
UNTIL = datetime(2026, 10, 1, 0, 0, tzinfo=UTC)


class FakeResult:
    def __init__(self, items: list[Any] | None = None, one_row: Any = None) -> None:
        self._items = items or []
        self._one = one_row

    def all(self) -> list[Any]:
        return self._items

    def scalars(self) -> FakeResult:
        return self

    def one(self) -> Any:
        return self._one


class FakeSession:
    """Dispatches queries by the table name rendered in the SQL text."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data

    async def execute(self, stmt: Any) -> FakeResult:
        text = str(stmt).lower()
        if "from po_outcomes" in text:
            if "avg(" in text:
                return FakeResult(one_row=self.data.get("outcome_agg", (0, None)))
            return FakeResult(items=self.data.get("outcomes", []))
        if "from audit_log" in text:
            return FakeResult(items=self.data.get("audits", []))
        if "from risk_alerts" in text:
            return FakeResult(items=self.data.get("alerts", []))
        if "from forecasts" in text:
            return FakeResult(items=self.data.get("forecasts", []))
        if "from llm_usage" in text:
            return FakeResult(one_row=self.data.get("usage_row", (0, 0, 0, 0.0)))
        if "from chat_messages" in text:
            return FakeResult(one_row=self.data.get("chat_row", (0, 0, 0, 0.0)))
        if "from purchase_orders" in text:
            return FakeResult(items=self.data.get("pos", []))
        return FakeResult(items=[])

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


def _factory(data: dict[str, Any]) -> Any:
    return lambda: FakeSession(data)


def _po(
    po_id: int = 1,
    status: POStatus = POStatus.approved,
    qty: int = 100,
    unit: float = 5.0,
    total: float = 0.0,
    created: datetime | None = None,
    approved_at: datetime | None = None,
    edited: bool = False,
    original: int | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=po_id,
        status=status,
        quantity=qty,
        unit_cost=unit,
        total_cost=total,
        created_at=created or (SINCE + timedelta(hours=1)),
        approved_at=approved_at,
        edited_before_approval=edited,
        original_quantity=original,
        merchant_id=None,
    )


def _outcome(prevented: bool, stockout: bool) -> SimpleNamespace:
    return SimpleNamespace(
        po_id=1,
        expected_stockout_prevented=prevented,
        actual_stockout_occurred=stockout,
        forecast_error_pct=10.0,
    )


def _forecast(
    model: str = "ensemble_v2",
    wmape: float | None = None,
    bias: float | None = None,
    p10: float | None = None,
    p50: float = 10.0,
    p90: float | None = None,
    meta: dict[str, Any] | None = None,
    sku_id: int = 1,
    created: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        model_version=model,
        backtest_wmape=wmape,
        backtest_bias=bias,
        p10_daily_demand=p10,
        p90_daily_demand=p90,
        predicted_daily_demand=p50,
        model_meta=meta,
        sku_id=sku_id,
        created_at=created or (SINCE + timedelta(hours=5)),
    )


def _audit(po_id: int, action: str = "po.approve", created: datetime | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        target_id=str(po_id),
        action=action,
        created_at=created or (SINCE + timedelta(hours=3)),
        merchant_id=None,
    )


async def test_stockouts_avoided_counts_only_prevented_without_actual_stockout() -> None:
    data = {
        "outcomes": [
            (_outcome(True, False), _po(qty=100, unit=5.0)),
            (_outcome(True, True), _po(qty=50, unit=5.0)),
            (_outcome(False, False), _po(qty=30, unit=5.0)),
        ]
    }
    result = await roi.calculate_stockouts_avoided(
        0, SINCE, UNTIL, revenue_multiplier=2.0, session_factory=_factory(data)
    )
    assert result == {"events": 1, "units": 100, "revenue_protected_usd": 1000.0}


async def test_stockouts_avoided_empty_window() -> None:
    result = await roi.calculate_stockouts_avoided(
        0, SINCE, UNTIL, revenue_multiplier=2.0, session_factory=_factory({})
    )
    assert result == {"events": 0, "units": 0, "revenue_protected_usd": 0.0}


async def test_po_decisioning_acceptance_hours_and_excess() -> None:
    t0 = SINCE + timedelta(hours=1)
    data = {
        "pos": [
            _po(1, POStatus.approved, qty=100, unit=5.0, created=t0, approved_at=t0 + timedelta(hours=4)),
            _po(
                2,
                POStatus.approved,
                qty=30,
                unit=10.0,
                created=t0,
                approved_at=t0 + timedelta(hours=4),
                edited=True,
                original=50,
            ),
            _po(3, POStatus.rejected, qty=20, unit=7.0, total=140.0, created=t0),
        ],
        "audits": [
            _audit(1, "po.approve", t0 + timedelta(hours=2)),
            _audit(3, "po.reject", t0 + timedelta(hours=6)),
        ],
    }
    result = await roi.calculate_po_decisioning(0, SINCE, UNTIL, session_factory=_factory(data))

    assert result["decided"] == 3
    assert result["accepted"] == 2
    assert result["rejected"] == 1
    assert result["accepted_as_is"] == 1
    assert result["edited_then_approved"] == 1
    assert result["acceptance_rate_pct"] == 66.7
    # decisions at +2h (audit), +4h (approved_at fallback), +6h (audit)
    assert result["avg_hours_to_decision"] == 4.0
    assert result["decisions_with_timestamp"] == 3
    # excess: 20 units trimmed at $10 + 20 rejected units at $140 total
    assert result["excess_reduction"] == {
        "units": 40,
        "capital_freed_usd": 340.0,
        "trimmed_pos": 1,
        "rejected_pos": 1,
    }


async def test_po_decisioning_empty_window() -> None:
    result = await roi.calculate_po_decisioning(0, SINCE, UNTIL, session_factory=_factory({}))
    assert result["decided"] == 0
    assert result["acceptance_rate_pct"] == 0.0
    assert result["avg_hours_to_decision"] is None
    assert result["excess_reduction"]["units"] == 0


async def test_forecast_accuracy_ensemble_vs_baseline() -> None:
    data = {
        "forecasts": [
            _forecast("ensemble_v2", wmape=0.10, bias=-0.05),
            _forecast("ensemble_v2", wmape=0.20, bias=0.05),
            _forecast("exp_smoothing_v1", wmape=0.30, bias=0.10),
            _forecast("exp_smoothing_v1", wmape=0.50),
            _forecast("exp_smoothing_v1", wmape=None),
        ],
        "outcome_agg": (4, 12.5),
    }
    result = await roi.calculate_forecast_accuracy(0, SINCE, UNTIL, session_factory=_factory(data))

    assert result["ensemble_wmape_pct"] == 15.0
    assert result["ensemble_bias_pct"] == 0.0
    assert result["ensemble_count"] == 2
    assert result["baseline_wmape_pct"] == 40.0
    assert result["baseline_bias_pct"] == 10.0
    assert result["baseline_count"] == 2
    assert result["wmape_improvement_pct"] == 62.5
    assert result["outcome_mape_pct"] == 12.5
    assert result["outcome_count"] == 4
    assert result["series"] == [
        {
            "date": "2026-09-01",
            "ensemble_wmape_pct": 15.0,
            "baseline_wmape_pct": 40.0,
        }
    ]


async def test_forecast_accuracy_empty_window() -> None:
    result = await roi.calculate_forecast_accuracy(0, SINCE, UNTIL, session_factory=_factory({}))
    assert result["ensemble_wmape_pct"] is None
    assert result["baseline_wmape_pct"] is None
    assert result["wmape_improvement_pct"] is None
    assert result["outcome_mape_pct"] is None
    assert result["series"] == []


async def test_llm_usage_sums_pipeline_and_chat() -> None:
    data = {"usage_row": (10, 1000, 500, 0.5), "chat_row": (2, 300, 100, 0.25)}
    result = await roi.calculate_llm_usage(0, SINCE, UNTIL, session_factory=_factory(data))
    assert result["cost_usd"] == 0.75
    assert result["pipeline_cost_usd"] == 0.5
    assert result["chat_cost_usd"] == 0.25
    assert result["calls"] == 12
    assert result["tokens_in"] == 1300
    assert result["tokens_out"] == 600


async def test_at_risk_dedupes_to_latest_alert_per_sku() -> None:
    def _alert(sku_id: int, level: str, created: datetime) -> SimpleNamespace:
        return SimpleNamespace(sku_id=sku_id, risk_level=level, reason=f"{level}!", created_at=created, resolved=False)

    def _sku(sku_id: int, code: str) -> SimpleNamespace:
        return SimpleNamespace(id=sku_id, sku_code=code, title=code, merchant_id=1)

    data = {
        "alerts": [
            (_alert(1, "critical", SINCE), _sku(1, "A")),
            (_alert(1, "warning", SINCE + timedelta(days=1)), _sku(1, "A")),
            (_alert(2, "critical", SINCE), _sku(2, "B")),
        ]
    }
    result = await roi.calculate_at_risk(0, session_factory=_factory(data))
    assert result["total"] == 2
    assert result["critical"] == 1
    assert result["warning"] == 1
    assert [s["sku_code"] for s in result["skus"]] == ["B", "A"]
    assert result["skus"][0]["risk_level"] == "critical"


async def test_forecast_health_coverage_confidence_and_fallback() -> None:
    data = {
        "forecasts": [
            _forecast("ensemble_v2", p10=8, p50=10, p90=12),  # width 0.4 -> tight
            _forecast("ensemble_v2", p10=5, p50=10, p90=15),  # width 1.0 -> typical
            _forecast("ensemble_v2", p10=2, p50=10, p90=20),  # width 1.8 -> wide
            _forecast("exp_smoothing_v1", meta={"fallback_used": True}),
        ]
    }
    result = await roi.calculate_forecast_health(0, SINCE, UNTIL, session_factory=_factory(data))

    confidence = result["forecast_confidence"]
    assert confidence["total_forecasts"] == 4
    assert confidence["with_intervals"] == 3
    assert confidence["coverage_pct"] == 75.0
    assert confidence["distribution"] == [
        {"bucket": "tight", "count": 1},
        {"bucket": "typical", "count": 1},
        {"bucket": "wide", "count": 1},
    ]

    engine = result["engine"]
    assert engine["fallbacks"] == 1
    assert engine["fallback_rate_pct"] == 25.0
    assert {"model": "ensemble_v2", "count": 3} in engine["distribution"]
    assert {"model": "exp_smoothing_v1", "count": 1} in engine["distribution"]


async def test_roi_report_assembles_value_cost_and_roi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "roi_manual_po_minutes", 12.0)
    monkeypatch.setattr(settings, "roi_revenue_multiplier", 2.0)

    t0 = SINCE + timedelta(hours=1)
    data = {
        "outcomes": [(_outcome(True, False), _po(1, qty=100, unit=5.0))],
        "outcome_agg": (3, 10.0),
        "pos": [
            _po(1, POStatus.approved, qty=100, unit=5.0, created=t0, approved_at=t0 + timedelta(hours=2)),
            _po(2, POStatus.rejected, qty=20, unit=7.0, total=140.0, created=t0),
        ],
        "audits": [
            _audit(1, "po.approve", t0 + timedelta(hours=2)),
            _audit(2, "po.reject", t0 + timedelta(hours=6)),
        ],
        "forecasts": [
            _forecast("ensemble_v2", wmape=0.20, p10=8, p90=12),
            _forecast("exp_smoothing_v1", wmape=0.40, p10=8, p90=12),
        ],
        "usage_row": (5, 100, 50, 0.5),
        "chat_row": (1, 50, 25, 0.25),
        "alerts": [],
    }

    report = await roi.calculate_roi_report(0, date(2026, 9, 1), date(2026, 9, 30), session_factory=_factory(data))

    assert report["period"] == {"start": "2026-09-01", "end": "2026-09-30", "days": 30}

    stockouts = report["operational"]["stockouts_avoided"]
    assert stockouts["units"] == 100
    assert stockouts["revenue_protected_usd"] == 1000.0
    excess = report["operational"]["excess_reduction"]
    assert excess["capital_freed_usd"] == 140.0

    efficiency = report["efficiency"]
    value = 1000.0 + 140.0
    assert efficiency["value_generated_usd"] == value
    assert efficiency["llm"]["cost_usd"] == 0.75
    assert efficiency["roi_multiple"] == round(value / 0.75, 1)
    assert efficiency["hours_saved"] == 0.4  # 2 decided POs x 12 min / 60
    assert efficiency["hours_saved_basis"] == {"decided_pos": 2, "minutes_per_po": 12.0}
    assert efficiency["assumptions"]["revenue_multiplier"] == 2.0

    assert report["health"]["at_risk"]["total"] == 0
    assert report["health"]["forecast_confidence"]["coverage_pct"] == 100.0
    assert report["health"]["engine"]["fallback_rate_pct"] == 0.0


def _request(path: str = "/api/v1/roi", query: bytes = b"") -> Request:
    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query,
        "headers": [(b"x-api-key", b"demo-key-2024")],
        "client": ("127.0.0.1", 4242),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope, receive=receive, send=lambda message: None)


@pytest.fixture
def no_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(roi_route.limiter, "enabled", False)


async def test_roi_route_defaults_to_rolling_30_days(no_rate_limit: None, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_report(merchant_id: int, start: date, end: date, session_factory: Any = None) -> dict[str, Any]:
        captured.update({"merchant_id": merchant_id, "start": start, "end": end})
        return {"period": {"start": start.isoformat(), "end": end.isoformat(), "days": (end - start).days + 1}}

    monkeypatch.setattr(roi_route, "calculate_roi_report", fake_report)
    result = await roi_route.get_roi(_request(), days=None, start=None, end=None, merchant=SimpleNamespace(id=0))

    today = date.today()
    assert captured["merchant_id"] == 0
    assert captured["end"] == today
    assert captured["start"] == today - timedelta(days=29)
    assert result["period"]["days"] == 30


async def test_roi_route_custom_range(no_rate_limit: None, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_report(merchant_id: int, start: date, end: date, session_factory: Any = None) -> dict[str, Any]:
        captured.update({"merchant_id": merchant_id, "start": start, "end": end})
        return {"period": {"days": (end - start).days + 1}}

    monkeypatch.setattr(roi_route, "calculate_roi_report", fake_report)
    result = await roi_route.get_roi(
        _request(),
        days=None,
        start=date(2026, 1, 1),
        end=date(2026, 1, 31),
        merchant=SimpleNamespace(id=7),
    )
    assert captured["merchant_id"] == 7
    assert captured["start"] == date(2026, 1, 1)
    assert captured["end"] == date(2026, 1, 31)
    assert result["period"]["days"] == 31


async def test_roi_route_days_param_sets_window(no_rate_limit: None, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_report(merchant_id: int, start: date, end: date, session_factory: Any = None) -> dict[str, Any]:
        captured.update({"start": start, "end": end})
        return {}

    monkeypatch.setattr(roi_route, "calculate_roi_report", fake_report)
    await roi_route.get_roi(_request(), days=7, start=None, end=None, merchant=SimpleNamespace(id=0))
    assert captured["end"] - captured["start"] == timedelta(days=6)


async def test_roi_route_rejects_incomplete_or_invalid_ranges(no_rate_limit: None) -> None:
    with pytest.raises(HTTPException) as excinfo:
        await roi_route.get_roi(_request(), days=None, start=date(2026, 1, 1), end=None, merchant=SimpleNamespace(id=0))
    assert excinfo.value.status_code == 400

    with pytest.raises(HTTPException) as excinfo:
        await roi_route.get_roi(
            _request(), days=None, start=date(2026, 2, 1), end=date(2026, 1, 1), merchant=SimpleNamespace(id=0)
        )
    assert excinfo.value.status_code == 400

    with pytest.raises(HTTPException) as excinfo:
        await roi_route.get_roi(
            _request(),
            days=None,
            start=date(2024, 1, 1),
            end=date(2025, 1, 2),  # 367 days
            merchant=SimpleNamespace(id=0),
        )
    assert excinfo.value.status_code == 400
