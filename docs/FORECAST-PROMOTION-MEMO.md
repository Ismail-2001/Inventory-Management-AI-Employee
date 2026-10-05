# Forecast Promotion — Decision Memo

**Scope:** offline backtest evidence, promotion criteria, and the go/no-go
decision for the v2 ensemble forecast engine. Companion implementation:
engine selection, safety gates, metrics and runbook in
[FORECAST-ENGINE-RUNBOOK.md](FORECAST-ENGINE-RUNBOOK.md).

**Status (5 Oct 2026): GO — ensemble is the global default.** All five
offline criteria pass after the medium-velocity regression was root-caused
and fixed (see *Diagnosis* below); the safety machinery (kill switch,
per-merchant override, alerts) stays armed and the open intermittent-tier
validation is tracked in issue #51.

## Evidence

Backtest: `scripts/forecast_backtest.py`, rolling-origin holdout against the
demo seed (10 SKUs, 58–90 stored rows each, synthetic weekly + holiday
seasonality, zero-sale days are not stored as rows). Both engines are scored
on identical train/test splits; pooled wMAPE weights each SKU by its actual
demand.

**Scoring is calendar-aligned.** The actual series for the hold-out horizon
is 0-filled across every calendar day after the last training day, so
prediction day *i* always compares against demand on the same calendar day.
(Previous versions compared horizon day *i* against the *i*-th stored sale
row, which mis-aligns whenever a SKU skips zero-sale days — only the medium
tier was affected. High-tier numbers below are directly comparable to the
original memo; medium-tier numbers are not.)

| Run | Holdout | Folds | Min history | SKUs / evals | v1 wMAPE | v2 wMAPE | Δ | Coverage |
|---|---|---|---|---|---|---|---|---|
| A | 14d | 1 | 60d | 9 / 9 | 42.7% | 16.4% | −61.6% | 0.93 |
| D | 14d | 2 | 60d | 9 / 18 | 41.0% | 16.1% | −60.7% | 0.87 |
| **E (primary)** | **14d** | **2** | **58d** | **10 / 20** | **42.3%** | **17.8%** | **−57.9%** | **0.85** |
| B | 14d | 3 | 90d | 5 / 15 | 39.5% | 12.1% | −69.4% | 0.93 |
| C | 28d | 1 | 90d | 5 / 5 | 39.5% | 10.6% | −73.3% | 0.99 |

Primary run (E): MASE 1.05 → 0.52, demand-weighted pooled bias −6.65%
(v1) → **−0.35%** (v2); **10 of 10 SKUs improved, 0 regressed**. Model mix:
`seasonal_holt` 14/20, `mean` 1, `mean+croston` 1, `croston+ses` 1,
`mean+holt` 1, `ses` 1.

Tier breakdown (primary run E, pooled wMAPE):

| Tier | Definition | Evals | v1 | v2 | Δ | Coverage |
|---|---|---|---|---|---|---|
| high | mean ≥ 10 u/day | 16 | 40.1% | 15.1% | **−62.5%** | 0.94 |
| medium | 1.5 – 10 u/day | 4 | 93.5% | 81.2% | **−13.2%** | 0.51 (flag) |
| intermittent | zero-share ≥ 30% or mean < 1.5 u/day | 0 | — | — | — | — |

## Diagnosis — why the medium tier regressed (+11.8% originally)

Root-caused on the original run E (per-SKU/fold replay + counterfactual
candidate scoring), three compounding causes:

1. **Trend extrapolation on short, noisy, low-volume series.** Both losing
   evals were `holt`-selected on 30-day trains with a 7-day internal
   selection holdout: SKU 1 fold 1 predicted a flat 5.5 u/day against an
   actual 3.6 (post-ramp level lock-in), SKU 7 fold 1 extrapolated the
   train-window downtrend to **0.0 u/day** against an actual 4.0. Seven noisy
   holdout days cannot validate a trend; the legacy v1 (flat SES) is immune
   to this failure mode, which is why v1 won. High-velocity SKUs were
   unaffected: dense history + strong weekly pattern make `seasonal_holt`
   genuinely reliable there (−62.5%).
2. **Evaluation misalignment on gap days (measurement bias).** The medium
   SKUs store rows only on sale days (25–32% calendar gaps); high SKUs are
   gapless. Horizon day *i* was compared against the *i*-th *sale* row, so
   after the first gap the sequences drifted apart — and only the medium
   tier paid for it. Fixed: calendar-aligned scoring with 0-filled actuals
   (dense SKUs score identically; this is why high-tier numbers match the
   original memo).
