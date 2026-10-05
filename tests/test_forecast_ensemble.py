"""Ensemble v2 forecasting — model math, selection, intervals, fallback, edges."""

from datetime import date, timedelta

import pytest

from agent.forecast import (
    ExternalCandidate,
    build_ensemble,
    confidence_band,
    diagnose,
    exponential_smoothing,
    fit_croston,
    fit_holt,
    fit_mean,
    fit_seasonal,
    fit_ses,
    holdout_days,
    impute_censored_days,
    legacy_predict_daily,
    prepare_series,
    robust_sigma,
    wmape,
)

HORIZON = 30


def _days(n: int, start: date = date(2026, 1, 1)) -> list[date]:
    return [start + timedelta(days=i) for i in range(n)]


def _rows(values: list[float], start: date = date(2026, 1, 1)) -> list[tuple[date, float]]:
    return list(zip(_days(len(values), start), values, strict=False))


def _seasonal_series(n: int, base: float = 10.0, weekly: float = 0.6) -> list[float]:
    pattern = [1.0, 1.0, 1.0, 1.0, 1.0, 1 + weekly, 1 + weekly * 1.2]
    return [round(base * pattern[i % 7] + (i % 3), 2) for i in range(n)]


def _sparse_series(n: int) -> list[float]:
    return [8.0 if i % 7 == 0 else 0.0 for i in range(n)]


def _trend_series(n: int) -> list[float]:
    return [round(5 + 0.15 * i + (i % 4) * 0.4, 2) for i in range(n)]


# ---------------------------------------------------------------------------
# Series preparation & diagnosis
# ---------------------------------------------------------------------------


def test_prepare_series_fills_calendar_gaps():
    rows = [(date(2026, 1, 1), 5.0), (date(2026, 1, 4), 7.0)]
    dates, values = prepare_series(rows)
    assert len(dates) == 4
    assert values == [5.0, 0.0, 0.0, 7.0]


def test_prepare_series_sorts_unsorted_input():
    rows = [(date(2026, 1, 3), 3.0), (date(2026, 1, 1), 1.0), (date(2026, 1, 2), 2.0)]
    _, values = prepare_series(rows)
    assert values == [1.0, 2.0, 3.0]


def test_prepare_series_empty():
    assert prepare_series([]) == ([], [])


def test_diagnose_all_zero_is_intermittent():
    diag = diagnose([0.0] * 50)
    assert diag.zero_share == 1.0
    assert diag.intermittent is True
    assert diag.weekly_seasonality is False


def test_diagnose_sparse_is_intermittent():
    assert diagnose(_sparse_series(70)).intermittent is True


def test_diagnose_dense_is_not_intermittent():
    assert diagnose(_seasonal_series(60)).intermittent is False


def test_diagnose_detects_weekly_seasonality():
    assert diagnose(_seasonal_series(56)).weekly_seasonality is True
    assert diagnose([10.0, 10.0, 9.5, 10.5, 10.0, 9.8, 10.2] * 8).weekly_seasonality is False


def test_diagnose_detects_trend_sign():
    assert diagnose(_trend_series(60)).trend_slope > 0
    assert diagnose(list(reversed(_trend_series(60)))).trend_slope < 0


# ---------------------------------------------------------------------------
# Stockout (censored demand) imputation
# ---------------------------------------------------------------------------


def test_impute_bracketed_zero():
    values = [5.0, 5.0, 5.0, 0.0, 5.0, 5.0, 5.0] * 3
    result, imputed = impute_censored_days(values)
    assert imputed == 3
    assert all(v > 0 for v in result)


