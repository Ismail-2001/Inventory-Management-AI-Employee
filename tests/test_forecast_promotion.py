"""Forecast engine promotion: resolution, gates, circuit breaker, admin API."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import api.routes.forecast_engine as fe_route
import api.routes.run_sync as run_sync_module
from agent import forecast_engine as fe
from agent.forecast_engine import (
    ENGINE_ENSEMBLE,
    ENGINE_EXPONENTIAL,
    ENGINE_SHADOW,
    GateCheck,
    MerchantHoldoutSummary,
    PromotionEvaluation,
    build_gates,
    evaluate_sku_holdout,
    in_rollout_cohort,
    resolve_engine,
    summarize_holdout,
)
from agent.models import Merchant
from agent.nodes import forecast_node as fn
from shared.metrics import metrics

START = date(2026, 1, 1)


def _series(values: list[float]) -> list[tuple[date, float]]:
    return [(START + timedelta(days=i), float(v)) for i, v in enumerate(values)]


TREND = [10 + 0.5 * i for i in range(60)]  # ensemble clearly beats v1 (ratio ~0.46)
CONSTANT = [5.0] * 60  # v1 MAPE is 0 — nothing to prove
STEP = [5.0] * 46 + [25.0] * 14  # both engines miss — gates must fail


def _metric_value(name_and_labels: str) -> float:
    prefix = name_and_labels + " "
    for line in metrics.render().splitlines():
        if line.startswith(prefix):
            return float(line[len(prefix) :])
    return 0.0


def _request(method: str = "GET") -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": "/api/v1/forecast-engine",
        "headers": [],
        "query_string": b"",
        "app": SimpleNamespace(state=SimpleNamespace()),
    }
    return Request(scope, receive=lambda: None, send=lambda msg: None)


def _good_summary() -> MerchantHoldoutSummary:
    return MerchantHoldoutSummary(
        evaluable_skus=3,
        total_skus=3,
        mape_ensemble=0.05,
        mape_v1=0.10,
        mape_ratio=0.5,
        bias_high_velocity=-0.02,
        coverage_p50=0.6,
        high_velocity_skus=2,
    )


# ---------------------------------------------------------------------------
# Engine resolution (override > merchant > default) + rollout cohort
# ---------------------------------------------------------------------------


def test_canonical_engine_aliases_and_junk():
    assert fe.canonical_engine("exp_smoothing_v1") == ENGINE_EXPONENTIAL
    assert fe.canonical_engine("ensemble_v2") == ENGINE_ENSEMBLE
    assert fe.canonical_engine(" SHADOW ") == ENGINE_SHADOW
    assert fe.canonical_engine("prophet") is None
    assert fe.canonical_engine("") is None
    assert fe.canonical_engine(None) is None


def test_resolve_engine_precedence(monkeypatch):
    monkeypatch.setattr(fe.settings, "forecast_engine_override", "")
    monkeypatch.setattr(fe.settings, "forecast_engine_default", "ensemble")

    assert resolve_engine(merchant_engine="shadow", merchant_id=1) == ("shadow", "merchant")
    assert resolve_engine(merchant_engine=None, merchant_id=1) == ("ensemble", "default")

    monkeypatch.setattr(fe.settings, "forecast_engine_override", "exponential")
    assert resolve_engine(merchant_engine="shadow", merchant_id=1) == ("exponential", "global_override")

    # Invalid override is ignored rather than forcing a bad engine.
    monkeypatch.setattr(fe.settings, "forecast_engine_override", "bogus")
    assert resolve_engine(merchant_engine="shadow", merchant_id=1) == ("shadow", "merchant")

    # Invalid everything → shadow (safe serve-legacy fallback), never ensemble.
    monkeypatch.setattr(fe.settings, "forecast_engine_override", "bogus")
    monkeypatch.setattr(fe.settings, "forecast_engine_default", "bogus")
    assert resolve_engine(merchant_engine="also-bogus", merchant_id=1) == ("shadow", "fallback")

    # Legacy stored values are canonicalized.
    monkeypatch.setattr(fe.settings, "forecast_engine_override", "")
    monkeypatch.setattr(fe.settings, "forecast_engine_default", "ensemble")
    assert resolve_engine(merchant_engine="ensemble_v2", merchant_id=1) == ("ensemble", "merchant")
    assert resolve_engine(merchant_engine="exp_smoothing_v1", merchant_id=1) == ("exponential", "merchant")


def test_resolve_engine_flag_defaults(monkeypatch):
    monkeypatch.setattr(fe.settings, "forecast_engine_override", "")
    monkeypatch.setattr(fe.settings, "forecast_engine_default", "ensemble")
    assert fe.canonical_engine(fe.settings.forecast_engine_default) == ENGINE_ENSEMBLE
    # Default invalid → shadow fallback.
    monkeypatch.setattr(fe.settings, "forecast_engine_default", "nope")
    assert resolve_engine(merchant_engine=None, merchant_id=1) == ("shadow", "fallback")


def test_in_rollout_cohort(monkeypatch):
    monkeypatch.setattr(fe.settings, "forecast_rollout_percent", 100)
    assert in_rollout_cohort(123) is True

    monkeypatch.setattr(fe.settings, "forecast_rollout_percent", 0)
    assert in_rollout_cohort(123) is False
    assert in_rollout_cohort(None) is False

    monkeypatch.setattr(fe.settings, "forecast_rollout_percent", 50)
    assert in_rollout_cohort(7) is True  # 7 % 100 = 7 < 50
    assert in_rollout_cohort(107) is True  # wraps: 7 < 50
    assert in_rollout_cohort(50) is False  # boundary: not strictly below
    assert in_rollout_cohort(99) is False  # 99 >= 50
    assert in_rollout_cohort(150) is False  # 50 after wrap-around


# ---------------------------------------------------------------------------
# Hold-out evaluation (pure)
# ---------------------------------------------------------------------------


def test_evaluate_sku_holdout_insufficient_history():
    m = evaluate_sku_holdout(_series([4.0] * 20), holdout=14, sku_id=1)
    assert m.evaluable is False
    assert m.reason == "insufficient_history"


def test_evaluate_sku_holdout_no_positive_demand():
    m = evaluate_sku_holdout(_series([0.0] * 60), holdout=14, sku_id=2)
    assert m.evaluable is False
    assert m.reason == "no_positive_demand"


def test_evaluate_sku_holdout_trend_beats_v1():
    m = evaluate_sku_holdout(_series(TREND), holdout=14, sku_id=3)
    assert m.evaluable is True
    assert m.positive_days == 14
    assert m.mape_ensemble < m.mape_v1
    assert m.mape_ensemble / m.mape_v1 < 0.85
    assert abs(m.bias_ensemble) <= 0.08
    assert m.coverage_p50 >= 0.45


def test_summarize_constant_series_has_no_mape_ratio():
    summary = summarize_holdout([evaluate_sku_holdout(_series(CONSTANT), sku_id=i) for i in range(3)])
    assert summary.evaluable_skus == 3
    assert summary.mape_ratio is None  # exponential MAPE is 0 — no proof possible


def test_summarize_step_series_fails_gates():
    summary = summarize_holdout([evaluate_sku_holdout(_series(STEP), sku_id=i) for i in range(3)])
    gates = build_gates(20, summary)
    failed = {g.name for g in gates if not g.passed}
    assert "mape_ratio" in failed
    assert "high_velocity_bias" in failed
    assert "p50_coverage" in failed


# ---------------------------------------------------------------------------
# Safety gates (pure)
# ---------------------------------------------------------------------------


def test_gates_pass_for_improving_trend_history():
    summary = summarize_holdout([evaluate_sku_holdout(_series(TREND), sku_id=i) for i in range(3)])
    gates = build_gates(20, summary)
    assert {g.name for g in gates} == {
        "shadow_days",
        "min_evaluable_skus",
        "mape_ratio",
        "high_velocity_bias",
        "p50_coverage",
    }
    assert all(g.passed for g in gates)


def test_gate_shadow_days_fails_below_minimum():
    gates = build_gates(13, _good_summary())
    failed = {g.name for g in gates if not g.passed}
    assert failed == {"shadow_days"}


def test_gate_min_evaluable_skus_fails():
    summary = MerchantHoldoutSummary(
        evaluable_skus=2,
        total_skus=9,
        mape_ensemble=0.05,
        mape_v1=0.10,
        mape_ratio=0.5,
        bias_high_velocity=None,
        coverage_p50=0.6,
        high_velocity_skus=0,
    )
    gates = build_gates(20, summary)
    failed = {g.name for g in gates if not g.passed}
    assert failed == {"min_evaluable_skus"}


def test_gate_mape_ratio_fails_without_comparable_v1():
    summary = MerchantHoldoutSummary(
        evaluable_skus=3,
        total_skus=3,
        mape_ensemble=0.0,
        mape_v1=0.0,
        mape_ratio=None,
        bias_high_velocity=None,
        coverage_p50=1.0,
        high_velocity_skus=0,
    )
    gates = build_gates(20, summary)
    failed = {g.name for g in gates if not g.passed}
    assert failed == {"mape_ratio"}


def test_gate_mape_ratio_fails_when_ensemble_worse():
    summary = MerchantHoldoutSummary(
        evaluable_skus=3,
        total_skus=3,
        mape_ensemble=0.30,
        mape_v1=0.10,
        mape_ratio=3.0,
        bias_high_velocity=0.0,
        coverage_p50=0.6,
        high_velocity_skus=2,
    )
    gates = build_gates(20, summary)
    assert [g.name for g in gates if not g.passed] == ["mape_ratio"]


def test_gate_bias_fails_when_too_negative():
    summary = MerchantHoldoutSummary(
        evaluable_skus=3,
        total_skus=3,
        mape_ensemble=0.05,
        mape_v1=0.10,
        mape_ratio=0.5,
        bias_high_velocity=-0.5,
        coverage_p50=0.6,
        high_velocity_skus=2,
    )
    gates = build_gates(20, summary)
    assert [g.name for g in gates if not g.passed] == ["high_velocity_bias"]


def test_gate_bias_vacuous_pass_without_high_velocity():
    summary = MerchantHoldoutSummary(
        evaluable_skus=3,
        total_skus=3,
        mape_ensemble=0.05,
        mape_v1=0.10,
        mape_ratio=0.5,
        bias_high_velocity=None,
        coverage_p50=0.6,
        high_velocity_skus=0,
    )
    gates = build_gates(20, summary)
    assert all(g.passed for g in gates)
    bias_gate = next(g for g in gates if g.name == "high_velocity_bias")
    assert bias_gate.value is None  # documented vacuous pass


def test_gate_coverage_fails_below_minimum():
    summary = MerchantHoldoutSummary(
        evaluable_skus=3,
        total_skus=3,
        mape_ensemble=0.05,
        mape_v1=0.10,
        mape_ratio=0.5,
        bias_high_velocity=-0.02,
        coverage_p50=0.1,
        high_velocity_skus=2,
    )
    gates = build_gates(20, summary)
    assert [g.name for g in gates if not g.passed] == ["p50_coverage"]


# ---------------------------------------------------------------------------
# evaluate_merchant (DB loaders monkeypatched)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_merchant_builds_passing_evaluation(monkeypatch):
    async def fake_metrics(merchant_id: int, holdout: int = 14):
        return [evaluate_sku_holdout(_series(TREND), holdout=holdout, sku_id=i) for i in range(1, 4)]

    async def fake_shadow_days(merchant_id: int) -> int:
        return 20

    monkeypatch.setattr(fe, "load_merchant_holdout_metrics", fake_metrics)
    monkeypatch.setattr(fe, "count_shadow_days", fake_shadow_days)

    evaluation = await fe.evaluate_merchant(5, engine_before=ENGINE_SHADOW, cohort=True)
    assert evaluation.gates_passed is True
    assert evaluation.mape_ratio is not None and evaluation.mape_ratio < 0.85
    assert evaluation.promoted is False  # evaluate alone never flips
    payload = evaluation.to_dict()
    assert payload["shadow_days"] == 20
    assert len(payload["gates"]) == 5
    assert payload["blocked_by"] == []


@pytest.mark.asyncio
async def test_evaluate_merchant_fails_when_shadow_days_low(monkeypatch):
    async def fake_metrics(merchant_id: int, holdout: int = 14):
        return [evaluate_sku_holdout(_series(TREND), holdout=holdout, sku_id=i) for i in range(1, 4)]

    monkeypatch.setattr(fe, "load_merchant_holdout_metrics", fake_metrics)
    monkeypatch.setattr(fe, "count_shadow_days", AsyncMock(return_value=3))

    evaluation = await fe.evaluate_merchant(5)
    assert evaluation.gates_passed is False
    assert evaluation.blocked_by == ["shadow_days"]


# ---------------------------------------------------------------------------
# auto_promote_merchants
# ---------------------------------------------------------------------------


class _ScalarResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return self._items


class _PromoSession:
    def __init__(self, merchants, flip_row=None):
        self.merchants = merchants
        self.flip_row = flip_row
        self.get_calls: list[int] = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, stmt):
        return _ScalarResult(self.merchants)

    async def get(self, model, pk):
        self.get_calls.append(pk)
        return self.flip_row

    async def commit(self):
        self.committed = True


def _passing_evaluation(mid: int, engine_before: str, cohort: bool) -> PromotionEvaluation:
    summary = MerchantHoldoutSummary(
        evaluable_skus=3,
        total_skus=3,
        mape_ensemble=0.05,
        mape_v1=0.10,
        mape_ratio=0.5,
        bias_high_velocity=-0.02,
        coverage_p50=0.6,
        high_velocity_skus=2,
    )
    gates = [GateCheck("shadow_days", True, 20.0, 14.0), GateCheck("mape_ratio", True, 0.5, 0.85)]
    return PromotionEvaluation(mid, engine_before, gates, 20, summary, cohort)


def _failing_evaluation(mid: int, engine_before: str, cohort: bool) -> PromotionEvaluation:
    summary = MerchantHoldoutSummary(
        evaluable_skus=3,
        total_skus=3,
        mape_ensemble=0.30,
        mape_v1=0.10,
        mape_ratio=3.0,
        bias_high_velocity=0.0,
        coverage_p50=0.6,
        high_velocity_skus=2,
    )
    gates = [GateCheck("mape_ratio", False, 3.0, 0.85)]
    return PromotionEvaluation(mid, engine_before, gates, 20, summary, cohort)


@pytest.mark.asyncio
async def test_auto_promote_flips_passing_shadow_merchant(monkeypatch):
    merchants = [
        SimpleNamespace(id=5, forecast_engine=ENGINE_SHADOW),
        SimpleNamespace(id=0, forecast_engine=ENGINE_SHADOW),  # demo — never touched
    ]
    flip_row = SimpleNamespace(id=5, forecast_engine=ENGINE_SHADOW, forecast_promoted_at=None)
    session = _PromoSession(merchants, flip_row=flip_row)
    monkeypatch.setattr(fe, "async_session_factory", lambda: session)
    monkeypatch.setattr(fe, "evaluate_merchant", AsyncMock(side_effect=_passing_evaluation))
    log_mock = AsyncMock()
    monkeypatch.setattr("agent.audit.log", log_mock)

    evaluations = await fe.auto_promote_merchants()

    assert [e.merchant_id for e in evaluations] == [5]  # demo merchant skipped
    assert evaluations[0].promoted is True
    assert flip_row.forecast_engine == ENGINE_ENSEMBLE
    assert flip_row.forecast_promoted_at is not None
    assert session.get_calls == [5]
    assert session.committed is True
    log_mock.assert_awaited_once()
    assert log_mock.call_args.kwargs["action"] == "forecast_engine_promoted"
    assert log_mock.call_args.kwargs["details"]["merchant_id"] == 5
    assert _metric_value('forecast_promotion_status{engine="ensemble",merchant="5"}') == 1.0
    assert _metric_value('forecast_mape_ratio{merchant="5"}') == 0.5
    assert _metric_value('forecast_promotion_gate_pass{merchant="5"}') == 1.0


@pytest.mark.asyncio
async def test_auto_promote_skips_merchant_when_gates_fail(monkeypatch):
    merchants = [SimpleNamespace(id=6, forecast_engine=ENGINE_SHADOW)]
    session = _PromoSession(merchants, flip_row=SimpleNamespace(id=6, forecast_engine=ENGINE_SHADOW))
    monkeypatch.setattr(fe, "async_session_factory", lambda: session)
    monkeypatch.setattr(fe, "evaluate_merchant", AsyncMock(side_effect=_failing_evaluation))
    log_mock = AsyncMock()
    monkeypatch.setattr("agent.audit.log", log_mock)

    evaluations = await fe.auto_promote_merchants()

    assert len(evaluations) == 1
    assert evaluations[0].promoted is False
    assert session.get_calls == []  # no flip attempted
    assert session.committed is False
    log_mock.assert_not_awaited()
    assert _metric_value('forecast_promotion_status{engine="shadow",merchant="6"}') == 1.0
    assert _metric_value('forecast_promotion_gate_pass{merchant="6"}') == 0.0


@pytest.mark.asyncio
async def test_auto_promote_respects_rollout_cohort(monkeypatch):
    monkeypatch.setattr(fe.settings, "forecast_rollout_percent", 0)
    merchants = [SimpleNamespace(id=7, forecast_engine=ENGINE_SHADOW)]
    session = _PromoSession(merchants, flip_row=SimpleNamespace(id=7, forecast_engine=ENGINE_SHADOW))
    monkeypatch.setattr(fe, "async_session_factory", lambda: session)
    monkeypatch.setattr(fe, "evaluate_merchant", AsyncMock(side_effect=_passing_evaluation))
    log_mock = AsyncMock()
    monkeypatch.setattr("agent.audit.log", log_mock)

    evaluations = await fe.auto_promote_merchants()

    assert evaluations[0].gates_passed is True
    assert evaluations[0].cohort is False
    assert evaluations[0].promoted is False
    assert session.get_calls == []
    log_mock.assert_not_awaited()


# ---------------------------------------------------------------------------
# Weekly report
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_weekly_report_empty(monkeypatch):
    session = _PromoSession([])
    monkeypatch.setattr(fe, "async_session_factory", lambda: session)

    report = await fe.build_weekly_engine_report(date(2026, 9, 21))
    assert report["week_start"] == "2026-09-21"
    assert report["week_end"] == "2026-09-28"
    assert report["merchants"] == []


@pytest.mark.asyncio
async def test_send_weekly_report_logs_and_returns(monkeypatch):
    expected = {"week_start": "2026-09-21", "week_end": "2026-09-28", "merchants": []}
    monkeypatch.setattr(fe, "build_weekly_engine_report", AsyncMock(return_value=expected))
    monkeypatch.setattr(fe.settings, "slack_webhook_url", "")
    log_mock = AsyncMock()
    monkeypatch.setattr("agent.audit.log", log_mock)

    report = await fe.send_weekly_engine_report(date(2026, 9, 21))
    assert report == expected
    log_mock.assert_awaited_once()
    assert log_mock.call_args.kwargs["action"] == "weekly_forecast_engine_report"


# ---------------------------------------------------------------------------
# forecast_node: engine selection + circuit breaker
# ---------------------------------------------------------------------------


def _fr(sku_id: int, engine: str) -> fn.ForecastResult:
    return fn.ForecastResult(
        sku_id=sku_id,
        predicted_daily_demand=2.0,
        days_of_stock_remaining=5.0,
        model_version="ensemble_v2" if engine == ENGINE_ENSEMBLE else "exp_smoothing_v1",
    )


@pytest.mark.asyncio
async def test_forecast_node_uses_engine_from_state(monkeypatch):
    seen: list[str | None] = []

    async def fake_calc(sku_id, current_stock, lead_time_days, engine=None, **kwargs):
        seen.append(engine)
        return _fr(sku_id, engine or ENGINE_EXPONENTIAL)

    monkeypatch.setattr(fn, "calculate_forecast", fake_calc)
    state = {"skus": [{"id": 988001, "current_stock": 10, "lead_time_days": 7}], "forecast_engine": ENGINE_EXPONENTIAL}
    result = await fn.forecast_node(state)

    assert seen == [ENGINE_EXPONENTIAL]
    assert result["forecast_engine"] == ENGINE_EXPONENTIAL
    assert result["forecast_circuit_tripped"] is False


@pytest.mark.asyncio
async def test_forecast_node_falls_back_to_settings_mode(monkeypatch):
    monkeypatch.setattr(fn.settings, "forecast_model_version", "shadow")
    seen: list[str | None] = []

    async def fake_calc(sku_id, current_stock, lead_time_days, engine=None, **kwargs):
        seen.append(engine)
        return _fr(sku_id, ENGINE_SHADOW)

    monkeypatch.setattr(fn, "calculate_forecast", fake_calc)
    state = {"skus": [{"id": 988002, "current_stock": 10, "lead_time_days": 7}]}
    result = await fn.forecast_node(state)

    assert seen == [ENGINE_SHADOW]
    assert result["forecast_engine"] == ENGINE_SHADOW


@pytest.mark.asyncio
async def test_circuit_breaker_trips_and_reruns_exponential(monkeypatch):
    """15/20 SKUs failing ensemble (75% > 5%) → whole run rerun on exponential."""
    calls: list[tuple[int, str | None]] = []

    async def fake_calc(sku_id, current_stock, lead_time_days, engine=None, **kwargs):
        calls.append((sku_id, engine))
        result = _fr(sku_id, engine or ENGINE_EXPONENTIAL)
        if engine == ENGINE_ENSEMBLE:
            result.fallback_used = True  # ensemble blew up for every SKU
        return result

    monkeypatch.setattr(fn, "calculate_forecast", fake_calc)
    skus = [{"id": 986001 + i, "current_stock": 10, "lead_time_days": 7} for i in range(20)]
    state = {"skus": skus, "forecast_engine": ENGINE_ENSEMBLE, "merchant_id": 7}

    breaker_before = _metric_value('forecast_fallback_count{reason="circuit_breaker"}')
    ensemble_used_before = _metric_value('forecast_engine_used{engine="ensemble",merchant="7"}')
    exponential_used_before = _metric_value('forecast_engine_used{engine="exponential",merchant="7"}')

    result = await fn.forecast_node(state)

    assert result["forecast_circuit_tripped"] is True
    assert result["forecast_engine"] == ENGINE_EXPONENTIAL  # effective engine recorded
    assert len(result["forecasts"]) == 20
    assert all(f["model_version"] == "exp_smoothing_v1" for f in result["forecasts"])

    ensemble_calls = [sku for sku, e in calls if e == ENGINE_ENSEMBLE]
    exponential_calls = [sku for sku, e in calls if e == ENGINE_EXPONENTIAL]
    assert sorted(ensemble_calls) == sorted(s["id"] for s in skus)  # first pass: all 20
    assert sorted(exponential_calls) == sorted(s["id"] for s in skus)  # rerun: all 20

    assert _metric_value('forecast_fallback_count{reason="circuit_breaker"}') > breaker_before
    assert _metric_value('forecast_engine_used{engine="exponential",merchant="7"}') > exponential_used_before
    assert _metric_value('forecast_engine_used{engine="ensemble",merchant="7"}') == ensemble_used_before


@pytest.mark.asyncio
async def test_circuit_breaker_holds_at_threshold(monkeypatch):
    """1/20 SKUs failing (exactly 5%) must NOT trip — threshold is strictly greater."""
    calls: list[tuple[int, str | None]] = []

    async def fake_calc(sku_id, current_stock, lead_time_days, engine=None, **kwargs):
        calls.append((sku_id, engine))
        result = _fr(sku_id, engine or ENGINE_EXPONENTIAL)
        if engine == ENGINE_ENSEMBLE and sku_id == 987001:
            result.fallback_used = True
        return result

    monkeypatch.setattr(fn, "calculate_forecast", fake_calc)
    skus = [{"id": 987001 + i, "current_stock": 10, "lead_time_days": 7} for i in range(20)]
    state = {"skus": skus, "forecast_engine": ENGINE_ENSEMBLE, "merchant_id": 8}

    breaker_before = _metric_value('forecast_fallback_count{reason="circuit_breaker"}')

    result = await fn.forecast_node(state)

    assert result["forecast_circuit_tripped"] is False
    assert result["forecast_engine"] == ENGINE_ENSEMBLE
    assert all(f["model_version"] == "ensemble_v2" for f in result["forecasts"] if f["sku_id"] != 987001)
    exponential_calls = [sku for sku, e in calls if e == ENGINE_EXPONENTIAL]
    assert exponential_calls == []  # no rerun happened
    assert _metric_value('forecast_fallback_count{reason="circuit_breaker"}') == breaker_before
    assert _metric_value('forecast_engine_used{engine="ensemble",merchant="8"}') > 0


@pytest.mark.asyncio
async def test_circuit_breaker_counts_timeouts(monkeypatch):
    """Timeouts count as failures: 3/10 (30% > 5%) trips the breaker."""
    calls: list[str | None] = []

    async def fake_calc(sku_id, current_stock, lead_time_days, engine=None, **kwargs):
        calls.append(engine)
        if engine == ENGINE_ENSEMBLE and sku_id in (989001, 989002, 989003):
            raise TimeoutError()
        return _fr(sku_id, engine or ENGINE_EXPONENTIAL)

    monkeypatch.setattr(fn, "calculate_forecast", fake_calc)
    skus = [{"id": 989001 + i, "current_stock": 10, "lead_time_days": 7} for i in range(10)]
    state = {"skus": skus, "forecast_engine": ENGINE_ENSEMBLE, "merchant_id": 9}

    timeout_before = _metric_value("forecast_timeout_total")

    result = await fn.forecast_node(state)

    assert result["forecast_circuit_tripped"] is True
    assert result["forecast_engine"] == ENGINE_EXPONENTIAL
    assert len(result["forecasts"]) == 10  # exponential rerun replaced the gaps
    assert calls.count(ENGINE_ENSEMBLE) == 10
    assert calls.count(ENGINE_EXPONENTIAL) == 10
    assert _metric_value("forecast_timeout_total") == timeout_before + 3


# ---------------------------------------------------------------------------
# run_sync engine resolution
# ---------------------------------------------------------------------------


def test_initial_state_resolves_default_engine():
    merchant = SimpleNamespace(id=1)  # no forecast_engine attr (legacy fixtures)
    state = run_sync_module._initial_state(merchant, "thread-1")
    assert state == {"merchant_id": 1, "thread_id": "thread-1", "forecast_engine": "shadow"}


def test_initial_state_prefers_merchant_flag():
    merchant = SimpleNamespace(id=1, forecast_engine="shadow")
    state = run_sync_module._initial_state(merchant, "thread-2")
    assert state["forecast_engine"] == "shadow"


def test_initial_state_override_wins(monkeypatch):
    monkeypatch.setattr(fe.settings, "forecast_engine_override", "exponential")
    merchant = SimpleNamespace(id=1, forecast_engine="shadow")
    state = run_sync_module._initial_state(merchant, "thread-3")
    assert state["forecast_engine"] == "exponential"


# ---------------------------------------------------------------------------
# Admin endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_engine_reports_stored_and_active(monkeypatch):
    monkeypatch.setattr(fe_route.limiter, "enabled", False)
    merchant = SimpleNamespace(id=1, forecast_engine="shadow")
    payload = await fe_route.get_forecast_engine(_request(), evaluate=False, merchant=merchant)

    assert payload["stored_engine"] == "shadow"
    assert payload["active_engine"] == "shadow"
    assert payload["source"] == "merchant"
    assert payload["default_engine"] == "shadow"
    assert payload["valid_engines"] == [ENGINE_ENSEMBLE, ENGINE_EXPONENTIAL, ENGINE_SHADOW]
    assert "evaluation" not in payload


@pytest.mark.asyncio
async def test_get_engine_evaluate_runs_gates(monkeypatch):
    monkeypatch.setattr(fe_route.limiter, "enabled", False)
    merchant = SimpleNamespace(id=1, forecast_engine="shadow")
    fake_evaluation = _passing_evaluation(1, ENGINE_SHADOW, cohort=True)
    fake_evaluation.promoted = False
    monkeypatch.setattr(fe_route, "evaluate_merchant", AsyncMock(return_value=fake_evaluation))

    payload = await fe_route.get_forecast_engine(_request(), evaluate=True, merchant=merchant)
    assert payload["evaluation"]["gates_passed"] is True
    assert len(payload["evaluation"]["gates"]) == 2


@pytest.mark.asyncio
async def test_get_engine_evaluate_rejects_demo_merchant(monkeypatch):
    monkeypatch.setattr(fe_route.limiter, "enabled", False)
    merchant = SimpleNamespace(id=0, forecast_engine="shadow")
    with pytest.raises(HTTPException) as exc:
        await fe_route.get_forecast_engine(_request(), evaluate=True, merchant=merchant)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_post_engine_rejects_unknown_engine(monkeypatch):
    monkeypatch.setattr(fe_route.limiter, "enabled", False)
    merchant = SimpleNamespace(id=1, forecast_engine="shadow")
    with pytest.raises(HTTPException) as exc:
        await fe_route.set_forecast_engine(
            _request("POST"), fe_route.EngineUpdateRequest(engine="prophet"), merchant=merchant
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_post_engine_rejects_demo_merchant(monkeypatch):
    monkeypatch.setattr(fe_route.limiter, "enabled", False)
    merchant = SimpleNamespace(id=0, forecast_engine="shadow")
    with pytest.raises(HTTPException) as exc:
        await fe_route.set_forecast_engine(
            _request("POST"), fe_route.EngineUpdateRequest(engine="ensemble"), merchant=merchant
        )
    assert exc.value.status_code == 400


class _MerchantSession:
    def __init__(self, row):
        self.row = row
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, model, pk):
        assert model is Merchant
        return self.row

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_post_engine_promotes_and_audits(monkeypatch):
    monkeypatch.setattr(fe_route.limiter, "enabled", False)
    row = SimpleNamespace(id=5, forecast_engine="shadow", forecast_promoted_at=None)
    session = _MerchantSession(row)
    monkeypatch.setattr(fe_route, "async_session_factory", lambda: session)
    log_mock = AsyncMock()
    monkeypatch.setattr(fe_route, "log", log_mock)

    merchant = SimpleNamespace(id=5, forecast_engine="shadow")
    payload = await fe_route.set_forecast_engine(
        _request("POST"), fe_route.EngineUpdateRequest(engine="ensemble_v2"), merchant=merchant
    )

    assert payload == {"status": "ok", "merchant_id": 5, "engine": "ensemble"}
    assert row.forecast_engine == "ensemble"
    assert row.forecast_promoted_at is not None
    assert session.committed is True
    log_mock.assert_awaited_once()
    assert log_mock.call_args.kwargs["action"] == "forecast_engine_change"
    assert _metric_value('forecast_promotion_status{engine="ensemble",merchant="5"}') == 1.0
    assert _metric_value('forecast_promotion_status{engine="shadow",merchant="5"}') == 0.0


@pytest.mark.asyncio
async def test_post_engine_demote_clears_promoted_at(monkeypatch):
    monkeypatch.setattr(fe_route.limiter, "enabled", False)
    row = SimpleNamespace(id=6, forecast_engine="ensemble", forecast_promoted_at=datetime.now(UTC))
    session = _MerchantSession(row)
    monkeypatch.setattr(fe_route, "async_session_factory", lambda: session)
    monkeypatch.setattr(fe_route, "log", AsyncMock())

    merchant = SimpleNamespace(id=6, forecast_engine="ensemble")
    payload = await fe_route.set_forecast_engine(
        _request("POST"), fe_route.EngineUpdateRequest(engine="exponential"), merchant=merchant
    )

    assert payload["engine"] == "exponential"
    assert row.forecast_engine == "exponential"
    assert row.forecast_promoted_at is None


# ---------------------------------------------------------------------------
# Merchant model defaults
# ---------------------------------------------------------------------------


def test_merchant_forecast_engine_column_defaults_to_shadow():
    column = Merchant.__table__.c.forecast_engine
    assert column.default is not None
    assert column.default.arg == "shadow"
    assert column.server_default is not None
    assert column.server_default.arg == "shadow"
    assert column.nullable is False