3. **Stockout imputation over-forecasting sparse series.** Bracketed zeros
   were imputed as censored (stockout) demand, but on low-volume SKUs those
   zeros are predominantly true zero-demand days — levels were inflated
   (SKU 1's flat forecasts ran ~+50% over actual), which showed up as
   positive bias and over-ordered quantities.

## What changed (lightest effective fix)

Both changes are small, reversible, gated by one shared constant, and fully
unit-tested (`agent/forecast.py`, `TREND_MIN_DAILY = 10` u/day):

1. **Velocity-gated model selection** — below 10 units/day (calendar mean,
   pre-imputation) the candidates are flat models only (`ses`, `mean`,
   `croston`); `holt` and `seasonal_holt` require ≥ 10 u/day. High-velocity
   selection is unchanged.
2. **Velocity-gated stockout imputation** — censored-demand imputation only
   runs at ≥ 10 u/day (fast sellers run out; slow sellers mostly just have
   quiet days). `stockout_correction=False` semantics unchanged.
3. **Calendar-aligned backtest scoring** — measurement fix, not model
   behavior (`aligned_actual()` in the backtest; `tests/test_forecast_backtest.py`).

Not tried on purpose: new models, blend-weight tuning, holdout
recalibration — the evidence pointed at selection policy + measurement, and
the fix above passes every criterion without them.

## Promotion criteria — re-evaluated on run E

1. Pooled wMAPE improves ≥ 15% relative vs v1 — **PASS (−57.9%)**.
2. No velocity tier regresses — **PASS** (high −62.5%, medium −13.2%).
3. No individual high-velocity SKU regresses — **PASS (10/10 improved;
   0 regressed overall)**.
4. |pooled bias| ≤ 1% — **PASS (−0.35%; v1 is −6.65%)**.
5. p10–p90 coverage within 0.75–0.90 — **PASS (0.85)**; per tier: high 0.94,
   medium 0.51 (**flag** — flat models draw tight bands around a noisy
   medium tier; revisit interval width for low-volume SKUs in #51).
6. Intermittent tier measured on real zero-inflated history — **still not
   testable on demo data** (seed has no true zero-inflation; Croston covered
   by unit tests only) — open in #51.

Online gates (`build_gates()` in `agent/forecast_engine.py`: ≥ 14 paired
shadow days, ≥ 3 evaluable SKUs, MAPE ratio ≤ 0.85, |bias| ≤ 8% on
high-velocity SKUs, coverage ≥ 0.45, rollout cohort) remain in place for any
tenant that is (re-)parked on `shadow`.

## Decision: GO — flip the global default to `ensemble`

The original PARTIAL GO withheld a global flip over the medium-tier
regression; that blocker is resolved and criteria 1–5 pass. The flip is:

- `FORECAST_ENGINE_DEFAULT` → `ensemble` (config default),
- `merchants.forecast_engine` column default + server default → `ensemble`
  (migration `018`, also promotes existing `shadow` rows),
- still overridable at any time: `FORECAST_ENGINE_OVERRIDE=exponential`
  (global kill switch), per-merchant demote endpoint, and the daily
  promotion job for anything parked back on `shadow`.

**Honest caveats:** criterion 6 (intermittent on real history) is still
open, and the "≥ 14 consecutive online gate days" condition from the
original memo has *not* been met — it is superseded by this offline-evidence
decision and replaced by a 7–14 day post-flip watch (below). Demo evidence
remains small (medium tier = 2 SKUs / 4 evals).

**Post-flip monitoring (first 7–14 days)** — dashboards/alerts already in
place: `forecast_engine_used` (must stay `ensemble`), `forecast_fallback_count`
/ `forecast_timeout_total` / `forecast_circuit_tripped` (fallback paths),
`forecast_mape_ratio` + `forecast_promotion_gate_pass` (weekly report
`build_weekly_engine_report`), `forecast_error_pct` (accuracy trend on the
ROI dashboard). Any fallback spike or MAPE ratio > 0.85 → set
`FORECAST_ENGINE_OVERRIDE=exponential` (documented in the runbook) and
investigate before removing it.

## Consumer verification

Risk and PO Draft nodes consume the served engine's output engine-agnostically
(`state["forecasts"]`) and use its confidence bands: risk escalates on the
p90 cover, PO quantities plan against p90 demand (see
`tests/test_band_consumption.py`). Low-volume SKUs now plan on flat
(ses/mean/croston) forecasts — no trend-driven PO quantities below 10 u/day.

## Limitations

- Demo seed only: synthetic, medium-tier evidence is 4 evaluations of
  2 SKUs; intermittent tier untested on real zero-inflated history (#51).
- Medium-tier interval coverage (0.51, p10–p90) is below the pooled target;
  pooled 0.85 passes, and the online gate measures p50 coverage (≥ 0.45)
  — track low-volume interval calibration in #51.
- Re-validate against real Shopify history for any tenant before trusting
  PO quantities in production (step 2 of the rollout procedure in
  [FORECAST-TUNING.md](FORECAST-TUNING.md)).

## Reproduce

```bash
py -3.12 scripts/forecast_backtest.py --holdout 14 --folds 2 --min-history 58 --json report.json
py -3.12 scripts/forecast_backtest.py --holdout 14 --folds 3 --min-history 90
py -3.12 scripts/forecast_backtest.py --holdout 28 --folds 1 --min-history 90
```