def test_impute_leaves_leading_zeros():
    values = [0.0, 0.0, 0.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    result, imputed = impute_censored_days(values)
    assert imputed == 0
    assert result[:3] == [0.0, 0.0, 0.0]


def test_impute_leaves_trailing_zeros():
    values = [5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 0.0, 0.0, 0.0]
    result, imputed = impute_censored_days(values)
    assert imputed == 0


def test_impute_all_zero_untouched():
    values = [0.0] * 30
    result, imputed = impute_censored_days(values)
    assert imputed == 0
    assert result == values


def test_impute_sparse_neighbor_untouched():
    values = [0.0] * 10 + [5.0] + [0.0] * 10
    result, imputed = impute_censored_days(values)
    assert imputed == 0


# ---------------------------------------------------------------------------
# Individual models
# ---------------------------------------------------------------------------


def test_ses_constant_series_stays_constant():
    fit = fit_ses([7.0] * 30)
    assert fit.predict(10) == pytest.approx([7.0] * 10, abs=1e-6)


def test_ses_grid_picks_known_alpha():
    fit = fit_ses([1.0, 5.0, 1.0, 5.0, 1.0, 5.0, 1.0, 5.0, 1.0, 5.0])
    assert fit.params["alpha"] in (0.1, 0.2, 0.3, 0.5)


def test_holt_follows_upward_trend():
    fit = fit_holt(_trend_series(60))
    path = fit.predict(14)
    assert path[-1] > path[0]
    assert path[-1] >= 0.0


def test_holt_nonnegative_on_declining_series():
    fit = fit_holt([100.0 - i for i in range(60)])
    assert all(v >= 0.0 for v in fit.predict(30))


def test_seasonal_requires_two_weeks():
    assert fit_seasonal([5.0] * 13) is None


def test_seasonal_varies_by_day_of_week():
    fit = fit_seasonal(_seasonal_series(60))
    assert fit is not None
    path = fit.predict(14)
    assert max(path) - min(path) > 1.0


def test_croston_positive_rate_for_sparse():
    fit = fit_croston(_sparse_series(70))
    path = fit.predict(14)
    assert all(v > 0 for v in path)
    assert len(set(path)) == 1  # constant rate


def test_croston_zero_for_all_zero():
    fit = fit_croston([0.0] * 40)
    assert fit.predict(7) == [0.0] * 7


def test_fit_mean_prefix_one_step():
    fit = fit_mean([2.0, 4.0, 6.0])
    assert fit.fitted_one_step == [2.0, 2.0, 3.0]


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


def test_wmape_known_value():
    assert wmape([10.0, 10.0], [10.0, 10.0]) == 0.0
    assert wmape([5.0, 5.0], [10.0, 10.0]) == pytest.approx(0.5)


def test_wmape_zero_actual_does_not_divide_by_zero():
    assert wmape([1.0], [0.0]) == 1.0


def test_holdout_tiers():
    assert holdout_days(120) == 14
    assert holdout_days(40) == 7
    assert holdout_days(25) == 5
    assert holdout_days(15) == 3
    assert holdout_days(5) == 0


def test_confidence_band_ordering_and_growth():
    p50 = [10.0] * 14
    p10, p90 = confidence_band(p50, sigma=2.0)
    assert all(p10[i] <= p50[i] <= p90[i] for i in range(14))
    assert all(v >= 0.0 for v in p10)
    assert p90[-1] - p10[-1] >= p90[0] - p10[0]


def test_confidence_band_zero_sigma_collapses():
    p10, p90 = confidence_band([5.0, 5.0], sigma=0.0)
    assert p10 == [5.0, 5.0]
    assert p90 == [5.0, 5.0]


def test_robust_sigma():
    assert robust_sigma([0.1, -0.1, 0.0, 0.05]) > 0
    assert robust_sigma([1.0]) == 0.0


def test_legacy_predict_matches_v1_formula():
    values = [3.0, 8.0, 5.0, 6.0, 4.0, 7.0, 5.0, 6.0, 5.0, 6.0]
    expected = max(exponential_smoothing(values), (sum(values) / len(values)) * 0.5)
    assert legacy_predict_daily(values) == pytest.approx(expected)
    assert legacy_predict_daily([]) == 0.0


# ---------------------------------------------------------------------------
# build_ensemble — selection, intervals, edges
# ---------------------------------------------------------------------------


def test_empty_history_bundle():
    bundle = build_ensemble([], HORIZON)
    assert bundle.meta["reason"] == "no_history"
    assert bundle.predictions == [0.0] * HORIZON
    assert bundle.p10 == bundle.p90 == [0.0] * HORIZON


def test_all_zero_bundle():
    bundle = build_ensemble(_rows([0.0] * 50), HORIZON)
    assert bundle.model == "zero"
    assert bundle.predictions == [0.0] * HORIZON


def test_horizon_lengths_supported():
    rows = _rows(_seasonal_series(60))
    for h in (30, 60, 90):
        bundle = build_ensemble(rows, h)
        assert len(bundle.predictions) == h
        assert len(bundle.p10) == h
        assert len(bundle.p90) == h


def test_intervals_ordered_on_real_data():
    bundle = build_ensemble(_rows(_seasonal_series(70)), HORIZON)
    assert all(bundle.p10[i] <= bundle.predictions[i] <= bundle.p90[i] for i in range(HORIZON))


def test_seasonal_series_selects_seasonal_model():
    bundle = build_ensemble(_rows(_seasonal_series(70)), HORIZON)
    assert "seasonal_holt" in bundle.model


def test_constant_series_blends_tied_models():
    bundle = build_ensemble(_rows([5.0] * 40), HORIZON)
    assert bundle.meta["blended"] is True
    assert "+" in bundle.model
    assert all(v == pytest.approx(5.0, abs=0.5) for v in bundle.predictions)


def test_sparse_series_stays_sane():
    bundle = build_ensemble(_rows(_sparse_series(70)), HORIZON)
    assert bundle.meta["intermittent"] is True
    mean_pred = sum(bundle.predictions) / len(bundle.predictions)
    assert 0 < mean_pred <= 10.0


def test_short_series_uses_no_holdout_path():
    bundle = build_ensemble(_rows([3.0, 4.0, 5.0]), HORIZON)
    assert bundle.meta["holdout_days"] == 0
    assert len(bundle.predictions) == HORIZON
    assert bundle.predictions[0] > 0


def test_stockout_correction_flag():
    # >= 10 u/day so the velocity gate leaves imputation eligible
    values = [15.0, 15.0, 15.0, 0.0, 15.0, 15.0, 15.0] * 8
    on = build_ensemble(_rows(values), HORIZON, stockout_correction=True)
    off = build_ensemble(_rows(values), HORIZON, stockout_correction=False)
    assert on.meta["imputed_days"] > 0
    assert off.meta["imputed_days"] == 0


def test_stockout_imputation_skipped_below_trend_min():
    # low-volume series: bracketed zeros are structural, not censored demand
    values = [5.0, 5.0, 5.0, 0.0, 5.0, 5.0, 5.0] * 8
    bundle = build_ensemble(_rows(values), HORIZON, stockout_correction=True)
    assert bundle.meta["velocity_daily"] < 10.0
    assert bundle.meta["imputed_days"] == 0


def test_strong_external_candidate_wins():
    rows = _rows(_seasonal_series(70))
    external = ExternalCandidate(
        name="prophet",
        wmape=0.001,
        bias=0.0,
        residuals=[0.0] * 14,
        horizon_predictions=[10.0] * HORIZON,
    )
    bundle = build_ensemble(rows, HORIZON, external=external)
    assert "prophet" in bundle.model


def test_weak_external_candidate_ignored():
    rows = _rows(_seasonal_series(70))
    external = ExternalCandidate(
        name="prophet",
        wmape=0.99,
        bias=0.5,
        residuals=[5.0] * 14,
        horizon_predictions=[999.0] * HORIZON,
    )
    bundle = build_ensemble(rows, HORIZON, external=external)
    assert "prophet" not in bundle.model
    assert "prophet" in bundle.meta["candidates"]


def test_candidate_scores_recorded():
    bundle = build_ensemble(_rows(_trend_series(60)), HORIZON)
    assert "ses" in bundle.meta["candidates"]
    assert "holt" in bundle.meta["candidates"]
    assert bundle.wmape >= 0


def test_low_velocity_series_excludes_trend_models():
    # Rising series below 10 units/day: holt fits it, but must not be eligible.
    values = [round(4 + 0.1 * i + (i % 5) * 0.2, 2) for i in range(60)]
    bundle = build_ensemble(_rows(values), HORIZON)
    assert bundle.meta["velocity_daily"] < 10.0
    assert set(bundle.meta["candidates"]) <= {"ses", "mean", "croston"}
    assert "holt" not in bundle.model
    assert "seasonal" not in bundle.model


def test_high_velocity_series_keeps_trend_models():
    values = [round(12 + 0.1 * i + (i % 5) * 0.2, 2) for i in range(60)]
    bundle = build_ensemble(_rows(values), HORIZON)
    assert bundle.meta["velocity_daily"] >= 10.0
    assert "holt" in bundle.meta["candidates"]


# ---------------------------------------------------------------------------
# CI no-regression guard: ensemble must not be materially worse than v1
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "values",
    [_seasonal_series(70), _sparse_series(70), _trend_series(70), [10.0] * 70],
    ids=["seasonal", "sparse", "trend", "constant"],
)
def test_v2_wmape_not_worse_than_v1(values: list[float]):
    holdout = 14
    train_values = values[:-holdout]
    actual = values[-holdout:]
    train_rows = _rows(train_values)

    v1_point = legacy_predict_daily(train_values)
    v1_wmape = wmape([v1_point] * holdout, actual)

    bundle = build_ensemble(train_rows, holdout)
    v2_wmape = wmape(bundle.predictions[:holdout], actual)

    assert v2_wmape <= v1_wmape * 1.05 + 0.02, f"ensemble v2 regressed: v2={v2_wmape:.3f} vs v1={v1_wmape:.3f}"


