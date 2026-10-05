# Forecast Promotion — Decision Memo

**Scope:** offline backtest evidence and promotion criteria for the v2
ensemble forecast engine, produced as Week 1 of the forecast-to-value
mission. Companion implementation: engine selection, safety gates, metrics
and runbook in this branch (see [FORECAST-ENGINE-RUNBOOK.md](FORECAST-ENGINE-RUNBOOK.md)).

## Evidence

Backtest: `scripts/forecast_backtest.py`, rolling-origin holdout against the
demo seed (10 SKUs, 58–90 days each, synthetic weekly + holiday seasonality,
zero-sale days are not present in the seed). Both engines scored on identical
train/test splits; pooled wMAPE weights each SKU by its actual demand.

| Run | Holdout | Folds | Min history | SKUs / evals | v1 wMAPE | v2 wMAPE | Δ | Coverage |
|---|---|---|---|---|---|---|---|---|
| A | 14d | 1 | 60d | 9 / 9 | 42.2% | 15.8% | −62.5% | 0.94 |
| D | 14d | 2 | 60d | 9 / 18 | 40.3% | 15.8% | −60.8% | 0.88 |
| **E (primary)** | **14d** | **2** | **58d** | **10 / 20** | **40.6%** | **17.0%** | **−58.2%** | **0.86** |
| B | 14d | 3 | 90d | 5 / 15 | 39.5% | 12.1% | −69.4% | 0.93 |
| C | 28d | 1 | 90d | 5 / 5 | 39.5% | 10.6% | −73.3% | 0.99 |

Primary run (E) also gives MASE 1.01 → 0.54 and pooled bias −0.06% → 0.00%;
8 of 10 SKUs improved, 0 skipped. Model mix: `seasonal_holt` 14/20, `holt` 2,
`mean` 1, blends 2, `croston` 1.

Tier breakdown (primary run E, pooled wMAPE):

| Tier | Definition | Evals | v1 | v2 | Δ | Coverage |
|---|---|---|---|---|---|---|
| high | mean ≥ 10 u/day | 16 | 39.9% | 15.0% | **−62.4%** | 0.93 |
| medium | 1.5 – 10 u/day | 4 | 56.5% | 63.1% | **+11.8%** | 0.59 |
| intermittent | zero-share ≥ 30% or mean < 1.5 u/day | 0 | — | — | — | — |

**Findings**

1. High-velocity SKUs: large, consistent improvement (−58% to −73% relative)
   across every configuration, no regressions.
2. Medium-velocity SKUs: the ensemble **regresses** (+11.8%, both SKUs, n=4
   evals); interval coverage drops to 0.59.
3. Intermittent SKUs: **not testable on demo data** — the seed only stores
   days with sales, so no SKU meets the intermittency definition. Croston is
   exercised in unit tests only.
4. Interval coverage is conservative overall (0.86–0.94 vs target 0.80):
   safe for stockout risk, slightly capital-heavy.

## Promotion criteria (explicit)

Offline, per candidate release — run `scripts/forecast_backtest.py` with the
primary config and require **all** of:

1. Pooled wMAPE improves ≥ 15% relative vs v1 — **PASS** (−58.2%).
2. No velocity tier regresses — **FAIL** (medium +11.8%).
3. No individual high-velocity SKU regresses — **PASS** (8/8).
4. |pooled bias| ≤ 1% — **PASS** (0.00%).
5. p10–p90 coverage within 0.75–0.90 — **PASS** (0.86); per tier: high 0.93,
   medium 0.59 (**flag**).
6. Intermittent tier measured on real zero-inflated history — **NOT YET
   TESTABLE**.

Online, per tenant — implemented as the daily promotion gates
(`build_gates()` in `agent/forecast_engine.py`): ≥ 14 paired shadow days,
≥ 3 evaluable SKUs, MAPE ratio ensemble/exponential ≤ 0.85, |bias| ≤ 8% on
high-velocity SKUs, coverage ≥ 0.45, rollout cohort percent.

## Decision: PARTIAL GO

**GO — merchant-level staged promotion.** High-velocity results plus the
per-tenant gates justify flipping individual tenants `shadow → ensemble`,
each measured on their own history first, with instant demotion
(`FORECAST_ENGINE_OVERRIDE=exponential`, admin API demote) and three
Prometheus alerts standing by.

**NO-GO — any unmeasured/global promotion.** Therefore this branch makes
every default measure-first: all tenants (existing via migration `016`,
new via column default) and `FORECAST_ENGINE_DEFAULT` start on `shadow`;
the daily job is the only path to `ensemble`. A global default flip to
`ensemble` requires, additionally:

- online gate evidence sustained ≥ 14 consecutive days across the rollout
  cohort (`forecast_promotion_gate_pass` staying at 1),
- medium-tier regression root-caused (suspect: seasonal Holt overfitting
  low-volume noise; candidates are tier-gated model selection or
  first/last demand Croston for intermittent SKUs),
- intermittent tier validated on real zero-inflated history.

Recommended rollout posture: start `FORECAST_ENGINE_ROLLOUT_PERCENT` at
25–50, raise it as gate results stay green, and keep the three alert rules
armed. Follow-up hardening: auto-demote a promoted tenant when its gates
start failing (today: alert → operator demotes via runbook).

## Consumer verification

Risk and PO Draft nodes consume the served engine's output engine-agnostically
(`state["forecasts"]`) and now also use its confidence bands: risk escalates
on the p90 cover, PO quantities plan against p90 demand (see
`tests/test_band_consumption.py`).

## Limitations

- Demo seed only: synthetic, no zero-days, 10 SKUs, single merchant; medium
  tier evidence is 4 evaluations of 2 SKUs.
- Results must be re-run against real Shopify history before any tenant in
  production is promoted (step 2 of the rollout procedure in
  [FORECAST-TUNING.md](FORECAST-TUNING.md)).

## Reproduce

```bash
py -3.12 scripts/forecast_backtest.py --holdout 14 --folds 2 --min-history 58 --json report.json
py -3.12 scripts/forecast_backtest.py --holdout 14 --folds 3 --min-history 90
py -3.12 scripts/forecast_backtest.py --holdout 28 --folds 1 --min-history 90
```