# ---------------------------------------------------------------------------
# Optional Prophet adapter (runs without prophet installed)
# ---------------------------------------------------------------------------


def test_prophet_available_returns_bool():
    from agent.forecast_prophet import prophet_available

    assert isinstance(prophet_available(), bool)


def test_prophet_eligibility_length_gate(monkeypatch):
    from agent import forecast_prophet

    monkeypatch.setattr(forecast_prophet, "prophet_available", lambda: True)
    monkeypatch.setattr(forecast_prophet.settings, "forecast_enable_prophet", True)

    short = _rows(_seasonal_series(30))
    long_enough = _rows(_seasonal_series(70))

    assert forecast_prophet.prophet_eligible(short) is False
    assert forecast_prophet.prophet_eligible(long_enough) is True


def test_prophet_disabled_by_flag(monkeypatch):
    from agent import forecast_prophet

    monkeypatch.setattr(forecast_prophet, "prophet_available", lambda: True)
    monkeypatch.setattr(forecast_prophet.settings, "forecast_enable_prophet", False)

    assert forecast_prophet.prophet_eligible(_rows(_seasonal_series(70))) is False


@pytest.mark.asyncio
async def test_try_prophet_returns_none_when_ineligible(monkeypatch):
    from agent import forecast_prophet

    monkeypatch.setattr(forecast_prophet, "prophet_available", lambda: False)
    result = await forecast_prophet.try_prophet(_rows(_seasonal_series(70)), HORIZON, True)
    assert result is None


def test_prophet_circuit_breaker(monkeypatch):
    from agent import forecast_prophet

    breaker = forecast_prophet.ProphetCircuitBreaker()
    assert breaker.is_open() is False
    for _ in range(forecast_prophet.CIRCUIT_FAILURE_THRESHOLD):
        breaker.record_failure()
    assert breaker.is_open() is True
    breaker.record_success()
    assert breaker.is_open() is False


# ---------------------------------------------------------------------------
# Node-level: modes, persistence, fallback
# ---------------------------------------------------------------------------


def _fake_rows(units: list[float]) -> list[tuple[float, date]]:
    return list(zip(units, _days(len(units)), strict=False))


class _FakeSession:
    def __init__(self, rows: list[tuple[float, date]]):
        self.rows = rows
        self.added: list[object] = []
        self.committed = False

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *args: object) -> bool:
        return False

    async def execute(self, query: object) -> object:
        rows = self.rows

        class _Result:
            def all(self) -> list[tuple[float, date]]:
                return rows

        return _Result()

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.committed = True


def _patch_session(monkeypatch: pytest.MonkeyPatch, rows: list[tuple[float, date]]) -> _FakeSession:
    session = _FakeSession(rows)
    monkeypatch.setattr("agent.nodes.forecast_node.async_session_factory", lambda: session)
    return session


@pytest.mark.asyncio
async def test_shadow_mode_persists_both_serves_v1(monkeypatch):
    from agent.nodes import forecast_node as fn

    monkeypatch.setattr(fn.settings, "forecast_model_version", "shadow")
    session = _patch_session(monkeypatch, _fake_rows(_seasonal_series(70)))

    result = await fn.calculate_forecast(sku_id=900001, current_stock=100, lead_time_days=7)

    assert result.model_version == "exp_smoothing_v1"
    versions = [getattr(r, "model_version", None) for r in session.added]
    assert versions == ["exp_smoothing_v1", "ensemble_v2"]
    v2_row = session.added[1]
    assert v2_row.p10_daily_demand is not None
    assert v2_row.backtest_wmape is not None
    assert v2_row.horizon_days == 30


@pytest.mark.asyncio
async def test_ensemble_mode_serves_v2_with_confidence(monkeypatch):
    from agent.nodes import forecast_node as fn

    monkeypatch.setattr(fn.settings, "forecast_model_version", "ensemble_v2")
    session = _patch_session(monkeypatch, _fake_rows(_seasonal_series(70)))

    result = await fn.calculate_forecast(sku_id=900002, current_stock=100, lead_time_days=7)

    assert result.model_version == "ensemble_v2"
    assert result.fallback_used is False
    assert result.p10_daily_demand is not None and result.p90_daily_demand is not None
    assert result.p10_daily_demand <= result.predicted_daily_demand <= result.p90_daily_demand
    assert result.days_of_cover_p90 is not None
    assert result.days_of_cover_p90 <= (result.days_of_cover_p10 or float("inf"))
    assert [r.model_version for r in session.added] == ["ensemble_v2"]


@pytest.mark.asyncio
async def test_ensemble_failure_falls_back_to_v1(monkeypatch):
    from agent.nodes import forecast_node as fn

    monkeypatch.setattr(fn.settings, "forecast_model_version", "ensemble_v2")
    monkeypatch.setattr(fn, "build_ensemble", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    session = _patch_session(monkeypatch, _fake_rows(_seasonal_series(70)))

    result = await fn.calculate_forecast(sku_id=900003, current_stock=100, lead_time_days=7)

    assert result.model_version == "exp_smoothing_v1"
    assert result.fallback_used is True
    assert session.added, "fallback must still persist a forecast row"


@pytest.mark.asyncio
async def test_invalid_mode_treated_as_v1(monkeypatch):
    from agent.nodes import forecast_node as fn

    monkeypatch.setattr(fn.settings, "forecast_model_version", "bogus_mode")
    session = _patch_session(monkeypatch, _fake_rows([5.0] * 30))

    result = await fn.calculate_forecast(sku_id=900004, current_stock=100, lead_time_days=7)

    assert result.model_version == "exp_smoothing_v1"
    assert [r.model_version for r in session.added] == ["exp_smoothing_v1"]


@pytest.mark.asyncio
async def test_zero_demand_gives_none_cover(monkeypatch):
    from agent.nodes import forecast_node as fn

    monkeypatch.setattr(fn.settings, "forecast_model_version", "exp_smoothing_v1")
    _patch_session(monkeypatch, _fake_rows([0.0] * 30))

    result = await fn.calculate_forecast(sku_id=900005, current_stock=10, lead_time_days=7)

    assert result.predicted_daily_demand == 0.0
    assert result.days_of_stock_remaining is None


@pytest.mark.asyncio
async def test_empty_history_v1_and_v2(monkeypatch):
    from agent.nodes import forecast_node as fn

    monkeypatch.setattr(fn.settings, "forecast_model_version", "ensemble_v2")
    _patch_session(monkeypatch, [])

    result = await fn.calculate_forecast(sku_id=900006, current_stock=42, lead_time_days=7)

    assert result.predicted_daily_demand == 0.0
    assert result.days_of_stock_remaining is None


# ---------------------------------------------------------------------------
# Lead-time fixes (sync_node / outcomes defensive helpers)
# ---------------------------------------------------------------------------


def test_supplier_lead_time_coercion():
    from agent.nodes.sync_node import _supplier_lead_time

    assert _supplier_lead_time(14) == 14
    assert _supplier_lead_time(0) == 7
    assert _supplier_lead_time(-3) == 7
    assert _supplier_lead_time(None) == 7
    assert _supplier_lead_time("not-an-int") == 7
    assert _supplier_lead_time(True) == 7


def test_outcomes_lead_time_coercion():
    from agent.outcomes import _lead_time

    assert _lead_time(10) == 10
    assert _lead_time(0) == 7
    assert _lead_time(False) == 7
    assert _lead_time(object()) == 7
